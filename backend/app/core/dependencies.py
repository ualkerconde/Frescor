"""
Dependency central de autenticação e isolamento multiempresa.

ESTE É O ARQUIVO MAIS IMPORTANTE DO PROJETO EM TERMOS DE SEGURANÇA.

Regra de ouro (ver especificação, seção 3): o negocio_id usado em qualquer
operação da API NUNCA pode vir de um parâmetro enviado pelo cliente (query
param, body, header arbitrário). Ele deve ser sempre derivado do token JWT
validado, que foi emitido pela própria API no momento do login — ou seja,
o cliente não tem como escolher ou falsificar de qual negócio ele "é".

Todo endpoint que precisar saber "quem está logado" e "de qual negócio"
declara uma dependência deste módulo (ver exemplos de uso no final do
arquivo), e nunca implementa essa extração de forma duplicada ou manual.
"""

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decodificar_token
from app.db.session import get_db
from app.models.central_producao import CentralProducao
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario

# HTTPBearer faz o Swagger mostrar um único campo de texto simples no botão
# "Authorize" (em vez do formulário de username/password do OAuth2, que não
# se aplica ao nosso fluxo de login por e-mail/senha em JSON). Cole aqui
# apenas o valor do access_token, sem a palavra "Bearer" na frente — o
# Swagger já adiciona esse prefixo automaticamente no header.
bearer_scheme = HTTPBearer()

# Esquema do SaaS web. auto_error=False porque, no FastAPI 0.115, o
# HTTPBearer padrão responde 403 quando o header Authorization falta; no
# SaaS, token ausente deve ser 401 (não autenticado), e 403 fica reservado
# para "autenticado, mas sem permissão". O bearer_scheme do app mobile não
# foi alterado para não mudar o comportamento que o app já conhece.
bearer_scheme_web = HTTPBearer(auto_error=False)


@dataclass
class UsuarioAutenticado:
    """
    Representa "quem está fazendo esta requisição", já validado.

    Esta classe é o único lugar de onde o restante do código deve ler
    usuario_id, negocio_id e loja_id — nunca de um parâmetro da requisição.
    """
    usuario_id: int
    negocio_id: int
    # None para gestores de central (tipo_usuario = gestor_central).
    loja_id: Optional[int]


@dataclass
class GestorCentralAutenticado:
    """
    Identidade de um gestor de central autenticado no SaaS web.

    Único lugar de onde os endpoints do SaaS devem ler negocio_id e
    central_producao_id — nunca de um parâmetro da requisição.
    """
    usuario_id: int
    negocio_id: int
    central_producao_id: int


def _credenciais_invalidas() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _carregar_usuario_do_token(token: str, db: Session) -> Usuario:
    """
    Valida o access token e devolve o usuário atual do banco.

    Comum às duas portas de entrada (app e SaaS). Levanta 401 se o token
    for inválido, expirado, não for um access token ou apontar para um
    usuário que não existe mais. Não verifica status nem permissões: isso
    é responsabilidade de cada dependency, porque as regras diferem.
    """
    try:
        payload = decodificar_token(token)
    except JWTError:
        raise _credenciais_invalidas()

    if payload.get("tipo") != "access":
        raise _credenciais_invalidas()

    usuario_id_str = payload.get("sub")
    if usuario_id_str is None:
        raise _credenciais_invalidas()

    usuario = db.get(Usuario, int(usuario_id_str))

    if usuario is None:
        raise _credenciais_invalidas()

    return usuario


def obter_usuario_autenticado(
    credenciais: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UsuarioAutenticado:
    """
    Dependency principal: valida o access token e devolve a identidade
    autenticada (usuario_id + negocio_id + loja_id) para o endpoint usar.

    Fluxo de validação, em ordem:
    1. O token é decodificado e a assinatura/expiração são verificadas.
    2. Confirma que é um access token (não um refresh token sendo usado
       indevidamente como se fosse um access token).
    3. Busca o usuário no banco e confirma que ele ainda existe, está
       ativo, e continua com permissão de acesso ao app.
    4. Devolve negocio_id e loja_id a partir do registro atual do usuário
       no banco (não apenas do que estava gravado no token), para que uma
       eventual revogação de acesso ou troca de loja feita pelo admin
       tenha efeito imediato.
    """
    usuario = _carregar_usuario_do_token(credenciais.credentials, db)

    if usuario.status != StatusUsuario.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário bloqueado ou inativo.",
        )

    if not usuario.tem_acesso_app:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu usuário não tem permissão para acessar o app. Fale com o administrador.",
        )

    # negocio_id e loja_id vêm do registro atual do usuário no banco, não
    # do token. Isso é intencional: garante que o isolamento multiempresa
    # (e a troca de loja de um usuário, se o admin fizer isso) reflita o
    # estado mais atual possível, mesmo dentro da validade do access token.
    return UsuarioAutenticado(
        usuario_id=usuario.id,
        negocio_id=usuario.negocio_id,
        loja_id=usuario.loja_id,
    )


def obter_gestor_central(
    credenciais: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme_web),
    db: Session = Depends(get_db),
) -> GestorCentralAutenticado:
    """
    Dependency do SaaS web: aceita só gestor de central ativo e com acesso
    ao SaaS (decisão D1 em docs/STATUS.md).

    Independe de tem_acesso_app: o acesso ao app mobile e ao SaaS são
    controlados por flags separadas.

    Respostas:
    - 401: token ausente, inválido, expirado, ou de usuário inexistente.
    - 403: usuário autenticado, mas bloqueado, sem tem_acesso_web, que não
      é gestor_central, ou cuja central não pertence ao seu negócio.

    negocio_id e central_producao_id vêm do registro atual do usuário no
    banco (não do token nem da requisição), para que uma revogação feita
    pelo admin tenha efeito imediato.
    """
    if credenciais is None or credenciais.scheme.lower() != "bearer":
        raise _credenciais_invalidas()

    usuario = _carregar_usuario_do_token(credenciais.credentials, db)

    if usuario.status != StatusUsuario.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário bloqueado ou inativo.",
        )

    if not usuario.tem_acesso_web:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu usuário não tem permissão para acessar o sistema web. Fale com o administrador.",
        )

    if usuario.tipo_usuario != TipoUsuario.GESTOR_CENTRAL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a gestores de central de produção.",
        )

    # O check constraint ck_usuario_tipo_vs_loja_central já garante central
    # preenchida para gestor_central, mas nada no banco garante que a
    # central é do mesmo negócio do usuário. Conferimos aqui porque um
    # vínculo cruzado vazaria dados de outro cliente.
    central = (
        db.get(CentralProducao, usuario.central_producao_id)
        if usuario.central_producao_id is not None
        else None
    )
    if central is None or central.negocio_id != usuario.negocio_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu usuário não está vinculado a uma central de produção válida. Fale com o administrador.",
        )

    return GestorCentralAutenticado(
        usuario_id=usuario.id,
        negocio_id=usuario.negocio_id,
        central_producao_id=usuario.central_producao_id,
    )


# -----------------------------------------------------------------------
# EXEMPLO DE USO em um endpoint futuro (não é executado aqui, é só referência):
#
#   from app.core.dependencies import obter_usuario_autenticado, UsuarioAutenticado
#
#   @router.get("/produtos")
#   def listar_produtos(
#       db: Session = Depends(get_db),
#       atual: UsuarioAutenticado = Depends(obter_usuario_autenticado),
#   ):
#       return (
#           db.query(Produto)
#           .join(ProdutoLoja, ProdutoLoja.produto_id == Produto.id)
#           .filter(ProdutoLoja.loja_id == atual.loja_id)
#           .all()
#       )
#
# Note que o endpoint NUNCA recebe negocio_id ou loja_id como parâmetro da
# rota, da query string ou do corpo da requisição — eles sempre vêm de
# "atual".
# -----------------------------------------------------------------------
