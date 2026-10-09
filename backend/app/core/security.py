"""
Funções centrais de segurança: hash de senha e geração/validação de tokens JWT.

Este módulo não conhece nada sobre banco de dados ou FastAPI — ele só sabe
fazer duas coisas, de forma isolada e testável:
1. Transformar senha em hash seguro, e confirmar se uma senha bate com um hash.
2. Criar e decodificar tokens JWT (access token e refresh token).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# CryptContext gerencia o algoritmo de hash de senha. bcrypt é o padrão
# recomendado: é lento de propósito (dificulta ataques de força bruta) e
# amplamente testado em produção.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_senha(senha_pura: str) -> str:
    """Transforma uma senha em texto puro em um hash seguro para salvar no banco."""
    return pwd_context.hash(senha_pura)


def verificar_senha(senha_pura: str, senha_hash: str) -> bool:
    """Confirma se a senha digitada corresponde ao hash salvo no banco."""
    return pwd_context.verify(senha_pura, senha_hash)


def _criar_token(dados: dict[str, Any], expira_em: timedelta, tipo: str) -> str:
    """
    Função interna que monta e assina um token JWT.

    `tipo` diferencia um access token de um refresh token dentro do próprio
    token (campo "tipo"), para que um refresh token não possa ser usado
    indevidamente como access token, e vice-versa.
    """
    agora = datetime.now(timezone.utc)
    payload = {
        **dados,
        "tipo": tipo,
        "iat": agora,  # issued at: quando o token foi criado
        "exp": agora + expira_em,  # expiration: quando o token deixa de ser válido
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def criar_access_token(usuario_id: int, negocio_id: int) -> str:
    """
    Cria um access token de vida curta.

    Carrega dentro de si o usuario_id e o negocio_id — são esses dois valores
    que o restante da API vai extrair do token para aplicar o isolamento
    multiempresa (nunca confiando em valores enviados pelo cliente).
    """
    return _criar_token(
        dados={"sub": str(usuario_id), "negocio_id": negocio_id},
        expira_em=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        tipo="access",
    )


def criar_refresh_token(usuario_id: int, negocio_id: int) -> str:
    """Cria um refresh token de vida longa (30 dias por padrão), usado só para
    obter um novo access token sem pedir senha novamente."""
    return _criar_token(
        dados={"sub": str(usuario_id), "negocio_id": negocio_id},
        expira_em=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        tipo="refresh",
    )


def decodificar_token(token: str) -> dict[str, Any]:
    """
    Decodifica e valida um token JWT (assinatura e expiração).

    Levanta jose.JWTError se o token for inválido, malformado, ou tiver
    expirado — quem chama esta função deve tratar esse erro e responder
    com 401 (não autenticado).
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
