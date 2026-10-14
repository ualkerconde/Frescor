"""
Testa GET /vendas e GET /perdas (Fase 2 / P6) por HTTP, com o TestClient,
e o critério de aceite da Fase 2 de ponta a ponta (importar um CSV pela
rota e consultá-lo).

Cenário (dados inseridos direto no banco, em setembro de 2026):
  negócio A, central A1: lojas T01 e T02; central A2: loja T03
  negócio B, central B: loja TB1
  produtos de A: P1 (UN), P2 (KG); de B: PB
  vendas A1: T01/P1 dias 1-5 (manual) + dia 1 (api); T01/P2 dias 1-3; T02/P1 dia 2 -> 10 linhas
  vendas A2: T03/P1 dia 1; vendas B: TB1/PB dia 1
  perdas A1: T01/P1 dia 1 e dia 2 -> 2 linhas
Usuários: gestor de A1, gestor de A2, gestor de B, gestor de A1 sem
tem_acesso_web, operador de loja (token do app).

Uso: python scripts/test_consulta_rotas.py
"""

import re
import sys
import uuid
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import PORTA_WEB, criar_access_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.perda_diaria import OrigemPerda, PerdaDiaria  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
PREFIXO_NEGOCIO_TESTE = "_Teste Consulta"
EMAIL_TESTE = re.compile(r"^tcr_[a-z_0-9]+_[0-9a-f]{8}@teste[.]com$")
SET = lambda d: date(2026, 9, d)  # noqa: E731
PERIODO = {"data_inicio": "2026-09-01", "data_fim": "2026-09-30"}

cliente = TestClient(app)
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def get(rota, token=None, **params):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return cliente.get(rota, params=params, headers=headers)


def corpo(r):
    try:
        return r.json()
    except ValueError:
        return r.text


def chaves(itens):
    return [(i["data"], i["loja"]["codigo"], i["produto"]["codigo"], i["origem"]) for i in itens]


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    db.query(VendaDiaria).filter(VendaDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(PerdaDiaria).filter(PerdaDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    produto_ids = [p.id for p in db.query(Produto).filter(Produto.negocio_id.in_(negocio_ids))]
    if produto_ids:
        db.query(ProdutoLoja).filter(ProdutoLoja.produto_id.in_(produto_ids)).delete(synchronize_session=False)
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
        avulsos = [u for u in db.query(Usuario).filter(Usuario.email.like("tcr_%@teste.com")).all()
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

        def loja(neg, central, codigo):
            lj = Loja(negocio_id=neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}", codigo=codigo,
                      horario_zeragem=time(6, 0), ativo=True)
            db.add(lj)
            return lj

        t01, t02, t03, tb1 = loja(neg_a, c_a1, "T01"), loja(neg_a, c_a1, "T02"), loja(neg_a, c_a2, "T03"), loja(neg_b, c_b, "TB1")
        p1 = Produto(negocio_id=neg_a.id, nome="_Produto Um", codigo="P1", unidade_medida=UnidadeMedida.UN, ativo=True)
        p2 = Produto(negocio_id=neg_a.id, nome="_Produto Dois", codigo="P2", unidade_medida=UnidadeMedida.KG, ativo=True)
        pb = Produto(negocio_id=neg_b.id, nome="_Produto B", codigo="PB", unidade_medida=UnidadeMedida.UN, ativo=True)
        db.add_all([p1, p2, pb])
        db.flush()
        for p, lj in ((p1, t01), (p2, t01), (p1, t02)):
            db.add(ProdutoLoja(produto_id=p.id, loja_id=lj.id))

        def venda(neg, lj, p, dia, qtd, origem=OrigemVenda.MANUAL):
            db.add(VendaDiaria(negocio_id=neg.id, loja_id=lj.id, produto_id=p.id, data=SET(dia),
                               quantidade=Decimal(qtd), origem=origem))

        for d in range(1, 6):
            venda(neg_a, t01, p1, d, str(10 + d))
        venda(neg_a, t01, p1, 1, "99", OrigemVenda.API)
        for d in range(1, 4):
            venda(neg_a, t01, p2, d, "1.250")
        venda(neg_a, t02, p1, 2, "7")
        venda(neg_a, t03, p1, 1, "5")
        venda(neg_b, tb1, pb, 1, "3")
        for d in (1, 2):
            db.add(PerdaDiaria(negocio_id=neg_a.id, loja_id=t01.id, produto_id=p1.id, data=SET(d),
                               quantidade=Decimal("1"), origem=OrigemPerda.MANUAL))

        def usuario(rotulo, neg, **campos):
            u = Usuario(negocio_id=neg.id, nome=f"Teste {rotulo}", email=f"tcr_{rotulo}_{run_id}@teste.com",
                        senha_hash=hash_senha("x"), status=StatusUsuario.ATIVO, **campos)
            db.add(u)
            db.flush()
            return u

        gestor = dict(tipo_usuario=TipoUsuario.GESTOR_CENTRAL, tem_acesso_app=False)
        g_a1 = usuario("gestor_a1", neg_a, central_producao_id=c_a1.id, tem_acesso_web=True, **gestor)
        g_a2 = usuario("gestor_a2", neg_a, central_producao_id=c_a2.id, tem_acesso_web=True, **gestor)
        g_b = usuario("gestor_b", neg_b, central_producao_id=c_b.id, tem_acesso_web=True, **gestor)
        g_sem_web = usuario("gestor_sem_web", neg_a, central_producao_id=c_a1.id, tem_acesso_web=False, **gestor)
        operador = usuario("operador", neg_a, tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=t01.id,
                           tem_acesso_web=False, tem_acesso_app=True)
        db.commit()
        tk = lambda u: criar_access_token(u.id, u.negocio_id, porta=PORTA_WEB)  # noqa: E731
        ta1 = tk(g_a1)

        # ---------------- autenticação ----------------
        r = get("/vendas", **PERIODO)
        registrar("A1 sem token", r.status_code == 401, f"{r.status_code}")
        r = get("/vendas", criar_access_token(operador.id, operador.negocio_id), **PERIODO)
        registrar("A2 token do app (operador)", r.status_code == 401, f"{r.status_code}")
        r = get("/vendas", tk(g_sem_web), **PERIODO)
        registrar("A3 gestor sem tem_acesso_web", r.status_code == 403, f"{r.status_code} -> {corpo(r)}")
        r = get("/perdas", **PERIODO)
        registrar("A4 /perdas sem token", r.status_code == 401, f"{r.status_code}")

        # ---------------- escopo e filtros ----------------
        r = get("/vendas", ta1, **PERIODO)
        b = corpo(r)
        lojas = sorted({i["loja"]["codigo"] for i in b["itens"]}) if r.status_code == 200 else None
        registrar("F1 sem filtros: so lojas da central A1", r.status_code == 200 and b["total"] == 10 and lojas == ["T01", "T02"],
                  f"{r.status_code} -> total={b.get('total') if isinstance(b, dict) else b}, lojas={lojas}")
        tudo = b["itens"] if r.status_code == 200 else []

        r = get("/vendas", ta1, loja_id=t01.id, **PERIODO)
        registrar("F2 loja_id=T01", corpo(r).get("total") == 9, f"total={corpo(r).get('total')}")
        r = get("/vendas", ta1, produto_id=p2.id, **PERIODO)
        registrar("F3 produto_id=P2", corpo(r).get("total") == 3, f"total={corpo(r).get('total')}")
        r = get("/vendas", ta1, loja_id=t02.id, produto_id=p1.id, **PERIODO)
        registrar("F4 loja_id=T02 + produto_id=P1", corpo(r).get("total") == 1, f"total={corpo(r).get('total')}")
        r = get("/vendas", ta1, data_inicio="2026-09-02", data_fim="2026-09-03")
        datas = sorted({i["data"] for i in corpo(r)["itens"]})
        registrar("F5 periodo 02 a 03/09 (inclusive)", corpo(r).get("total") == 5 and datas == ["2026-09-02", "2026-09-03"],
                  f"total={corpo(r).get('total')}, datas={datas}")
        r = get("/vendas", ta1, produto_id=pb.id, **PERIODO)
        registrar("F6 produto de outro negocio -> lista vazia", r.status_code == 200 and corpo(r)["total"] == 0,
                  f"{r.status_code} -> total={corpo(r).get('total')}")

        # ---------------- formato do item ----------------
        kg = next((i for i in tudo if i["produto"]["codigo"] == "P2"), None)
        esperado = {"data": "2026-09-01", "loja": {"id": t01.id, "codigo": "T01"},
                    "produto": {"id": p2.id, "codigo": "P2", "nome": "_Produto Dois"},
                    "quantidade": "1.250", "unidade": "KG", "origem": "manual"}
        registrar("I1 campos do item (produto KG)", kg == esperado, f"{kg}")
        api = [i for i in tudo if i["origem"] == "api"]
        registrar("I2 origem api listada junto com a manual do mesmo dia",
                  len(api) == 1 and api[0]["quantidade"] == "99.000", f"{api}")

        # ---------------- ordenação e paginação ----------------
        ordem = [(i["data"], i["loja"]["id"], i["produto"]["id"], i["origem"]) for i in tudo]
        registrar("O1 ordenacao por data, loja, produto, origem", ordem == sorted(ordem), f"{chaves(tudo)[:4]}...")
        paginas, totais = [], set()
        for off in (0, 3, 6, 9):
            r = get("/vendas", ta1, limit=3, offset=off, **PERIODO)
            paginas += corpo(r)["itens"]
            totais.add(corpo(r)["total"])
        registrar("O2 paginas de 3 reconstroem a lista sem repetir nem pular",
                  chaves(paginas) == chaves(tudo) and totais == {10} and len(set(chaves(paginas))) == 10,
                  f"{len(paginas)} itens em 4 paginas, totais={totais}")
        r = get("/vendas", ta1, limit=3, offset=9, **PERIODO)
        registrar("O3 ultima pagina parcial", len(corpo(r)["itens"]) == 1 and corpo(r)["limit"] == 3 and corpo(r)["offset"] == 9,
                  f"itens={len(corpo(r)['itens'])}, limit={corpo(r)['limit']}, offset={corpo(r)['offset']}")
        r = get("/vendas", ta1, limit=1000, **PERIODO)
        registrar("O4 limit=1000 aceito", r.status_code == 200, f"{r.status_code}")
        r = get("/vendas", ta1, limit=1001, **PERIODO)
        registrar("O5 limit=1001 -> 422", r.status_code == 422, f"{r.status_code}")
        r = get("/vendas", ta1, limit=0, **PERIODO)
        registrar("O6 limit=0 -> 422", r.status_code == 422, f"{r.status_code}")

        # ---------------- período ----------------
        r = get("/vendas", ta1, data_inicio="2026-09-10", data_fim="2026-09-01")
        registrar("P1 data_inicio depois de data_fim -> 422", r.status_code == 422 and "posterior" in str(corpo(r)),
                  f"{r.status_code} -> {corpo(r)}")
        r = get("/vendas", ta1, data_inicio="2025-09-01", data_fim="2026-09-02")
        registrar("P2 periodo de 367 dias -> 422", r.status_code == 422 and "367 dias" in str(corpo(r)),
                  f"{r.status_code} -> {corpo(r)}")
        inicio = date(2025, 10, 1)
        r = get("/vendas", ta1, data_inicio=str(inicio), data_fim=str(inicio + timedelta(days=365)))
        registrar("P3 periodo de exatamente 366 dias -> 200", r.status_code == 200, f"{r.status_code}")
        r = get("/vendas", ta1, data_fim="2026-09-30")
        registrar("P4 sem data_inicio -> 422 do FastAPI", r.status_code == 422, f"{r.status_code}")
        r = get("/vendas", ta1, data_inicio="01/09/2026", data_fim="2026-09-30")
        registrar("P5 data em dd/mm/aaaa na URL -> 422", r.status_code == 422, f"{r.status_code}")

        # ---------------- loja fora do escopo (404 idêntico) ----------------
        respostas = []
        for nome, lid in (("E1 loja de outra central (T03)", t03.id), ("E2 loja de outro negocio (TB1)", tb1.id),
                          ("E3 loja inexistente", 2_000_000_000)):
            r = get("/vendas", ta1, loja_id=lid, **PERIODO)
            respostas.append((r.status_code, r.text))
            registrar(nome, r.status_code == 404, f"{r.status_code} -> {corpo(r)}")
        registrar("E4 as tres respostas 404 sao identicas", len(set(respostas)) == 1, f"{len(set(respostas))} distinta(s)")

        # ---------------- isolamento ----------------
        r = get("/vendas", tk(g_a2), **PERIODO)
        registrar("S1 gestor A2 so ve T03", [i["loja"]["codigo"] for i in corpo(r)["itens"]] == ["T03"], f"{chaves(corpo(r)['itens'])}")
        r = get("/vendas", tk(g_b), **PERIODO)
        registrar("S2 gestor do negocio B so ve TB1", [i["loja"]["codigo"] for i in corpo(r)["itens"]] == ["TB1"],
                  f"{chaves(corpo(r)['itens'])}")
        r = get("/vendas", tk(g_b), loja_id=t01.id, **PERIODO)
        registrar("S3 gestor B pedindo loja de A -> 404", r.status_code == 404, f"{r.status_code}")

        # ---------------- perdas ----------------
        r = get("/perdas", ta1, **PERIODO)
        registrar("L1 /perdas devolve so perdas", r.status_code == 200 and corpo(r)["total"] == 2,
                  f"{r.status_code} -> total={corpo(r).get('total')}")

        # ---------------- critério de aceite da Fase 2, de ponta a ponta ----------------
        csv = "data;codigo_loja;codigo_produto;quantidade\r\n20/09/2026;T02;P1;30\r\n21/09/2026;T02;P1;31\r\n"
        r = cliente.post("/vendas/importar", files={"arquivo": ("vendas.csv", csv.encode(), "text/csv")},
                         headers={"Authorization": f"Bearer {ta1}"})
        registrar("Z1 importar CSV pela rota", r.status_code == 200 and corpo(r)["inseridas"] == 2, f"{r.status_code} -> {corpo(r)}")
        r = get("/vendas", ta1, loja_id=t02.id, produto_id=p1.id, data_inicio="2026-09-20", data_fim="2026-09-21")
        itens = [(i["data"], i["quantidade"], i["origem"]) for i in corpo(r).get("itens", [])]
        registrar("Z2 consultar o que foi importado",
                  itens == [("2026-09-20", "30.000", "manual"), ("2026-09-21", "31.000", "manual")], f"{r.status_code} -> {itens}")

    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste das rotas de consulta ===")
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
