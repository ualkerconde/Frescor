"""
Script para criar dados de teste da Fase 1: um negócio, uma central de
produção, duas lojas vinculadas a ela, um usuário operador por loja e um
usuário gestor da central.

Use isto para testar o login do app (POST /auth/login) e, no SaaS, as
dependencies do gestor de central, sem precisar ainda das telas
administrativas do software web.

Idempotente: pode rodar quantas vezes quiser. Cada registro é procurado
antes de ser criado (negócio pelo nome, central pela primeira do negócio,
loja pelo nome dentro do negócio, usuário pelo e-mail). As flags de acesso
dos usuários são reaplicadas a cada execução, para que uma flag nova
(ex.: tem_acesso_web, migration 0014) chegue também aos usuários que já
existiam.

Como rodar (com o ambiente virtual ativado, na raiz do projeto backend/):
    python scripts/seed_dev.py

Pode editar as constantes abaixo antes de rodar, se quiser.
"""

import sys
from datetime import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.security import hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402

NOME_NEGOCIO = "Rede Padaria Teste"
NOME_CENTRAL = "Central de Produção Teste"
SENHA_TESTE = "senha123"

# Uma entrada por loja, cada uma com seu operador. A primeira mantém o
# usuário histórico admin@teste.com, já usado para testar o app mobile.
LOJAS = [
    {"nome": "Loja Centro", "operador_email": "admin@teste.com", "operador_nome": "Administrador Teste"},
    {"nome": "Loja Bairro", "operador_email": "operador.bairro@teste.com", "operador_nome": "Operador Loja Bairro"},
]

# Gestor da central: não tem loja, não usa o app mobile e entra no SaaS web.
GESTOR = {
    "email": "gestor@teste.com",
    "nome": "Gestor Central Teste",
    "flags": {"tem_acesso_app": False, "tem_acesso_web": True},
}


def _obter_ou_criar_negocio(db):
    negocio = db.query(Negocio).filter(Negocio.nome == NOME_NEGOCIO).order_by(Negocio.id).first()
    if negocio:
        return negocio, False
    negocio = Negocio(nome=NOME_NEGOCIO, ativo=True)
    db.add(negocio)
    db.flush()
    return negocio, True


def _obter_ou_criar_central(db, negocio):
    # Reaproveita qualquer central já existente do negócio, em vez de buscar
    # pelo nome: a migration 0008 criou centrais padrão com outro nome para
    # as lojas que já existiam, e buscar pelo nome criaria uma segunda.
    central = (
        db.query(CentralProducao)
        .filter(CentralProducao.negocio_id == negocio.id)
        .order_by(CentralProducao.id)
        .first()
    )
    if central:
        return central, False
    central = CentralProducao(negocio_id=negocio.id, nome=NOME_CENTRAL, ativa=True)
    db.add(central)
    db.flush()
    return central, True


def _obter_ou_criar_loja(db, negocio, central, nome):
    loja = db.query(Loja).filter(Loja.negocio_id == negocio.id, Loja.nome == nome).first()
    if loja:
        return loja, False
    loja = Loja(
        negocio_id=negocio.id,
        central_producao_id=central.id,
        nome=nome,
        horario_zeragem=time(6, 0),
        ativo=True,
    )
    db.add(loja)
    db.flush()
    return loja, True


def _obter_ou_criar_usuario(db, negocio, email, nome, tipo, flags, loja_id=None, central_producao_id=None):
    """
    Cria o usuário se não existir. Se existir, só reaplica as flags de
    acesso (não mexe em senha, nome nem vínculos de quem já existe).
    Devolve (usuario, situacao), situacao em "criado", "atualizado" ou "existente".
    """
    usuario = db.query(Usuario).filter(Usuario.email == email).first()
    if usuario is None:
        usuario = Usuario(
            negocio_id=negocio.id,
            tipo_usuario=tipo,
            loja_id=loja_id,
            central_producao_id=central_producao_id,
            nome=nome,
            email=email,
            senha_hash=hash_senha(SENHA_TESTE),
            status=StatusUsuario.ATIVO,
            **flags,
        )
        db.add(usuario)
        db.flush()
        return usuario, "criado"

    alterado = False
    for campo, valor in flags.items():
        if getattr(usuario, campo) != valor:
            setattr(usuario, campo, valor)
            alterado = True
    return usuario, "atualizado" if alterado else "existente"


def main():
    db = SessionLocal()
    try:
        negocio, criado = _obter_ou_criar_negocio(db)
        print(f"Negócio: {negocio.nome} (id={negocio.id}) [{'criado' if criado else 'existente'}]")

        central, criado = _obter_ou_criar_central(db, negocio)
        print(f"Central: {central.nome} (id={central.id}) [{'criado' if criado else 'existente'}]")

        for item in LOJAS:
            loja, criado = _obter_ou_criar_loja(db, negocio, central, item["nome"])
            print(
                f"Loja:    {loja.nome} (id={loja.id}, central_producao_id={loja.central_producao_id}) "
                f"[{'criado' if criado else 'existente'}]"
            )
            usuario, situacao = _obter_ou_criar_usuario(
                db,
                negocio,
                email=item["operador_email"],
                nome=item["operador_nome"],
                tipo=TipoUsuario.OPERADOR_LOJA,
                flags={"tem_acesso_app": True},
                loja_id=loja.id,
            )
            print(f"  Operador: {usuario.email} (id={usuario.id}, loja_id={usuario.loja_id}) [{situacao}]")

        gestor, situacao = _obter_ou_criar_usuario(
            db,
            negocio,
            email=GESTOR["email"],
            nome=GESTOR["nome"],
            tipo=TipoUsuario.GESTOR_CENTRAL,
            flags=GESTOR["flags"],
            central_producao_id=central.id,
        )
        print(
            f"Gestor:  {gestor.email} (id={gestor.id}, central_producao_id={gestor.central_producao_id}) "
            f"[{situacao}]"
        )

        db.commit()
        print(f"Senha dos usuários criados agora: {SENHA_TESTE}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
