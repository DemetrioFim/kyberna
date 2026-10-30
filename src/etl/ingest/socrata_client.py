from __future__ import annotations

import calendar
import datetime
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from src.core.logging import logger
from src.core.paths import raw_path
from src.core.settings import get_settings

DEFAULT_SOCRATA_ENDPOINT = "https://data.iowa.gov/resource/m3tr-qhgy.csv"
DEFAULT_PAGE_SIZE = 50000


def is_retryable_exception(exc: BaseException) -> bool:
    """Identifica se a exceção HTTP justifica retry com backoff exponencial.

    Apenas status transitórios de servidor (5xx), rate limit (429) e falhas de rede/timeout.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError))


class SocrataClient:
    """Cliente HTTP com resiliência para ingestão da API Socrata (Iowa Liquor Sales)."""

    def __init__(
        self,
        endpoint_url: str = DEFAULT_SOCRATA_ENDPOINT,
        app_token: str | None = None,
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url
        settings = get_settings()
        self.app_token = app_token or settings.socrata_app_token
        self.timeout_seconds = timeout_seconds

        headers = {
            "Accept": "text/csv",
            "User-Agent": "Kyberna-ETL/1.0",
        }
        if self.app_token:
            headers["X-App-Token"] = self.app_token

        if client is not None:
            self._client = client
        elif transport is not None:
            self._client = httpx.Client(transport=transport, timeout=timeout_seconds, headers=headers)
        else:
            self._client = httpx.Client(timeout=timeout_seconds, headers=headers)

    def close(self) -> None:
        """Fecha o cliente HTTP subjacente."""
        self._client.close()

    def __enter__(self) -> SocrataClient:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    @retry(
        retry=retry_if_exception(is_retryable_exception),
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1.0, max=30.0, jitter=1.0),
        reraise=True,
    )
    def fetch_page_csv(
        self,
        start_date: str,
        end_date: str,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> str:
        """Busca uma página CSV da API Socrata com paginação determinística e retry.

        Args:
            start_date: Data inicial (inclusive) no formato YYYY-MM-DD.
            end_date: Data final (inclusive) no formato YYYY-MM-DD.
            limit: Quantidade máxima de registros por página ($limit).
            offset: Deslocamento para paginação ($offset).

        Returns:
            String contendo o corpo da resposta em formato CSV.
        """
        params = {
            "$where": f"date >= '{start_date}' and date <= '{end_date}'",
            "$order": ":id",
            "$limit": str(limit),
            "$offset": str(offset),
        }
        logger.debug(f"Buscando Socrata: limit={limit} offset={offset} {start_date}..{end_date}")
        response = self._client.get(self.endpoint_url, params=params)
        response.raise_for_status()
        return response.text

    def download_month(
        self,
        year: int,
        month: int,
        *,
        base_dir: Path | None = None,
        force: bool = False,
        page_size: int = DEFAULT_PAGE_SIZE,
        start_bound: datetime.date | None = None,
        end_bound: datetime.date | None = None,
    ) -> Path:
        """Baixa de forma idempotente todos os dados de um mês calendário para data/raw/.

        Args:
            year: Ano da partição (ex: 2024).
            month: Mês da partição (1 a 12).
            base_dir: Diretório raiz customizado (opcional, para testes).
            force: Se True, sobrescreve o arquivo existente.
            page_size: Tamanho de cada página baixada.
            start_bound: Limite inferior opcional de data.
            end_bound: Limite superior opcional de data.

        Returns:
            Path do arquivo CSV baixado (`data/raw/sales/year=YYYY/month=MM/data.csv`).
        """
        target_path = raw_path("sales", year=year, month=month, base=base_dir)

        if target_path.exists() and not force:
            logger.info(f"Mês {year}-{month:02d} já existe em {target_path}. Pulando (idempotência).")
            return target_path

        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.with_suffix(f".tmp_{year}_{month:02d}.csv")

        # Define as datas de início e fim do mês respeitando limites externos
        num_days = calendar.monthrange(year, month)[1]
        m_start = datetime.date(year, month, 1)
        m_end = datetime.date(year, month, num_days)

        if start_bound and start_bound > m_start:
            m_start = start_bound
        if end_bound and end_bound < m_end:
            m_end = end_bound

        str_start = m_start.isoformat()
        str_end = m_end.isoformat()

        offset = 0
        total_rows = 0

        try:
            with temp_path.open("w", encoding="utf-8", newline="") as out_f:
                while True:
                    csv_text = self.fetch_page_csv(
                        start_date=str_start,
                        end_date=str_end,
                        limit=page_size,
                        offset=offset,
                    )
                    lines = csv_text.strip().splitlines()
                    if not lines:
                        break

                    # Primeira página: escreve cabeçalho + dados
                    if offset == 0:
                        out_f.write(csv_text.strip() + "\n")
                        data_rows = max(0, len(lines) - 1)
                    # Páginas subsequentes: pula o cabeçalho
                    elif len(lines) > 1:
                        out_f.write("\n".join(lines[1:]) + "\n")
                        data_rows = len(lines) - 1
                    else:
                        data_rows = 0

                    total_rows += data_rows
                    logger.debug(f"Mês {year}-{month:02d}: lidas {data_rows} linhas no offset {offset}")

                    # Se a página retornou menos dados que o limite, atingimos o fim do mês
                    if data_rows < page_size:
                        break

                    offset += page_size

            temp_path.replace(target_path)
            logger.info(f"Mês {year}-{month:02d} concluído: {total_rows:,} linhas salvas em {target_path}.")
            return target_path
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def download_range(
        self,
        start_date: datetime.date | str,
        end_date: datetime.date | str,
        base_dir: Path | None = None,
        force: bool = False,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[Path]:
        """Baixa todos os meses contidos no intervalo de datas especificado."""
        dt_start = datetime.date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
        dt_end = datetime.date.fromisoformat(end_date) if isinstance(end_date, str) else end_date

        if dt_start > dt_end:
            raise ValueError(f"start_date ({dt_start}) não pode ser maior que end_date ({dt_end})")

        downloaded: list[Path] = []
        cur_year = dt_start.year
        cur_month = dt_start.month

        while (cur_year, cur_month) <= (dt_end.year, dt_end.month):
            p = self.download_month(
                year=cur_year,
                month=cur_month,
                base_dir=base_dir,
                force=force,
                page_size=page_size,
                start_bound=dt_start,
                end_bound=dt_end,
            )
            downloaded.append(p)

            # Avança para o próximo mês
            if cur_month == 12:
                cur_year += 1
                cur_month = 1
            else:
                cur_month += 1

        return downloaded
