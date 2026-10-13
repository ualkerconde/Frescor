"""
Testa o escopo do gestor de central (decisão D8: só as lojas da própria
central; loja fora do escopo -> 404). Fase 2 / P3.

Cenário de teste:
  negócio A: central A1 (do gestor) com loja A1a (ativa) e A1b (inativa);
             central A2 com loja A2
  negócio B: central B com loja B

Casos:
  S1 lojas do gestor = exatamente A1a e A1b
  S2 loja inativa da central está no escopo (comportamento atual, ver STATUS)
  S3 buscar A1a -> encontrada
  S4 buscar A2 (outra central do mesmo negócio) -> fora do escopo
  S5 buscar B (outro negócio) -> fora do escopo
  S6 buscar loja inexistente -> fora do escopo
  S7 gestor do seed (gestor@teste.com) -> lojas 001 e 002 do seed
  H1 GET de A1a pela rota -> 200
  H2 GET de A2 -> 404
  H3 GET de B -> 404
  H4 GET de loja inexistente -> 404
  H5 as três respostas 404 são idênticas (não revelam se a loja existe)
  H6 listagem pela rota -> só as lojas da central

As rotas H* existem só neste processo de teste (nenhuma rota real usa o
escopo ainda; P5/P6 vão usar). Tokens gerados direto com porta web.

Uso: python scripts/test_escopo_gestor.py
"""

import re
import sys
import uuid
from datetime import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import Depends  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.escopo import loja_no_escopo_ou_404  # noqa: E402
from app.core.dependencies import GestorCentralAutenticado, obter_gestor_central  # noqa: E402
from app.core.security import PORTA_WEB, criar_access_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402
from app.services.escopo_service import buscar_loja_no_escopo, ids_lojas_do_gestor  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 13
PREFIXO_NEGOCIO_TESTE = "_Teste Escopo"
EMAIL_TESTE = re.compile(r"^tes_[a-z_]+_[0-9a-f]{8}@teste[.]com$")
INEXISTENTE = 2_000_000_000


@app.get("/_teste/escopo/lojas")
def _rota_lojas(gestor: GestorCentralAutenticado = Depends(obter_gestor_central), db: Session = Depends(get_db)):
    return ids_lojas_do_gestor(db, gestor)


@app.get("/_teste/escopo/lojas/{loja_id}")
def _rota_loja(loja_id: int, gestor: GestorCentralAutenticado = Depends(obter_gestor_central),
               db: Session = Depends(get_db)):
    return {"id": loja_no_escopo_ou_404(db, gestor, loja_id).id}


cliente = TestClient(app)
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    db.query(Usuario).filter(Usuario.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Loja).filter(Loja.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(CentralProducao).filter(CentralProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Negocio).filter(Negocio.id.in_(negocio_ids)).delete(synchronize_session=False)
    db.commit()


def _limpar_residuos():
    db = SessionLocal()
    try:
        negocios = [n for n in db.query(Negocio).all() if n.nome.startswith(PREFIXO_NEGOCIO_TESTE + " ")]
        avulsos = [u for u in db.query(Usuario).filter(Usuario.email.like("tes_%@teste.com")).all()
                   if EMAIL_TESTE.match(u.email) and u.negocio_id not in [n.id for n in negocios]]
        if not negocios and not avulsos:
            print("[limpeza inicial] Nenhum resíduo de teste encontrado.")
            return
        print("[limpeza inicial] Resíduos de execuções anteriores encontrados:")
        for n in negocios:
            print(f"  negocio id={n.id} nome={n.nome!r}")
        for u in avulsos:
            print(f"  usuario avulso id={u.id} email={u.email!r}")
            db.delete(u)
        db.commit()
        _limpar(db, [n.id for n in negocios])
        print("[limpeza inicial] Resíduos apagados.")
    finally:
        db.close()


def main():
    _limpar_residuos()
    db = SessionLocal()
    negocio_ids = []
    try:
        run_id = uuid.uuid4().hex[:8]
        neg_a = Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run_id} A", ativo=True)
        neg_b = Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run_id} B", ativo=True)
        db.add_all([neg_a, neg_b])
        db.flush()
        negocio_ids = [neg_a.id, neg_b.id]
        c_a1 = CentralProducao(negocio_id=neg_a.id, nome="_Central A1", ativa=True)
        c_a2 = CentralProducao(negocio_id=neg_a.id, nome="_Central A2", ativa=True)
        c_b = CentralProducao(negocio_id=neg_b.id, nome="_Central B", ativa=True)
        db.add_all([c_a1, c_a2, c_b])
        db.flush()

        def loja(negocio, central, nome, ativo=True):
            lj = Loja(negocio_id=negocio.id, central_producao_id=central.id, nome=nome,
                      horario_zeragem=time(6, 0), ativo=ativo)
            db.add(lj)
            db.flush()
            return lj

        l_a1a = loja(neg_a, c_a1, "_Loja A1a")
        l_a1b = loja(neg_a, c_a1, "_Loja A1b inativa", ativo=False)
        l_a2 = loja(neg_a, c_a2, "_Loja A2")
        l_b = loja(neg_b, c_b, "_Loja B")
        gestor = Usuario(
            negocio_id=neg_a.id, tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=c_a1.id,
            nome="Teste gestor", email=f"tes_gestor_{run_id}@teste.com", senha_hash=hash_senha("x"),
            status=StatusUsuario.ATIVO, tem_acesso_app=False, tem_acesso_web=True,
        )
        db.add(gestor)
        db.commit()

        g = GestorCentralAutenticado(usuario_id=gestor.id, negocio_id=neg_a.id, central_producao_id=c_a1.id)

        # ---- serviço ----
        ids = ids_lojas_do_gestor(db, g)
        registrar("S1 lojas do gestor = so as da central A1", ids == sorted([l_a1a.id, l_a1b.id]),
                  f"obtido {ids}, esperado {sorted([l_a1a.id, l_a1b.id])} (A2={l_a2.id}, B={l_b.id} fora)")
        registrar("S2 loja inativa da central esta no escopo", l_a1b.id in ids, f"A1b (inativa) id={l_a1b.id}")
        achada = buscar_loja_no_escopo(db, g, l_a1a.id)
        registrar("S3 buscar A1a", achada is not None and achada.id == l_a1a.id, f"-> {achada.id if achada else None}")
        for nome, lid in (("S4 buscar A2 (outra central, mesmo negocio)", l_a2.id),
                          ("S5 buscar B (outro negocio)", l_b.id),
                          ("S6 buscar loja inexistente", INEXISTENTE)):
            r = buscar_loja_no_escopo(db, g, lid)
            registrar(nome, r is None, "fora do escopo" if r is None else f"DEVOLVEU a loja {r.id}")

        # S7: gestor real do seed (só leitura).
        seed = db.query(Usuario).filter(Usuario.email == "gestor@teste.com").first()
        if seed is None:
            registrar("S7 gestor do seed", False, "gestor@teste.com não existe -> rode scripts/seed_dev.py")
        else:
            g_seed = GestorCentralAutenticado(seed.id, seed.negocio_id, seed.central_producao_id)
            codigos = [lj.codigo for lj in db.query(Loja).filter(Loja.id.in_(ids_lojas_do_gestor(db, g_seed))).order_by(Loja.id)]
            registrar("S7 gestor do seed -> lojas 001 e 002", codigos == ["001", "002"], f"codigos={codigos}")

        # ---- HTTP ----
        h = {"Authorization": "Bearer " + criar_access_token(gestor.id, neg_a.id, porta=PORTA_WEB)}
        r = cliente.get(f"/_teste/escopo/lojas/{l_a1a.id}", headers=h)
        registrar("H1 GET loja A1a", r.status_code == 200 and r.json() == {"id": l_a1a.id}, f"{r.status_code} -> {r.json()}")
        respostas_404 = []
        for nome, lid in (("H2 GET loja A2 (outra central)", l_a2.id), ("H3 GET loja B (outro negocio)", l_b.id),
                          ("H4 GET loja inexistente", INEXISTENTE)):
            r = cliente.get(f"/_teste/escopo/lojas/{lid}", headers=h)
            respostas_404.append((r.status_code, r.text))
            registrar(nome, r.status_code == 404, f"{r.status_code} -> {r.json()}")
        registrar("H5 respostas 404 identicas", len(set(respostas_404)) == 1, f"{len(set(respostas_404))} resposta(s) distinta(s)")
        r = cliente.get("/_teste/escopo/lojas", headers=h)
        registrar("H6 listagem pela rota", r.status_code == 200 and r.json() == sorted([l_a1a.id, l_a1b.id]),
                  f"{r.status_code} -> {r.json()}")

    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste de escopo do gestor ===")
            for r in resultados:
                print(r)
            falhas = [r for r in resultados if r.startswith(FAIL)]
            if len(resultados) < TOTAL_CASOS:
                print(f"\nTESTE INCOMPLETO: só {len(resultados)} de {TOTAL_CASOS} casos rodaram")
            else:
                print(f"\n{'TODOS OS CASOS PASSARAM' if not falhas else f'{len(falhas)} CASO(S) FALHARAM'}")
        finally:
            try:
                db.rollback()
                _limpar(db, negocio_ids)
            except Exception as e:
                print(f"[aviso] Erro na limpeza: {e}")
            db.close()

    if len(resultados) < TOTAL_CASOS or any(r.startswith(FAIL) for r in resultados):
        sys.exit(1)


if __name__ == "__main__":
    main()
