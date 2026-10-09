"""
Testa o check constraint ck_usuario_tipo_vs_loja_central.

Verifica 4 casos:
  [INVÁLIDO 1] operador_loja com loja_id=NULL  → deve falhar
  [INVÁLIDO 2] gestor_central com loja_id preenchido → deve falhar
  [VÁLIDO 1]   operador_loja com loja_id preenchido e central_producao_id=NULL → deve passar
  [VÁLIDO 2]   gestor_central com loja_id=NULL e central_producao_id preenchido → deve passar

Uso: python scripts/test_constraint_usuario.py
"""

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

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def _limpar(db, negocio_id):
    """Remove dados criados por este teste para não deixar resíduos."""
    db.query(Usuario).filter(Usuario.negocio_id == negocio_id).delete()
    db.query(Loja).filter(Loja.negocio_id == negocio_id).delete()
    db.query(CentralProducao).filter(CentralProducao.negocio_id == negocio_id).delete()
    db.query(Negocio).filter(Negocio.id == negocio_id).delete()
    db.commit()


def main():
    db = SessionLocal()
    try:
        # --- Setup: cria negócio, central e loja de teste ---
        run_id = uuid.uuid4().hex[:8]
        negocio = Negocio(nome=f"_Teste Constraint {run_id}", ativo=True)
        db.add(negocio)
        db.flush()

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

        resultados = []

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
            resultados.append(f"{PASS} INVÁLIDO 1 (operador_loja sem loja_id): constraint violada corretamente → {type(e).__name__}")
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
            resultados.append(f"{PASS} INVÁLIDO 2 (gestor_central com loja_id): constraint violada corretamente → {type(e).__name__}")
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
            resultados.append(f"{FAIL} VÁLIDO 1 (operador_loja correto): falhou inesperadamente → {e}")
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
            resultados.append(f"{FAIL} VÁLIDO 2 (gestor_central correto): falhou inesperadamente → {e}")
        finally:
            db5.close()

    finally:
        print("\n=== Resultado do teste de constraint ===")
        for r in resultados:
            print(r)
        falhas = [r for r in resultados if r.startswith("❌")]
        print(f"\n{'TODOS OS CASOS PASSARAM' if not falhas else f'{len(falhas)} CASO(S) FALHARAM'}")
        # Limpeza dos dados de teste
        try:
            _limpar(db, negocio.id)
        except Exception as e:
            print(f"[aviso] Erro na limpeza: {e}")
        db.close()


if __name__ == "__main__":
    main()
