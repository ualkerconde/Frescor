"""
Troca da própria senha (operador no app, gestor no SaaS).

Por que existe: o script de implantação (scripts/implantar_cliente.py) cria
cada usuário com uma senha provisória aleatória; sem troca, ela ficaria
para sempre e passaria de mão em mão.

Regras:
- exige a senha atual (quem pegou o celular desbloqueado não troca a senha
  sem saber a de agora);
- senha nova com 8 a 128 caracteres, diferente da atual, não pode ser só
  espaços;
- só o próprio usuário troca a própria senha (o id vem do token, nunca do
  corpo). Redefinir a senha de outra pessoa ("esqueci a senha") ainda não
  existe: hoje é pelo script/banco.

Limitação conhecida: os tokens JWT já emitidos continuam valendo até
expirar (access 60 min, refresh 30 dias); trocar a senha não derruba as
outras sessões. Fechar isso exige guardar a hora da troca e conferir no
token (mudança em app/core/dependencies.py), que fica para depois do piloto.
"""

from sqlalchemy.orm import Session

from app.core.security import hash_senha, verificar_senha
from app.models.usuario import Usuario

TAMANHO_MINIMO = 8
TAMANHO_MAXIMO = 128


class SenhaInvalida(Exception):
    """Mensagem pronta para o usuário (português)."""


class SenhaAtualIncorreta(SenhaInvalida):
    pass


def trocar_senha(db: Session, usuario: Usuario, senha_atual: str, senha_nova: str) -> None:
    if not verificar_senha(senha_atual, usuario.senha_hash):
        raise SenhaAtualIncorreta("A senha atual não confere.")
    if not senha_nova.strip():
        raise SenhaInvalida("A senha nova não pode ficar em branco.")
    if len(senha_nova) < TAMANHO_MINIMO:
        raise SenhaInvalida(f"A senha nova precisa ter pelo menos {TAMANHO_MINIMO} caracteres.")
    if len(senha_nova) > TAMANHO_MAXIMO:
        raise SenhaInvalida(f"A senha nova pode ter no máximo {TAMANHO_MAXIMO} caracteres.")
    if senha_nova == senha_atual:
        raise SenhaInvalida("A senha nova tem de ser diferente da atual.")
    usuario.senha_hash = hash_senha(senha_nova)
    db.commit()
