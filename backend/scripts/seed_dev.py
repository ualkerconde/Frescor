"""
Script para criar dados de teste: um negócio, uma central de produção,
uma loja vinculada à central, e um usuário operador de loja.

Use isto para conseguir testar o login (POST /auth/login) sem precisar
ainda das telas administrativas do software web.

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

EMAIL_TESTE = "admin@teste.com"
SENHA_TESTE = "senha123"


def main():
    db = SessionLocal()
    try:
        usuario_existente = db.query(Usuario).filter(Usuario.email == EMAIL_TESTE).first()
        if usuario_existente:
            print(f"Usuário de teste '{EMAIL_TESTE}' já existe (id={usuario_existente.id}). Nada a fazer.")
            return

        negocio = Negocio(nome="Rede Padaria Teste", ativo=True)
        db.add(negocio)
        db.flush()  # garante que negocio.id já está disponível

        central = CentralProducao(
            negocio_id=negocio.id,
            nome="Central de Produção Teste",
            ativa=True,
        )
        db.add(central)
        db.flush()  # garante que central.id já está disponível

        loja = Loja(
            negocio_id=negocio.id,
            central_producao_id=central.id,
            nome="Loja Centro",
            horario_zeragem=time(6, 0),
            ativo=True,
        )
        db.add(loja)
        db.flush()  # garante que loja.id já está disponível

        usuario = Usuario(
            negocio_id=negocio.id,
            loja_id=loja.id,
            tipo_usuario=TipoUsuario.OPERADOR_LOJA,
            nome="Administrador Teste",
            email=EMAIL_TESTE,
            senha_hash=hash_senha(SENHA_TESTE),
            status=StatusUsuario.ATIVO,
            tem_acesso_app=True,
        )
        db.add(usuario)

        db.commit()

        print("Dados de teste criados com sucesso:")
        print(f"  Negócio: {negocio.nome} (id={negocio.id})")
        print(f"  Central: {central.nome} (id={central.id})")
        print(f"  Loja:    {loja.nome} (id={loja.id})")
        print(f"  Usuário: {usuario.email} (id={usuario.id})")
        print(f"  Senha:   {SENHA_TESTE}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

