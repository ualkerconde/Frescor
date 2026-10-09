"""
Configurações centrais da aplicação.

Tudo que pode variar entre ambientes (desenvolvimento, produção) fica aqui,
lido a partir do arquivo .env — nunca direto no código.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Banco de dados
    DATABASE_URL: str

    # Autenticação (usado a partir da próxima etapa, já configurado agora)
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Geral
    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Instância única, importada em qualquer lugar da aplicação que precisar
# de uma configuração: "from app.core.config import settings"
settings = Settings()
