"""
Testa o lançamento de perda (D110) por HTTP, com o TestClient: app da loja
(/perdas/lancamentos) e SaaS do gestor (/web/perdas/lancamentos). A soma dos
lançamentos do dia tem de virar a perda do dia em `perdas_diarias` (origem
manual), que previsão, necessidade e consultas já leem.

Cenário: negócio A, central A1 (lojas 001 e 002) e central A2 (loja 201);
negócio B (loja B1). Produtos: PA (UN), PB (KG), PX (UN, desativado na 001),
PZ (do negócio B).

Casos:
  A1 sem token -> 403 nas rotas do app (padrão do app)
  A2 token do SaaS no app -> 401; gestor com token do app -> 403
  L1 op001 lança PA 3 un (vencido) -> 201, perda do dia = 3
  L2 op001 lança PA 2 un (avariado) -> perda do dia = 5 (soma)
  L3 inválidos -> 422 e nada gravado: UN fracionada, zero, motivo inválido,
     "outro" sem observação, amanhã, 2 dias atrás, produto desativado na
     loja, produto de outro negócio
  L4 lista do app: op001 vê os 2; op002 não vê nenhum; `?loja_id=` ignorado
  L5 op002 corrige ou apaga o lançamento da 001 -> 404, nada muda
  L6 op001 corrige o 1º de 3 para 1 -> perda do dia = 3
  L7 op001 apaga os dois -> linha manual do dia some
  P1 lançamento de 3 dias atrás: a loja corrige -> 409; o gestor corrige -> 200
     e a perda daquele dia é recalculada
  W1 gestor lista a central (001 e 002, não a 201); filtra loja; loja de
     outra central -> 404; período > 92 dias -> 422
  W2 gestor lança na 002 para 10 dias atrás -> 201; na 201 (outra central) -> 404
  W3 gestor do negócio B corrige ou apaga lançamento do A -> 404
  R1 KG com 3 casas (PB 1,255 kg) aceito; perda do dia 1,255
  O1 OpenAPI: as rotas do app não recebem loja_id nem negocio_id

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_perdas_lancamento_rotas.py
"""

import sys
import uuid
from datetime import time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import PORTA_WEB, criar_access_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.lancamento_perda import LancamentoPerda, MotivoPerda  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.perda_diaria import OrigemPerda, PerdaDiaria  # noqa: E402
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402
from app.services.perda_lancamento_service import hoje_local  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 18
PREFIXO_NEGOCIO_TESTE = "_Teste Perdas Lancamento"
DEC = Decimal
HOJE = hoje_local()

cliente = TestClient(app, raise_server_exceptions=False)
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def corpo(r):
    try:
        return r.json()
    except ValueError:
        return r.text


def detalhe(r):
    b = corpo(r)
    return str(b.get("detail") if isinstance(b, dict) else b)[:160]


def h(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    for modelo in (LancamentoPerda, PerdaDiaria):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    lojas = [l.id for l in db.query(Loja).filter(Loja.negocio_id.in_(negocio_ids))]
    if lojas:
        db.query(ProdutoLoja).filter(ProdutoLoja.loja_id.in_(lojas)).delete(synchronize_session=False)
    for modelo in (Usuario, Produto, Loja, CentralProducao):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Negocio).filter(Negocio.id.in_(negocio_ids)).delete(synchronize_session=False)
    db.commit()


def _limpar_residuos():
    db = SessionLocal()
    try:
        negocios = [n for n in db.query(Negocio).all() if n.nome.startswith(PREFIXO_NEGOCIO_TESTE + " ")]
        if not negocios:
            print("[limpeza inicial] Nenhum resíduo de teste encontrado.")
            return
        print(f"[limpeza inicial] Apagando {len(negocios)} negócio(s) de execuções anteriores.")
        _limpar(db, [n.id for n in negocios])
    finally:
        db.close()


def main():
    _limpar_residuos()
    db = SessionLocal()
    negocio_ids = []
    try:
        run = uuid.uuid4().hex[:8]

        def add(obj):
            db.add(obj)
            db.flush()
            return obj

        neg = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} A", ativo=True))
        neg_b = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} B", ativo=True))
        negocio_ids = [neg.id, neg_b.id]
        a1 = add(CentralProducao(negocio_id=neg.id, nome="_A1", ativa=True))
        a2 = add(CentralProducao(negocio_id=neg.id, nome="_A2", ativa=True))
        cb = add(CentralProducao(negocio_id=neg_b.id, nome="_B", ativa=True))

        def loja(codigo, n, central):
            return add(Loja(negocio_id=n.id, central_producao_id=central.id, nome=f"_Loja {codigo}", codigo=codigo,
                            horario_zeragem=time(6, 0), ativo=True))

        l1, l2, l201, lb = loja("001", neg, a1), loja("002", neg, a1), loja("201", neg, a2), loja("B1", neg_b, cb)

        def usuario(rotulo, n, **campos):
            padrao = dict(tipo_usuario=TipoUsuario.OPERADOR_LOJA, tem_acesso_app=True, tem_acesso_web=False)
            padrao.update(campos)
            return add(Usuario(negocio_id=n.id, nome=f"_U {rotulo}", email=f"tpl_{rotulo}_{run}@teste.com",
                               senha_hash=hash_senha("x"), **padrao))

        op1, op2 = usuario("op1", neg, loja_id=l1.id), usuario("op2", neg, loja_id=l2.id)
        gestor = usuario("gestor", neg, tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=a1.id,
                         tem_acesso_app=False, tem_acesso_web=True)
        gestor_b = usuario("gestorb", neg_b, tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=cb.id,
                           tem_acesso_app=False, tem_acesso_web=True)

        def produto(n, codigo, unidade):
            return add(Produto(negocio_id=n.id, nome=f"_Produto {codigo}", codigo=codigo, unidade_medida=unidade,
                               ativo=True, tipo_abastecimento=TipoAbastecimento.PRODUZIDO))

        pa, pb, px = produto(neg, "PA", UnidadeMedida.UN), produto(neg, "PB", UnidadeMedida.KG), \
            produto(neg, "PX", UnidadeMedida.UN)
        pz = produto(neg_b, "PZ", UnidadeMedida.UN)
        for p, lj, ativo in [(pa, l1, True), (pb, l1, True), (px, l1, False), (pa, l2, True), (pa, l201, True),
                             (pz, lb, True)]:
            add(ProdutoLoja(produto_id=p.id, loja_id=lj.id, ativo=ativo))
        db.commit()

        tk = lambda u: criar_access_token(u.id, u.negocio_id)  # noqa: E731
        tw = lambda u: criar_access_token(u.id, u.negocio_id, porta=PORTA_WEB)  # noqa: E731
        t1, t2, tg, tgb = tk(op1), tk(op2), tw(gestor), tw(gestor_b)

        def chamar(metodo, url, token=None, **kw):
            return getattr(cliente, metodo)(url, headers=h(token), **kw)

        def perda_do_dia(lj, p, dia=HOJE):
            db.expire_all()
            linha = db.query(PerdaDiaria).filter(PerdaDiaria.loja_id == lj.id, PerdaDiaria.produto_id == p.id,
                                                 PerdaDiaria.data == dia,
                                                 PerdaDiaria.origem == OrigemPerda.MANUAL).first()
            return None if linha is None else str(linha.quantidade.normalize())

        def contar():
            db.expire_all()
            return db.query(LancamentoPerda).filter(LancamentoPerda.negocio_id == neg.id).count()

        # ---- A ----
        rotas = [("get", "/perdas/lancamentos", None), ("post", "/perdas/lancamentos", {}),
                 ("put", "/perdas/lancamentos/1", {}), ("delete", "/perdas/lancamentos/1", None)]
        sem = [chamar(m, u, **({"json": j} if j is not None else {})).status_code for m, u, j in rotas]
        registrar("A1 sem token -> 403", sem == [403] * 4, f"{sem}")
        r_web = chamar("get", "/perdas/lancamentos", tg).status_code
        r_ges = chamar("get", "/perdas/lancamentos", tk(gestor)).status_code
        registrar("A2 token do SaaS no app -> 401; gestor com token do app -> 403",
                  (r_web, r_ges) == (401, 403), f"{r_web} {r_ges}")

        # ---- L ----
        r1 = chamar("post", "/perdas/lancamentos", t1, json={"produto_id": pa.id, "quantidade": 3, "motivo": "vencido"})
        id1 = corpo(r1).get("id") if r1.status_code == 201 else None
        registrar("L1 lanca PA 3 un -> 201, perda do dia 3",
                  r1.status_code == 201 and perda_do_dia(l1, pa) == "3"
                  and corpo(r1)["lancado_por"] == "_U op1" and corpo(r1)["loja_pode_alterar"] is True,
                  f"{r1.status_code} perda={perda_do_dia(l1, pa)}")
        r2 = chamar("post", "/perdas/lancamentos", t1,
                    json={"produto_id": pa.id, "quantidade": "2", "motivo": "avariado", "observacao": " caiu "})
        id2 = corpo(r2).get("id") if r2.status_code == 201 else None
        registrar("L2 segundo lancamento soma -> 5", r2.status_code == 201 and perda_do_dia(l1, pa) == "5"
                  and corpo(r2)["observacao"] == "caiu", f"{r2.status_code} perda={perda_do_dia(l1, pa)}")

        antes = contar()
        invalidos = {
            "UN fracionada": {"produto_id": pa.id, "quantidade": "1.5", "motivo": "vencido"},
            "zero": {"produto_id": pa.id, "quantidade": 0, "motivo": "vencido"},
            "motivo invalido": {"produto_id": pa.id, "quantidade": 1, "motivo": "furto"},
            "outro sem obs": {"produto_id": pa.id, "quantidade": 1, "motivo": "outro"},
            "amanha": {"produto_id": pa.id, "quantidade": 1, "motivo": "vencido",
                       "data": str(HOJE + timedelta(days=1))},
            "2 dias atras": {"produto_id": pa.id, "quantidade": 1, "motivo": "vencido",
                             "data": str(HOJE - timedelta(days=2))},
            "desativado na loja": {"produto_id": px.id, "quantidade": 1, "motivo": "vencido"},
            "outro negocio": {"produto_id": pz.id, "quantidade": 1, "motivo": "vencido"},
        }
        codigos = {k: chamar("post", "/perdas/lancamentos", t1, json=v).status_code for k, v in invalidos.items()}
        r_desc = chamar("post", "/perdas/lancamentos", t1, json=invalidos["UN fracionada"])
        registrar("L3 invalidos -> 422 em portugues, nada gravado",
                  set(codigos.values()) == {422} and contar() == antes and "inteira" in detalhe(r_desc),
                  f"{codigos} msg={detalhe(r_desc)}")

        l_1 = [x["id"] for x in corpo(chamar("get", "/perdas/lancamentos", t1))]
        l_2 = corpo(chamar("get", "/perdas/lancamentos", t2))
        l_2q = corpo(chamar("get", f"/perdas/lancamentos?loja_id={l1.id}", t2))
        registrar("L4 cada loja ve so os seus", sorted(l_1) == sorted([id1, id2]) and l_2 == [] and l_2q == [],
                  f"001 {l_1}; 002 {l_2}; 002?loja=001 {l_2q}")

        rp = chamar("put", f"/perdas/lancamentos/{id1}", t2, json={"quantidade": 9, "motivo": "vencido"})
        rd = chamar("delete", f"/perdas/lancamentos/{id1}", t2)
        registrar("L5 outra loja nao corrige nem apaga -> 404", (rp.status_code, rd.status_code) == (404, 404)
                  and perda_do_dia(l1, pa) == "5", f"{rp.status_code} {rd.status_code} perda={perda_do_dia(l1, pa)}")

        r = chamar("put", f"/perdas/lancamentos/{id1}", t1, json={"quantidade": 1, "motivo": "vencido"})
        registrar("L6 corrige 3 -> 1, perda do dia 3", r.status_code == 200 and perda_do_dia(l1, pa) == "3"
                  and corpo(r)["alterado_por"] == "_U op1", f"{r.status_code} perda={perda_do_dia(l1, pa)}")

        c1 = chamar("delete", f"/perdas/lancamentos/{id1}", t1).status_code
        meio = perda_do_dia(l1, pa)
        c2 = chamar("delete", f"/perdas/lancamentos/{id2}", t1).status_code
        registrar("L7 apaga os dois -> 2 e depois linha some", (c1, c2) == (204, 204) and meio == "2"
                  and perda_do_dia(l1, pa) is None, f"{c1} {c2} meio={meio} fim={perda_do_dia(l1, pa)}")

        # ---- P: prazo da loja ----
        dia_velho = HOJE - timedelta(days=3)
        velho = add(LancamentoPerda(negocio_id=neg.id, loja_id=l1.id, produto_id=pa.id, data=dia_velho,
                                    quantidade=DEC("4"), motivo=MotivoPerda.VENCIDO,
                                    lancado_por_usuario_id=op1.id))
        db.commit()
        velho_id = velho.id
        rl = chamar("put", f"/perdas/lancamentos/{velho_id}", t1, json={"quantidade": 1, "motivo": "vencido"})
        rdl = chamar("delete", f"/perdas/lancamentos/{velho_id}", t1)
        rg = chamar("put", f"/web/perdas/lancamentos/{velho_id}", tg, json={"quantidade": 6, "motivo": "avariado"})
        registrar("P1 fora do prazo: loja 409; gestor corrige e recalcula",
                  (rl.status_code, rdl.status_code, rg.status_code) == (409, 409, 200)
                  and perda_do_dia(l1, pa, dia_velho) == "6" and "gestor" in detalhe(rl),
                  f"{rl.status_code} {rdl.status_code} {rg.status_code} perda={perda_do_dia(l1, pa, dia_velho)}")
        lista_app = [x["id"] for x in corpo(chamar("get", "/perdas/lancamentos", t1))]
        registrar("P2 lista do app so traz hoje e ontem", velho_id not in lista_app, f"{lista_app}")

        # ---- W: SaaS ----
        ini, fim = str(HOJE - timedelta(days=30)), str(HOJE)
        r201 = add(LancamentoPerda(negocio_id=neg.id, loja_id=l201.id, produto_id=pa.id, data=HOJE,
                                   quantidade=DEC("1"), motivo=MotivoPerda.VENCIDO, lancado_por_usuario_id=op1.id))
        db.commit()
        rw = chamar("post", "/web/perdas/lancamentos", tg,
                    json={"loja_id": l2.id, "produto_id": pa.id, "quantidade": 7, "motivo": "vencido",
                          "data": str(HOJE - timedelta(days=10))})
        rw_fora = chamar("post", "/web/perdas/lancamentos", tg,
                         json={"loja_id": l201.id, "produto_id": pa.id, "quantidade": 1, "motivo": "vencido",
                               "data": str(HOJE)})
        registrar("W2 gestor lanca na 002 (10 dias atras) -> 201; na 201 -> 404",
                  rw.status_code == 201 and rw_fora.status_code == 404
                  and perda_do_dia(l2, pa, HOJE - timedelta(days=10)) == "7",
                  f"{rw.status_code} {rw_fora.status_code}")
        todas = corpo(chamar("get", f"/web/perdas/lancamentos?data_inicio={ini}&data_fim={fim}", tg))
        lojas_vistas = sorted({x["loja"]["codigo"] for x in todas}) if isinstance(todas, list) else todas
        so_002 = corpo(chamar("get", f"/web/perdas/lancamentos?data_inicio={ini}&data_fim={fim}&loja_id={l2.id}", tg))
        fora = chamar("get", f"/web/perdas/lancamentos?data_inicio={ini}&data_fim={fim}&loja_id={l201.id}", tg)
        longo = chamar("get", f"/web/perdas/lancamentos?data_inicio={HOJE - timedelta(days=100)}&data_fim={fim}", tg)
        registrar("W1 gestor ve so a central; outra central 404; periodo longo 422",
                  lojas_vistas == ["001", "002"] and [x["loja"]["codigo"] for x in so_002] == ["002"]
                  and fora.status_code == 404 and longo.status_code == 422 and r201.id not in [x["id"] for x in todas],
                  f"{lojas_vistas} {fora.status_code} {longo.status_code}")
        rb1 = chamar("put", f"/web/perdas/lancamentos/{velho_id}", tgb, json={"quantidade": 1, "motivo": "vencido"})
        rb2 = chamar("delete", f"/web/perdas/lancamentos/{velho_id}", tgb)
        rb3 = chamar("delete", f"/web/perdas/lancamentos/{r201.id}", tg)
        registrar("W3 outro negocio ou outra central -> 404",
                  (rb1.status_code, rb2.status_code, rb3.status_code) == (404, 404, 404)
                  and perda_do_dia(l1, pa, dia_velho) == "6", f"{rb1.status_code} {rb2.status_code} {rb3.status_code}")
        rgd = chamar("delete", f"/web/perdas/lancamentos/{velho_id}", tg)
        registrar("W4 gestor apaga lancamento antigo -> 204, linha some",
                  rgd.status_code == 204 and perda_do_dia(l1, pa, dia_velho) is None, f"{rgd.status_code}")

        # ---- R ----
        r = chamar("post", "/perdas/lancamentos", t1, json={"produto_id": pb.id, "quantidade": "1.255",
                                                           "motivo": "outro", "observacao": "Queimou no forno"})
        r4 = chamar("post", "/perdas/lancamentos", t1, json={"produto_id": pb.id, "quantidade": "1.2555",
                                                            "motivo": "vencido"})
        registrar("R1 KG 3 casas aceito; 4 casas 422", r.status_code == 201 and perda_do_dia(l1, pb) == "1.255"
                  and r4.status_code == 422, f"{r.status_code} {r4.status_code} perda={perda_do_dia(l1, pb)}")
        ontem = chamar("post", "/perdas/lancamentos", t1, json={"produto_id": pa.id, "quantidade": 2,
                                                               "motivo": "vencido", "data": str(HOJE - timedelta(1))})
        hoje_pa = chamar("post", "/perdas/lancamentos", t1, json={"produto_id": pa.id, "quantidade": 1,
                                                                 "motivo": "vencido"})
        registrar("R2 loja lanca para ontem -> 201; cada dia soma so o seu",
                  (ontem.status_code, hoje_pa.status_code) == (201, 201)
                  and perda_do_dia(l1, pa, HOJE - timedelta(1)) == "2" and perda_do_dia(l1, pa) == "1",
                  f"{ontem.status_code} ontem={perda_do_dia(l1, pa, HOJE - timedelta(1))} hoje={perda_do_dia(l1, pa)}")

        # ---- O ----
        spec = cliente.get("/openapi.json").json()
        params = []
        for caminho in ("/perdas/lancamentos", "/perdas/lancamentos/{lancamento_id}"):
            for op in spec["paths"].get(caminho, {}).values():
                params += [p["name"] for p in op.get("parameters", [])]
                esquema = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
                ref = esquema.get("$ref", "").split("/")[-1]
                if ref:
                    params += list(spec["components"]["schemas"][ref].get("properties", {}))
        registrar("O1 rotas do app sem loja_id/negocio_id", "loja_id" not in params and "negocio_id" not in params,
                  f"{sorted(set(params))}")
    finally:
        try:
            _limpar(db, negocio_ids)
        finally:
            db.close()

    print()
    for linha in resultados:
        print(linha)
    falhas = [r for r in resultados if r.startswith(FAIL)]
    print()
    print(f"{len(resultados) - len(falhas)}/{TOTAL_CASOS} casos OK")
    if falhas or len(resultados) != TOTAL_CASOS:
        sys.exit(1)


if __name__ == "__main__":
    main()
