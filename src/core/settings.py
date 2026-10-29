from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.paths import get_data_dir, get_duckdb_path
from src.core.types import AzureSqlAuth, DataBackend, Environment


class Settings(BaseSettings):
    """Configurações globais tipadas da plataforma Kyberna."""

    env: Environment = Field(default="dev", description="Ambiente de execução")
    data_backend: DataBackend = Field(
        default="auto", description="Mecanismo de dados: auto, azure_sql ou duckdb"
    )

    data_dir: Path = Field(default_factory=get_data_dir, description="Diretório base de dados local")
    duckdb_path: Path = Field(default_factory=get_duckdb_path, description="Caminho do banco local DuckDB")

    lake_uri: str | None = Field(
        default=None, description="URI do Azure Data Lake Storage Gen2 (ex: abfss://...)"
    )

    # Azure SQL Database (Free Tier Serverless)
    azure_sql_server: str | None = Field(default=None, description="FQDN do Azure SQL Server")
    azure_sql_database: str | None = Field(default=None, description="Nome da base Azure SQL")
    azure_sql_auth: AzureSqlAuth = Field(
        default="token", description="Tipo de autenticação: token (Entra ID) ou sql"
    )
    azure_sql_connect_timeout_s: int = Field(
        default=8, ge=1, le=60, description="Timeout curto em segundos para auto-fallback"
    )
    azure_sql_user: str | None = Field(default=None, description="Usuário SQL (dev local apenas)")
    azure_sql_password: str | None = Field(default=None, description="Senha SQL (dev local apenas)")

    # Ingestão Socrata
    socrata_app_token: str | None = Field(default=None, description="App Token da API Socrata")

    # Regras de Negócio e Demonstração
    reference_date: date | None = Field(
        default=None, description="Data âncora da demonstração (padrão: ontem)"
    )
    app_password: str = Field(default="kyberna2026", description="Senha de acesso ao App comercial")

    model_config = SettingsConfigDict(
        env_prefix="KYBERNA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("reference_date", mode="before")
    @classmethod
    def default_reference_date(cls, value: date | str | None) -> date:
        """Se nenhuma data for especificada, calcula o padrão como o dia de ontem."""
        if value is None or value == "":
            return date.today() - timedelta(days=1)
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value

    @property
    def effective_reference_date(self) -> date:
        """Retorna a data âncora garantida (ontem se não configurada)."""
        return self.reference_date or (date.today() - timedelta(days=1))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna instância singleton em cache das configurações."""
    return Settings()
