"""
Configuração de ambiente do Alembic.

Conecta o Alembic com:
- A URL real do banco (lida do .env via app.core.config.settings)
- Todos os modelos do projeto (via app.models), para que o Alembic
  consiga detectar automaticamente as tabelas ao gerar migrações
  (comando "alembic revision --autogenerate").
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.session import Base
import app.models  # noqa: F401  (garante que todos os modelos sejam carregados)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Sobrescreve a URL do banco definida no alembic.ini com a do nosso .env,
# para manter uma única fonte de verdade sobre a conexão.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# metadata usado pelo autogenerate para comparar os modelos com o estado
# atual do banco e gerar as migrações automaticamente.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
