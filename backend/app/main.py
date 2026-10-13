"""
Ponto de entrada da aplicação FastAPI.

Para rodar localmente (com o ambiente virtual já ativado):
    uvicorn app.main:app --reload

Depois, acesse:
    http://127.0.0.1:8000/docs       -> documentação interativa (Swagger)
    http://127.0.0.1:8000/api/health -> verificação de saúde da API + banco

Observação sobre o --reload e o agendador: em modo de desenvolvimento com
--reload, o Uvicorn reinicia o processo a cada alteração de arquivo, o que
reinicia o agendador também (comportamento esperado e sem problema para
desenvolvimento). Em produção, normalmente roda-se sem --reload.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, auth_web, health, produtos, zeragem
from app.core.scheduler import iniciar_agendador, parar_agendador
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Executado uma vez quando a API sobe: inicia o agendador em segundo
    # plano (verificação periódica de lojas pendentes de zeragem).
    iniciar_agendador()
    yield
    # Executado quando a API é encerrada: para o agendador de forma limpa.
    parar_agendador()


app = FastAPI(
    title="API - App de Coleta de Dados (Contagem de Estoque)",
    description="Backend que integra o app móvel (PWA) ao software web multiempresa.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.100.8:3000",
        "http://192.168.0.65:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cada novo grupo de endpoints (produtos, estoque, auth, admin...) será
# registrado aqui nas próximas etapas, seguindo este mesmo padrão.
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(auth.router, prefix="/auth", tags=["Autenticação"])
app.include_router(auth_web.router, prefix="/auth/web", tags=["Autenticação (SaaS web)"])
app.include_router(produtos.router, tags=["Produtos e Estoque"])
app.include_router(zeragem.router, tags=["Zeragem"])


@app.get("/")
def root():
    return {"mensagem": "API rodando. Acesse /docs para a documentação interativa."}
