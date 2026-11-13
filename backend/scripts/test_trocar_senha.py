"""
Testa a troca da própria senha: POST /auth/senha (app) e POST /auth/web/senha (SaaS).

Casos:
  S1 app: operador troca (204), entra com a nova e não entra mais com a antiga
  S2 app: senha atual errada -> 400 e a senha não muda
  S3 regras: nova curta (< 8), igual à atual, só espaços -> 400
  S4 sem token -> 401/403; token do SaaS na rota do app -> 401
  S5 web: gestor troca (204) e entra no SaaS com a nova
  S6 isolamento: a troca de um usuário não mexe na senha de outro
  S7 gestor com token do app (não tem) / operador com token do app na rota web -> 401

Uso: python scripts/test_trocar_senha.py
"""

import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import hash_senha, verificar_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402

PREFIXO = "TESTE_SENHA"
cliente = TestClient(app)
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{'[OK]' if ok else '[FALHA]'} {nome}: {detalhe}")


def limpar(db):
    ids = [n.id for n in db.query(Negocio).filter(Negocio.nome.like(f"{PREFIXO} %"))]
    if ids:
        db.query(Usuario).filter(Usuario.negocio_id.in_(ids)).delete(synchronize_session=False)
        db.query(Loja).filter(Loja.negocio_id.in_(ids)).delete(synchronize_session=False)
        db.query(CentralProducao).filter(CentralProducao.negocio_id.in_(ids)).delete(synchronize_session=False)
        db.query(Negocio).filter(Negocio.id.in_(ids)).delete(synchronize_session=False)
        db.commit()


def login(rota, email, senha):
    return cliente.post(rota, json={"email": email, "senha": senha})


def trocar(rota, token, atual, nova):
    cab = {"Authorization": f"Bearer {token}"} if token else {}
    return cliente.post(rota, json={"senha_atual": atual, "senha_nova": nova}, headers=cab)


def main():
    db = SessionLocal()
    limpar(db)
    run = uuid.uuid4().hex[:8]
    try:
        neg = Negocio(nome=f"{PREFIXO} {run}", ativo=True)
        db.add(neg)
        db.flush()
        central = CentralProducao(negocio_id=neg.id, nome="Central", ativa=True)
        db.add(central)
        db.flush()
        loja = Loja(negocio_id=neg.id, central_producao_id=central.id, nome="Loja", codigo="S1", ativo=True)
        db.add(loja)
        db.flush()
        comum = dict(negocio_id=neg.id, senha_hash=hash_senha("antiga123"), status=StatusUsuario.ATIVO)
        op = Usuario(tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=loja.id, nome="Op", email=f"op.{run}@t.com",
                     tem_acesso_app=True, tem_acesso_web=False, **comum)
        op2 = Usuario(tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=loja.id, nome="Op2", email=f"op2.{run}@t.com",
                      tem_acesso_app=True, tem_acesso_web=False, **comum)
        ges = Usuario(tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=central.id, nome="Ges",
                      email=f"ges.{run}@t.com", tem_acesso_app=False, tem_acesso_web=True, **comum)
        db.add_all([op, op2, ges])
        db.commit()

        tok_op = login("/auth/login", op.email, "antiga123").json()["access_token"]
        tok_ges = login("/auth/web/login", ges.email, "antiga123").json()["access_token"]

        r = trocar("/auth/senha", tok_op, "antiga123", "novasenha1")
        ok = (r.status_code == 204 and login("/auth/login", op.email, "novasenha1").status_code == 200
              and login("/auth/login", op.email, "antiga123").status_code == 401)
        registrar("S1 app troca", ok, f"{r.status_code}")

        r = trocar("/auth/senha", tok_op, "errada999", "outrasenha2")
        ok = r.status_code == 400 and "atual" in r.json()["detail"] and login("/auth/login", op.email, "novasenha1").status_code == 200
        registrar("S2 senha atual errada", ok, f"{r.status_code} {r.json().get('detail')}")

        respostas = [trocar("/auth/senha", tok_op, "novasenha1", nova) for nova in ("curta", "novasenha1", "         ")]
        registrar("S3 regras da senha nova", all(x.status_code == 400 for x in respostas),
                  " | ".join(f"{x.status_code} {x.json().get('detail')}" for x in respostas))

        sem = trocar("/auth/senha", None, "novasenha1", "outrasenha2")
        cruz = trocar("/auth/senha", tok_ges, "antiga123", "outrasenha2")
        registrar("S4 sem token e token do SaaS no app", sem.status_code in (401, 403) and cruz.status_code == 401,
                  f"sem token {sem.status_code}, token web {cruz.status_code}")

        r = trocar("/auth/web/senha", tok_ges, "antiga123", "gestorsenha9")
        registrar("S5 web troca", r.status_code == 204 and login("/auth/web/login", ges.email, "gestorsenha9").status_code == 200,
                  f"{r.status_code}")

        db.expire_all()
        registrar("S6 outro usuario intacto", verificar_senha("antiga123", db.get(Usuario, op2.id).senha_hash), "op2 com a antiga")

        cruz = trocar("/auth/web/senha", tok_op, "novasenha1", "outrasenha2")
        registrar("S7 token do app na rota web", cruz.status_code == 401, f"{cruz.status_code}")
    except Exception as e:  # noqa: BLE001
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        db.rollback()
        limpar(db)
        db.close()

    print()
    for r in resultados:
        print(r)
    falhas = [r for r in resultados if r.startswith("[FALHA]")]
    print()
    print(f"{len(falhas)} CASO(S) FALHARAM" if falhas else "TODOS OS CASOS PASSARAM")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
