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
from app.models.usuario import StatusUsuario, Usuario

# HTTPBearer faz o Swagger mostrar um único campo de texto simples no botão
# "Authorize" (em vez do formulário de username/password do OAuth2, que não
# se aplica ao nosso fluxo de login por e-mail/senha em JSON). Cole aqui
# apenas o valor do access_token, sem a palavra "Bearer" na frente — o
# Swagger já adiciona esse prefixo automaticamente no header.
bearer_scheme = HTTPBearer()


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
    token = credenciais.credentials

    credenciais_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decodificar_token(token)
    except JWTError:
        raise credenciais_invalidas

    if payload.get("tipo") != "access":
        raise credenciais_invalidas

    usuario_id_str = payload.get("sub")
    if usuario_id_str is None:
        raise credenciais_invalidas

    usuario = db.get(Usuario, int(usuario_id_str))

    if usuario is None:
        raise credenciais_invalidas

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
