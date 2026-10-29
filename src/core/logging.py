from __future__ import annotations

import functools
import json
import logging
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, ParamSpec, TypeVar

from rich.logging import RichHandler

from src.core.settings import get_settings

P = ParamSpec("P")
R = TypeVar("R")


class JsonFormatter(logging.Formatter):
    """Formatador de log estruturado em JSON para ambientes de CI e Produção."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Inclui metadados extras passados no dicionário 'extra'
        standard_attrs = {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "id",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
        }
        for key, val in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                log_entry[key] = val

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(env: str | None = None, level: int = logging.INFO) -> None:
    """Configura handlers e formatadores do logging global da aplicação.

    Args:
        env: Ambiente ('dev', 'ci' ou 'prod'). Se omitido, consulta Settings.
        level: Nível mínimo de logging (padrão: INFO).
    """
    current_env = env or get_settings().env
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Limpa handlers anteriores para evitar duplicações
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    if current_env == "dev":
        handler = RichHandler(
            rich_tracebacks=True,
            show_time=True,
            show_path=False,
            markup=False,
        )
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())

    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Retorna logger nomeado."""
    return logging.getLogger(name)


logger = get_logger("kyberna")


class TimedStep:
    """Context manager e decorator para monitoramento de etapas do pipeline.

    Calcula e registra a duração da etapa e quantidade opcional de linhas processadas.
    """

    def __init__(
        self,
        name: str,
        row_count: int | None = None,
        logger_instance: logging.Logger | None = None,
    ) -> None:
        self.name = name
        self.row_count = row_count
        self.logger = logger_instance or logger
        self.start_time: float = 0.0
        self.duration_s: float = 0.0

    def __enter__(self) -> TimedStep:
        self.start_time = time.perf_counter()
        self.logger.info("Iniciando etapa: %s", self.name, extra={"step": self.name, "status": "started"})
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self.duration_s = time.perf_counter() - self.start_time
        duration_ms = round(self.duration_s * 1000, 2)

        extra_info: dict[str, Any] = {
            "step": self.name,
            "duration_s": round(self.duration_s, 4),
            "duration_ms": duration_ms,
        }
        if self.row_count is not None:
            extra_info["row_count"] = self.row_count

        if exc_type is not None:
            self.logger.error(
                "Etapa falhou: %s após %.3fs",
                self.name,
                self.duration_s,
                extra={**extra_info, "status": "failed"},
            )
            return

        rows_info = f" ({self.row_count:,} linhas)" if self.row_count is not None else ""
        self.logger.info(
            "Etapa concluída: %s em %.3fs%s",
            self.name,
            self.duration_s,
            rows_info,
            extra={**extra_info, "status": "completed"},
        )

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with self:
                return func(*args, **kwargs)

        return wrapper


def timed_step(
    name: str,
    row_count: int | None = None,
    logger_instance: logging.Logger | None = None,
) -> TimedStep:
    """Cria um monitor de tempo utilizável como context manager ou decorator."""
    return TimedStep(name=name, row_count=row_count, logger_instance=logger_instance)
