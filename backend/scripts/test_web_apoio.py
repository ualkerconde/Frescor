"""
Testa as rotas de apoio do SaaS web (frontend, passo W1):
GET /web/me, GET /web/lojas e GET /web/produtos, por HTTP com o TestClient.

Cenário:
  negócio A, central A1: lojas T01 (ativa) e T02 (inativa); central A2: loja T03
  negócio B, central B: loja TB1
Requer a migration 0017 (extensão unaccent: a busca ignora acentos).

  produtos de A: INT-1 "Pão Francês", INT-2 "Pão de Forma", CR-1 "Croissant" (inativo),
                 X-1 "Promo 100%_teste" (para testar % e _ como texto)
  produto de B: INT-1 "Pão Francês B" (mesmo código, outro negócio)
Usuários: gestor de A1, gestor de A2, gestor de B, gestor de A1 sem
tem_acesso_web, operador de loja (token do app).

Uso: python scripts/test_web_apoio.py
"""

import re
import sys
import uuid
from datetime import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import PORTA_WEB, criar_access_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
PREFIXO_NEGOCIO_TESTE = "_Teste Web Apoio"
EMAIL_TESTE = re.compile(r"^twa_[a-z_0-9]+_[0-9a-f]{8}@teste[.]com$")
ROTAS = ("/web/me", "/web/lojas", "/web/produtos")

cliente = TestClient(app)
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def get(rota, token=None, **params):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return cliente.get(rota, params=params, headers=headers)


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    db.query(Produto).filter(Produto.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Usuario).filter(Usuario.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Loja).filter(Loja.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(CentralProducao).filter(CentralProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Negocio).filter(Negocio.id.in_(negocio_ids)).delete(synchronize_session=False)
    db.commit()


def _limpar_residuos():
    db = SessionLocal()
    try:
        negocios = [n for n in db.query(Negocio).all() if n.nome.startswith(PREFIXO_NEGOCIO_TESTE + " ")]
        avulsos = [u for u in db.query(Usuario).filter(Usuario.email.like("twa_%@teste.com")).all()
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

        def loja(neg, central, codigo, ativo=True):
            lj = Loja(negocio_id=neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}", codigo=codigo,
                      horario_zeragem=time(6, 0), ativo=ativo)
            db.add(lj)
            return lj

        t01, t02 = loja(neg_a, c_a1, "T01"), loja(neg_a, c_a1, "T02", ativo=False)
        t03, tb1 = loja(neg_a, c_a2, "T03"), loja(neg_b, c_b, "TB1")

        def produto(neg, codigo, nome, un=UnidadeMedida.UN, ativo=True):
            p = Produto(negocio_id=neg.id, nome=nome, codigo=codigo, unidade_medida=un, ativo=ativo)
            db.add(p)
            return p

        produto(neg_a, "INT-1", "Pão Francês", UnidadeMedida.KG)
        produto(neg_a, "INT-2", "Pão de Forma", UnidadeMedida.KG)
        produto(neg_a, "CR-1", "Croissant", ativo=False)
        produto(neg_a, "X-1", "Promo 100%_teste")
        produto(neg_b, "INT-1", "Pão Francês B")
        db.flush()

        def usuario(rotulo, neg, **campos):
            u = Usuario(negocio_id=neg.id, nome=f"Teste {rotulo}", email=f"twa_{rotulo}_{run_id}@teste.com",
                        senha_hash=hash_senha("x"), status=StatusUsuario.ATIVO, **campos)
            db.add(u)
            db.flush()
            return u

        gest = dict(tipo_usuario=TipoUsuario.GESTOR_CENTRAL, tem_acesso_app=False)
        g_a1 = usuario("gestor_a1", neg_a, central_producao_id=c_a1.id, tem_acesso_web=True, **gest)
        g_a2 = usuario("gestor_a2", neg_a, central_producao_id=c_a2.id, tem_acesso_web=True, **gest)
        g_b = usuario("gestor_b", neg_b, central_producao_id=c_b.id, tem_acesso_web=True, **gest)
        g_sem_web = usuario("gestor_sem_web", neg_a, central_producao_id=c_a1.id, tem_acesso_web=False, **gest)
        operador = usuario("operador", neg_a, tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=t01.id,
                           tem_acesso_web=False, tem_acesso_app=True)
        db.commit()
        tk = lambda u: criar_access_token(u.id, u.negocio_id, porta=PORTA_WEB)  # noqa: E731
        ta1 = tk(g_a1)

        # ---------------- autenticação (as três rotas) ----------------
        st = {r: get(r).status_code for r in ROTAS}
        registrar("A1 sem token -> 401 nas tres rotas", set(st.values()) == {401}, f"{st}")
        app_tk = criar_access_token(operador.id, operador.negocio_id)
        st = {r: get(r, app_tk).status_code for r in ROTAS}
        registrar("A2 token do app -> 401 nas tres rotas", set(st.values()) == {401}, f"{st}")
        st = {r: get(r, tk(g_sem_web)).status_code for r in ROTAS}
        registrar("A3 gestor sem tem_acesso_web -> 403 nas tres rotas", set(st.values()) == {403}, f"{st}")

        # ---------------- /web/me ----------------
        r = get("/web/me", ta1)
        b = r.json()
        esperado = {"usuario": {"id": g_a1.id, "nome": "Teste gestor_a1", "email": g_a1.email},
                    "central": {"id": c_a1.id, "nome": "_Central A1"},
                    "negocio": {"id": neg_a.id, "nome": neg_a.nome}}
        registrar("M1 /web/me do gestor A1", r.status_code == 200 and b == esperado, f"{r.status_code} -> {b}")
        b = get("/web/me", tk(g_b)).json()
        registrar("M2 /web/me do gestor B", b["negocio"]["id"] == neg_b.id and b["central"]["id"] == c_b.id,
                  f"negocio={b['negocio']['nome']}, central={b['central']['nome']}")

        # ---------------- /web/lojas ----------------
        r = get("/web/lojas", ta1)
        b = r.json()
        registrar("L1 lojas do gestor A1: so a central dele, com a inativa",
                  r.status_code == 200 and [(x["codigo"], x["ativo"]) for x in b] == [("T01", True), ("T02", False)],
                  f"{r.status_code} -> {[(x['codigo'], x['ativo']) for x in b]}")
        registrar("L2 campos da loja", b and set(b[0]) == {"id", "codigo", "nome", "ativo"} and b[0]["id"] == t01.id,
                  f"{b[0] if b else None}")
        b = get("/web/lojas", tk(g_a2)).json()
        registrar("L3 gestor A2 so ve T03", [x["codigo"] for x in b] == ["T03"], f"{[x['codigo'] for x in b]}")
        b = get("/web/lojas", tk(g_b)).json()
        registrar("L4 gestor B so ve TB1", [x["codigo"] for x in b] == ["TB1"], f"{[x['codigo'] for x in b]}")

        # ---------------- /web/produtos ----------------
        r = get("/web/produtos", ta1)
        b = r.json()
        cods = [x["codigo"] for x in b["itens"]]
        registrar("P1 produtos do negocio A (ordem por codigo), sem os de B",
                  r.status_code == 200 and b["total"] == 4 and cods == ["CR-1", "INT-1", "INT-2", "X-1"]
                  and all(x["nome"] != "Pão Francês B" for x in b["itens"]),
                  f"{r.status_code} -> total={b.get('total')}, codigos={cods}")
        cr = next((x for x in b["itens"] if x["codigo"] == "CR-1"), None)
        registrar("P2 produto inativo aparece com ativo=false", cr is not None and cr["ativo"] is False and cr["unidade"] == "UN",
                  f"{cr}")
        b = get("/web/produtos", ta1, busca="pão").json()
        registrar("P3 busca 'pão' (nome, sem diferenciar maiusculas)", sorted(x["codigo"] for x in b["itens"]) == ["INT-1", "INT-2"],
                  f"total={b['total']}, {[x['nome'] for x in b['itens']]}")
        b = get("/web/produtos", ta1, busca="PÃO").json()
        registrar("P4 busca 'PÃO' em maiusculas", b["total"] == 2, f"total={b['total']}")
        b = get("/web/produtos", ta1, busca="int-").json()
        registrar("P5 busca pelo codigo 'int-'", sorted(x["codigo"] for x in b["itens"]) == ["INT-1", "INT-2"], f"total={b['total']}")
        b = get("/web/produtos", ta1, busca="%").json()
        registrar("P6 '%' e texto, nao curinga", [x["codigo"] for x in b["itens"]] == ["X-1"], f"total={b['total']}")
        # Como curinga, "p_o" acharia "Pão" (p + qualquer letra + o); como texto, não acha nada.
        b = get("/web/produtos", ta1, busca="p_o").json()
        registrar("P7 '_' e texto, nao curinga ('p_o' nao acha 'Pão')", b["total"] == 0, f"total={b['total']}")
        b = get("/web/produtos", ta1, busca="%_t").json()
        registrar("P7b '%_t' literal acha so o X-1", [x["codigo"] for x in b["itens"]] == ["X-1"], f"total={b['total']}")
        b = get("/web/produtos", ta1, busca="pao").json()
        registrar("P8 'pao' sem acento acha 'Pão' (unaccent, migration 0017)",
                  sorted(x["codigo"] for x in b["itens"]) == ["INT-1", "INT-2"], f"total={b['total']}, {[x['nome'] for x in b['itens']]}")
        b = get("/web/produtos", ta1, busca="FRANCES").json()
        registrar("P8b 'FRANCES' (sem acento, maiusculas) acha so o 'Pão Francês' de A",
                  [x["codigo"] for x in b["itens"]] == ["INT-1"], f"total={b['total']}, {[x['nome'] for x in b['itens']]}")
        r = get("/web/produtos", ta1, busca="a\\b")
        registrar("P8c barra invertida na busca nao quebra (e o caractere de escape do LIKE)",
                  r.status_code == 200 and r.json()["total"] == 0, f"{r.status_code} -> total={r.json().get('total')}")
        b = get("/web/produtos", ta1, busca="   ").json()
        registrar("P9 busca so com espacos = sem filtro", b["total"] == 4, f"total={b['total']}")
        pag = []
        for off in (0, 2):
            bb = get("/web/produtos", ta1, limit=2, offset=off).json()
            pag += [x["codigo"] for x in bb["itens"]]
        registrar("P10 paginacao de 2 em 2 reconstroi a lista", pag == ["CR-1", "INT-1", "INT-2", "X-1"], f"{pag}")
        r1, r2 = get("/web/produtos", ta1, limit=200), get("/web/produtos", ta1, limit=201)
        registrar("P11 limit 200 aceito, 201 -> 422", r1.status_code == 200 and r2.status_code == 422,
                  f"200 -> {r1.status_code}; 201 -> {r2.status_code}")
        b = get("/web/produtos", tk(g_b)).json()
        registrar("P12 gestor B so ve o produto de B", [x["nome"] for x in b["itens"]] == ["Pão Francês B"], f"{[x['nome'] for x in b['itens']]}")

        # Gestor do seed (só leitura).
        tk_seed = cliente.post("/auth/web/login", json={"email": "gestor@teste.com", "senha": "senha123"})
        if tk_seed.status_code == 200:
            h = tk_seed.json()["access_token"]
            lj = [x["codigo"] for x in get("/web/lojas", h).json()]
            pr = get("/web/produtos", h).json()["total"]
            registrar("Z1 gestor do seed: lojas 001/002 e 11 produtos", lj == ["001", "002"] and pr == 11, f"lojas={lj}, produtos={pr}")
        else:
            registrar("Z1 gestor do seed", False, f"login falhou: {tk_seed.status_code} (rode os seeds)")

    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste das rotas de apoio /web ===")
            for r in resultados:
                print(r)
            falhas = [r for r in resultados if r.startswith(FAIL)]
            print(f"\n{len(resultados)} verificações; " + ("TODAS PASSARAM" if not falhas else f"{len(falhas)} FALHARAM"))
        finally:
            try:
                db.rollback()
                _limpar(db, negocio_ids)
            except Exception as e:
                print(f"[aviso] Erro na limpeza: {e}")
            db.close()

    if not resultados or any(r.startswith(FAIL) for r in resultados):
        sys.exit(1)


if __name__ == "__main__":
    main()
