"""
Configuração da conexão com o banco de dados (PostgreSQL) via SQLAlchemy.

Este módulo define:
- O "engine" (motor de conexão com o banco)
- A fábrica de sessões (SessionLocal), usada para criar uma sessão por requisição
- A classe Base, da qual todos os modelos (tabelas) devem herdar
- A função get_db, usada como dependency do FastAPI para injetar uma sessão
  de banco em cada endpoint que precisar
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

# O engine gerencia o pool de conexões com o PostgreSQL.
# pool_pre_ping=True faz uma verificação rápida antes de cada uso da conexão,
# evitando erros quando a conexão fica ociosa por muito tempo e o banco a encerra.
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

# Cada instância de SessionLocal() é uma "conversa" individual com o banco.
# autocommit=False e autoflush=False são os valores recomendados para uso
# com FastAPI, dando controle explícito sobre quando salvar (commit).
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Toda classe de modelo (tabela) do projeto herda de Base.
Base = declarative_base()


def get_db():
    """
    Dependency do FastAPI: abre uma sessão de banco para a requisição atual,
    entrega essa sessão para o endpoint usar, e garante o fechamento da
    conexão ao final — mesmo que ocorra um erro no meio do caminho.

    Uso em um endpoint:
        @app.get("/produtos")
        def listar_produtos(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
