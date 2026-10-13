"""
Testa o check constraint ck_usuario_tipo_vs_loja_central.

Verifica 4 casos:
  [INVÁLIDO 1] operador_loja com loja_id=NULL  → deve falhar
  [INVÁLIDO 2] gestor_central com loja_id preenchido → deve falhar
  [VÁLIDO 1]   operador_loja com loja_id preenchido e central_producao_id=NULL → deve passar
  [VÁLIDO 2]   gestor_central com loja_id=NULL e central_producao_id preenchido → deve passar

Uso: python scripts/test_constraint_usuario.py

Saída só com caracteres que o console do Windows (cp1252) imprime:
[OK]/[FALHA] e "->" em vez de emojis e setas. Um erro de impressão já
deixou dados de teste sobrando no banco; por isso o script também apaga
resíduos de execuções anteriores logo no início.
"""

import re
import sys
from datetime import time
from pathlib import Path
import uuid

sys.path.append(str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_senha
from app.db.session import SessionLocal
from app.models.central_producao import CentralProducao
from app.models.loja import Loja
from app.models.negocio import Negocio
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario

PASS = "[OK]"
FAIL = "[FALHA]"

# Identificação dos dados criados por este teste. O nome sem sufixo vem de
# uma versão antiga do script, que não usava run_id.
PREFIXO_NEGOCIO_TESTE = "_Teste Constraint"
EMAIL_TESTE = re.compile(r"^(in)?valido[12](_[0-9a-f]{8})?@teste[.]com$")


def _limpar(db, negocio_id):
    """Remove dados criados por este teste para não deixar resíduos."""
    db.query(Usuario).filter(Usuario.negocio_id == negocio_id).delete()
    db.query(Loja).filter(Loja.negocio_id == negocio_id).delete()
    db.query(CentralProducao).filter(CentralProducao.negocio_id == negocio_id).delete()
    db.query(Negocio).filter(Negocio.id == negocio_id).delete()
    db.commit()


def _limpar_residuos():
    """
    Apaga dados de teste deixados por execuções anteriores que quebraram
    antes da limpeza. Mostra o que encontrou antes de apagar.
    """
    db = SessionLocal()
    try:
        negocios = [
            n for n in db.query(Negocio).all()
            if n.nome == PREFIXO_NEGOCIO_TESTE or n.nome.startswith(PREFIXO_NEGOCIO_TESTE + " ")
        ]
        negocio_ids = {n.id for n in negocios}
        usuarios_avulsos = [
            u for u in db.query(Usuario).filter(Usuario.email.like("%@teste.com")).all()
            if EMAIL_TESTE.match(u.email) and u.negocio_id not in negocio_ids
        ]

        if not negocios and not usuarios_avulsos:
            print("[limpeza inicial] Nenhum resíduo de teste encontrado.")
            return

        print("[limpeza inicial] Resíduos de execuções anteriores encontrados:")
        for n in negocios:
            emails = [u.email for u in db.query(Usuario).filter(Usuario.negocio_id == n.id)]
            print(f"  negocio id={n.id} nome={n.nome!r} usuarios={emails}")
        for u in usuarios_avulsos:
            print(f"  usuario avulso id={u.id} email={u.email!r} negocio_id={u.negocio_id}")

        for u in usuarios_avulsos:
            db.delete(u)
        db.commit()
        for n in negocios:
            _limpar(db, n.id)
        print("[limpeza inicial] Resíduos apagados.")
    finally:
        db.close()


def main():
    _limpar_residuos()

    db = SessionLocal()
    negocio_id = None
    resultados = []
    try:
        # --- Setup: cria negócio, central e loja de teste ---
        run_id = uuid.uuid4().hex[:8]
        negocio = Negocio(nome=f"_Teste Constraint {run_id}", ativo=True)
        db.add(negocio)
        db.flush()
        negocio_id = negocio.id

        central = CentralProducao(negocio_id=negocio.id, nome="_Central Teste", ativa=True)
        db.add(central)
        db.flush()

        loja = Loja(
            negocio_id=negocio.id,
            central_producao_id=central.id,
            nome="_Loja Teste",
            horario_zeragem=time(6, 0),
            ativo=True,
        )
        db.add(loja)
        db.flush()
        db.commit()

        # ---- CASO INVÁLIDO 1: operador_loja sem loja_id ----
        db2 = SessionLocal()
        try:
            u = Usuario(
                negocio_id=negocio.id,
                tipo_usuario=TipoUsuario.OPERADOR_LOJA,
                loja_id=None,           # INVÁLIDO: operador_loja precisa de loja_id
                central_producao_id=None,
                nome="Inválido 1",
                email=f"invalido1_{run_id}@teste.com",
                senha_hash=hash_senha("x"),
                status=StatusUsuario.ATIVO,
                tem_acesso_app=False,
            )
            db2.add(u)
            db2.flush()
            db2.commit()
            resultados.append(f"{FAIL} INVÁLIDO 1 (operador_loja sem loja_id): constraint NÃO foi violada — bug!")
        except (IntegrityError, sa.exc.ProgrammingError) as e:
            db2.rollback()
            resultados.append(f"{PASS} INVÁLIDO 1 (operador_loja sem loja_id): constraint violada corretamente -> {type(e).__name__}")
        finally:
            db2.close()

        # ---- CASO INVÁLIDO 2: gestor_central com loja_id preenchido ----
        db3 = SessionLocal()
        try:
            u = Usuario(
                negocio_id=negocio.id,
                tipo_usuario=TipoUsuario.GESTOR_CENTRAL,
                loja_id=loja.id,        # INVÁLIDO: gestor_central não deve ter loja_id
                central_producao_id=central.id,
                nome="Inválido 2",
                email=f"invalido2_{run_id}@teste.com",
                senha_hash=hash_senha("x"),
                status=StatusUsuario.ATIVO,
                tem_acesso_app=False,
            )
            db3.add(u)
            db3.flush()
            db3.commit()
            resultados.append(f"{FAIL} INVÁLIDO 2 (gestor_central com loja_id): constraint NÃO foi violada — bug!")
        except (IntegrityError, sa.exc.ProgrammingError) as e:
            db3.rollback()
            resultados.append(f"{PASS} INVÁLIDO 2 (gestor_central com loja_id): constraint violada corretamente -> {type(e).__name__}")
        finally:
            db3.close()

        # ---- CASO VÁLIDO 1: operador_loja com loja_id e sem central_producao_id ----
        db4 = SessionLocal()
        try:
            u = Usuario(
                negocio_id=negocio.id,
                tipo_usuario=TipoUsuario.OPERADOR_LOJA,
                loja_id=loja.id,
                central_producao_id=None,
                nome="Válido 1",
                email=f"valido1_{run_id}@teste.com",
                senha_hash=hash_senha("x"),
                status=StatusUsuario.ATIVO,
                tem_acesso_app=False,
            )
            db4.add(u)
            db4.flush()
            db4.commit()
            resultados.append(f"{PASS} VÁLIDO 1 (operador_loja correto): inserido com sucesso (id={u.id})")
        except Exception as e:
            resultados.append(f"{FAIL} VÁLIDO 1 (operador_loja correto): falhou inesperadamente -> {e}")
        finally:
            db4.close()

        # ---- CASO VÁLIDO 2: gestor_central com central_producao_id e sem loja_id ----
        db5 = SessionLocal()
        try:
            u = Usuario(
                negocio_id=negocio.id,
                tipo_usuario=TipoUsuario.GESTOR_CENTRAL,
                loja_id=None,
                central_producao_id=central.id,
                nome="Válido 2",
                email=f"valido2_{run_id}@teste.com",
                senha_hash=hash_senha("x"),
                status=StatusUsuario.ATIVO,
                tem_acesso_app=False,
            )
            db5.add(u)
            db5.flush()
            db5.commit()
            resultados.append(f"{PASS} VÁLIDO 2 (gestor_central correto): inserido com sucesso (id={u.id})")
        except Exception as e:
            resultados.append(f"{FAIL} VÁLIDO 2 (gestor_central correto): falhou inesperadamente -> {e}")
        finally:
            db5.close()

    finally:
        try:
            print("\n=== Resultado do teste de constraint ===")
            for r in resultados:
                print(r)
            falhas = [r for r in resultados if r.startswith(FAIL)]
            if len(resultados) < 4:
                print(f"\nTESTE INCOMPLETO: só {len(resultados)} de 4 casos rodaram")
            else:
                print(f"\n{'TODOS OS CASOS PASSARAM' if not falhas else f'{len(falhas)} CASO(S) FALHARAM'}")
        finally:
            # Roda mesmo que a impressão acima falhe.
            if negocio_id is not None:
                try:
                    db.rollback()
                    _limpar(db, negocio_id)
                except Exception as e:
                    print(f"[aviso] Erro na limpeza: {e}")
            db.close()

    if len(resultados) < 4 or any(r.startswith(FAIL) for r in resultados):
        sys.exit(1)


if __name__ == "__main__":
    main()
