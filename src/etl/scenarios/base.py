from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

    from src.core.scenarios import ScenarioConfig


class ScenarioBuilder(ABC):
    """Classe base abstrata para transformadores e construtores de cenários Gold.

    Cada cenário (C1 Brinquedos, C2 Bebidas, C3 Rede, C4 PDV) implementa sua própria
    subclasse derivando desta base, definindo regras taxonômicas, remapeamento de fatos
    e materialização do star schema e marts analíticos.
    """

    def __init__(self, config: ScenarioConfig, duckdb_path: Path | None = None) -> None:
        """Inicializa o builder com a configuração tipada do cenário e catálogo DuckDB.

        Args:
            config: Configuração do cenário validada via ScenarioConfig.
            duckdb_path: Caminho opcional do arquivo kyberna.duckdb.
        """
        self.config = config
        self.duckdb_path = duckdb_path

    @abstractmethod
    def build(self, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        """Executa o pipeline de remapeamento e materializa as tabelas Gold no DuckDB.

        Args:
            con: Conexão ativa com o banco DuckDB.

        Returns:
            Dicionário com a contagem de registros gerados por tabela/mart.
        """
        ...
