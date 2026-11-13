"""
Testa o acompanhamento (dashboard, D115/D116) por HTTP: GET /web/acompanhamento.

Cenário: negócio A, central A1 (lojas 001 e 002) e central A2 (loja 201);
negócio B. Produtos PA (UN) e PB (KG). Período fixo de 05/10 a 07/10/2026
(D1, D2, D3).

Dados de A1:
  previsão PA: 001 D1=10, 001 D2=12, 002 D1=5 (feitas na véspera);
               (D3 sem previsão: a venda aparece no dia, fora do erro)
  previsão PB: 001 D1=2,5
  venda PA:    001 D1 manual 50 + api 8 (a api vence: 8), 001 D2=12,
               002 D1=6, 001 D3=9; PB 001 D1=2
  perda PA:    001 D1=1
  ordem APROVADA entrega D1: PA produzido 20; 001 sugerido 11 final 12;
               002 sugerido 5 final 6
  ordem RASCUNHO entrega D2: 001 sugerido/final 99 (fica de fora)
  romaneio D1: entrega 001 expedida (PA 12); entrega 002 aguardando saída
               (PA 6, fica de fora)
  loja 201 (outra central) e negócio B: previsão e venda 999 (ficam de fora)

Casos:
  A1 sem token -> 401; token do app -> 401
  T1 totais UN: previsto 27, sugerido 16, final 18, produzido 20, enviado 12,
     vendido 35, perda 1
  T2 erro UN: 3 células, WAPE 3/26 = 0,1154, viés 1/26 = 0,0385
  T3 KG separado do UN: previsto 2,5, vendido 2, WAPE 0,25
  T4 dia D1 UN: previsto 15, vendido 14, final 18, produzido 20; D2 sem ordem
     (sugerido None); 3 dias na série
  T5 produto PA: sobra = enviado − vendido − perda = 12 − 35 − 1 = −24
  F1 filtro loja 002: produção fora (produzido_disponivel False, None),
     previsto 5, vendido 6, final 6, enviado None
  F2 filtro produto PB: só a unidade KG
  F3 loja de outra central -> 404; período > 28 dias -> 422; fim < início -> 422
  F4 padrão: 7 dias até ontem
  I1 gestor do negócio B não vê nada de A

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_acompanhamento_rotas.py
"""

import sys
import uuid
from datetime import date, datetime, time, timedelta
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
from app.models.ordem_producao import OrdemProducao, StatusOrdemProducao  # noqa: E402
from app.models.ordem_producao_item import OrdemProducaoItem  # noqa: E402
from app.models.ordem_producao_linha import OrdemProducaoLinha  # noqa: E402
from app.models.perda_diaria import OrigemPerda, PerdaDiaria  # noqa: E402
from app.models.previsao_diaria import EstatisticaBase, MetodoPrevisao, PrevisaoDiaria  # noqa: E402
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida  # noqa: E402
from app.models.romaneio import Romaneio, StatusRomaneio  # noqa: E402
from app.models.romaneio_entrega import RomaneioEntrega, SituacaoEntrega  # noqa: E402
from app.models.romaneio_item import RomaneioItem  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402
from app.services.perda_lancamento_service import hoje_local  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 13
PREFIXO_NEGOCIO_TESTE = "_Teste Acompanhamento"
DEC = Decimal
D1, D2, D3 = date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)
PERIODO = f"data_inicio={D1}&data_fim={D3}"

cliente = TestClient(app, raise_server_exceptions=False)
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def corpo(r):
    try:
        return r.json()
    except ValueError:
        return r.text


def h(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


def n(valor):
    """Texto decimal da API -> Decimal normalizado (None fica None)."""
    return None if valor is None else DEC(str(valor)).normalize()


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    db.query(Romaneio).filter(Romaneio.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (RomaneioItem, RomaneioEntrega):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(OrdemProducao).filter(OrdemProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (OrdemProducaoLinha, OrdemProducaoItem, PrevisaoDiaria, VendaDiaria, PerdaDiaria, Usuario,
                   Produto, Loja, CentralProducao):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Negocio).filter(Negocio.id.in_(negocio_ids)).delete(synchronize_session=False)
    db.commit()


def _limpar_residuos():
    db = SessionLocal()
    try:
        negocios = [x for x in db.query(Negocio).all() if x.nome.startswith(PREFIXO_NEGOCIO_TESTE + " ")]
        if not negocios:
            print("[limpeza inicial] Nenhum resíduo de teste encontrado.")
            return
        print(f"[limpeza inicial] Apagando {len(negocios)} negócio(s) de execuções anteriores.")
        _limpar(db, [x.id for x in negocios])
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

        def loja(codigo, ng, central):
            return add(Loja(negocio_id=ng.id, central_producao_id=central.id, nome=f"_Loja {codigo}", codigo=codigo,
                            horario_zeragem=time(6, 0), ativo=True))

        l1, l2, l201, lb = loja("001", neg, a1), loja("002", neg, a1), loja("201", neg, a2), loja("B1", neg_b, cb)

        def gestor(rotulo, ng, central):
            return add(Usuario(negocio_id=ng.id, nome=f"_G {rotulo}", email=f"tac_{rotulo}_{run}@teste.com",
                               senha_hash=hash_senha("x"), tipo_usuario=TipoUsuario.GESTOR_CENTRAL,
                               central_producao_id=central.id, tem_acesso_app=False, tem_acesso_web=True))

        g, gb = gestor("a1", neg, a1), gestor("b", neg_b, cb)
        op = add(Usuario(negocio_id=neg.id, nome="_Op", email=f"tac_op_{run}@teste.com", senha_hash=hash_senha("x"),
                         tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=l1.id, tem_acesso_app=True,
                         tem_acesso_web=False))

        def produto(ng, codigo, unidade):
            return add(Produto(negocio_id=ng.id, nome=f"_Produto {codigo}", codigo=codigo, unidade_medida=unidade,
                               ativo=True, tipo_abastecimento=TipoAbastecimento.PRODUZIDO))

        pa, pb, pz = produto(neg, "PA", UnidadeMedida.UN), produto(neg, "PB", UnidadeMedida.KG), \
            produto(neg_b, "PZ", UnidadeMedida.UN)

        def prev(ng, central, lj, p, dia, valor, ref=None):
            add(PrevisaoDiaria(
                negocio_id=ng.id, central_producao_id=central.id, loja_id=lj.id, produto_id=p.id, data=dia,
                data_referencia=ref or dia - timedelta(days=1), previsao=DEC(valor), metodo=MetodoPrevisao.SEMANAL,
                estatistica=EstatisticaBase.MEDIANA, semanas_na_base=6, tendencia=DEC(1), dias_na_tendencia=7,
                peso_historico=DEC(1), versao_metodo="teste"))

        def venda(ng, lj, p, dia, valor, origem="manual"):
            add(VendaDiaria(negocio_id=ng.id, loja_id=lj.id, produto_id=p.id, data=dia, quantidade=DEC(valor),
                            origem=OrigemVenda(origem)))

        prev(neg, a1, l1, pa, D1, 10)
        prev(neg, a1, l1, pa, D2, 12)
        prev(neg, a1, l2, pa, D1, 5)
        prev(neg, a1, l1, pb, D1, "2.5")
        prev(neg, a2, l201, pa, D1, 999)
        prev(neg_b, cb, lb, pz, D1, 999)
        venda(neg, l1, pa, D1, 50)
        venda(neg, l1, pa, D1, 8, "api")
        venda(neg, l1, pa, D2, 12)
        venda(neg, l2, pa, D1, 6)
        venda(neg, l1, pa, D3, 9)
        venda(neg, l1, pb, D1, 2)
        venda(neg, l201, pa, D1, 999)
        venda(neg_b, lb, pz, D1, 999)
        add(PerdaDiaria(negocio_id=neg.id, loja_id=l1.id, produto_id=pa.id, data=D1, quantidade=DEC(1),
                        origem=OrigemPerda.MANUAL))

        agora = datetime(2026, 10, 4, 12, 0)

        def ordem(entrega, aprovada, linhas, produzido=None):
            o = add(OrdemProducao(
                negocio_id=neg.id, central_producao_id=a1.id, data_producao=entrega - timedelta(days=1),
                data_entrega=entrega, versao_metodo="teste", gerado_em=agora,
                status=StatusOrdemProducao.APROVADA if aprovada else StatusOrdemProducao.RASCUNHO,
                aprovado_em=agora if aprovada else None, aprovado_por_usuario_id=g.id if aprovada else None))
            item = add(OrdemProducaoItem(negocio_id=neg.id, ordem_id=o.id, produto_id=pa.id,
                                         tipo_abastecimento=pa.tipo_abastecimento, unidade=pa.unidade_medida,
                                         quantidade_produzida=None if produzido is None else DEC(produzido),
                                         producao_registrada_em=agora if produzido is not None else None,
                                         producao_registrada_por_usuario_id=g.id if produzido is not None else None))
            criadas = {}
            for lj, sug, fin in linhas:
                criadas[lj.codigo] = add(OrdemProducaoLinha(negocio_id=neg.id, item_id=item.id, loja_id=lj.id,
                                                            quantidade_sugerida=DEC(sug), quantidade_final=DEC(fin)))
            return o, criadas

        o1, linhas1 = ordem(D1, True, [(l1, 11, 12), (l2, 5, 6)], produzido=20)
        ordem(D2, False, [(l1, 99, 99)])
        rom = add(Romaneio(negocio_id=neg.id, central_producao_id=a1.id, ordem_id=o1.id, data_entrega=D1,
                           status=StatusRomaneio.APROVADO, gerado_em=agora, aprovado_em=agora,
                           aprovado_por_usuario_id=g.id))
        for lj, saiu, qtd in [(l1, True, 12), (l2, False, 6)]:
            ent = add(RomaneioEntrega(
                negocio_id=neg.id, romaneio_id=rom.id, loja_id=lj.id,
                situacao=SituacaoEntrega.EXPEDIDA if saiu else SituacaoEntrega.AGUARDANDO_SAIDA,
                expedido_em=agora if saiu else None, expedido_por_usuario_id=g.id if saiu else None))
            add(RomaneioItem(negocio_id=neg.id, entrega_id=ent.id, produto_id=pa.id,
                             ordem_linha_id=linhas1[lj.codigo].id, unidade=pa.unidade_medida,
                             quantidade_sugerida=DEC(qtd), quantidade_final=DEC(qtd)))
        db.commit()

        tg = criar_access_token(g.id, g.negocio_id, porta=PORTA_WEB)
        tgb = criar_access_token(gb.id, gb.negocio_id, porta=PORTA_WEB)

        def get(query="", token=tg):
            return cliente.get(f"/web/acompanhamento{('?' + query) if query else ''}", headers=h(token))

        # ---- A ----
        s1, s2 = get(token=None).status_code, get(token=criar_access_token(op.id, op.negocio_id)).status_code
        registrar("A1 sem token -> 401; token do app -> 401", (s1, s2) == (401, 401), f"{s1} {s2}")

        r = get(PERIODO)
        b = corpo(r) if r.status_code == 200 else {}
        un = next((u for u in b.get("unidades", []) if u["unidade"] == "UN"), None)
        kg = next((u for u in b.get("unidades", []) if u["unidade"] == "KG"), None)

        # ---- T ----
        esperado = {"previsto": 27, "sugerido": 16, "final": 18, "produzido": 20, "enviado": 12, "vendido": 35,
                    "perda": 1}
        obtido = {k: n(v) for k, v in (un or {}).get("totais", {}).items()}
        # Sem contagem no cenário: nenhum balanço (D111), sem_registro None e 0 balanços.
        registrar("T1 totais UN", obtido == {**{k: DEC(v) for k, v in esperado.items()}, "sem_registro": None}
                  and (un or {}).get("balancos") == 0, f"{r.status_code} {obtido}")
        erro = (un or {}).get("erro", {})
        registrar("T2 erro UN (3 celulas, WAPE 0,1154, vies 0,0385)",
                  erro.get("celulas") == 3 and n(erro.get("wape")) == DEC("0.1154")
                  and n(erro.get("vies")) == DEC("0.0385"), f"{erro}")
        registrar("T3 KG separado", kg is not None and n(kg["totais"]["previsto"]) == DEC("2.5")
                  and n(kg["totais"]["vendido"]) == 2 and n(kg["erro"]["wape"]) == DEC("0.25"),
                  f"{kg and kg['totais']} {kg and kg['erro']}")
        dias = {d["data"]: d for d in (un or {}).get("dias", [])}
        d1, d2 = dias.get(str(D1), {}), dias.get(str(D2), {})
        registrar("T4 dia a dia",
                  len(dias) == 3 and n(d1.get("previsto")) == 15 and n(d1.get("vendido")) == 14
                  and n(d1.get("final")) == 18 and n(d1.get("produzido")) == 20 and n(d2.get("previsto")) == 12
                  and d2.get("sugerido") is None, f"{len(dias)} D1={d1} D2.sugerido={d2.get('sugerido')}")
        prod_pa = next((p for p in b.get("produtos", []) if p["produto"]["codigo"] == "PA"), {})
        registrar("T5 sobra do PA = 12 - 35 - 1 = -24", n(prod_pa.get("sobra")) == DEC(-24) and b.get(
            "produzido_disponivel") is True, f"sobra={prod_pa.get('sobra')}")

        # ---- F ----
        r = get(f"{PERIODO}&loja_id={l2.id}")
        b2 = corpo(r) if r.status_code == 200 else {}
        un2 = next((u for u in b2.get("unidades", []) if u["unidade"] == "UN"), {})
        t2 = {k: n(v) for k, v in un2.get("totais", {}).items()}
        registrar("F1 filtro loja 002: producao fora",
                  b2.get("produzido_disponivel") is False and t2.get("produzido") is None and t2.get("previsto") == 5
                  and t2.get("vendido") == 6 and t2.get("final") == 6 and t2.get("enviado") is None,
                  f"{r.status_code} {t2}")
        r = get(f"{PERIODO}&produto_id={pb.id}")
        unidades = [u["unidade"] for u in corpo(r).get("unidades", [])] if r.status_code == 200 else None
        registrar("F2 filtro produto PB: so KG", unidades == ["KG"], f"{r.status_code} {unidades}")
        s_loja = get(f"{PERIODO}&loja_id={l201.id}").status_code
        s_longo = get(f"data_inicio={D1}&data_fim={D1 + timedelta(days=28)}").status_code
        s_inv = get(f"data_inicio={D3}&data_fim={D1}").status_code
        registrar("F3 loja de outra central 404; periodo longo 422; fim<inicio 422",
                  (s_loja, s_longo, s_inv) == (404, 422, 422), f"{s_loja} {s_longo} {s_inv}")
        r = get()
        ontem = hoje_local() - timedelta(days=1)
        b4 = corpo(r) if r.status_code == 200 else {}
        registrar("F4 padrao: 7 dias ate ontem",
                  b4.get("data_fim") == str(ontem) and b4.get("data_inicio") == str(ontem - timedelta(days=6)),
                  f"{b4.get('data_inicio')} a {b4.get('data_fim')}")

        # ---- I ----
        r = get(PERIODO, token=tgb)
        bb = corpo(r) if r.status_code == 200 else {}
        totais_b = [u["totais"] for u in bb.get("unidades", [])]
        registrar("I1 gestor do negocio B nao ve A", r.status_code == 200 and all(
            n(t["previsto"]) == 999 and n(t["vendido"]) == 999 for t in totais_b) and len(totais_b) == 1,
            f"{r.status_code} {totais_b}")
        ids_b = {p["produto"]["id"] for p in bb.get("produtos", [])}
        registrar("I2 produtos de B so do B", ids_b == {pz.id}, f"{ids_b}")
        d3 = dias.get(str(D3)) or {}
        registrar("I3 venda sem previsao aparece no dia, fora do erro",
                  n(d3.get("previsto")) is None and n(d3.get("vendido")) == 9, f"D3={d3}")
    finally:
        try:
            _limpar(db, negocio_ids)
        finally:
            db.close()

    for linha in resultados:
        print(linha)
    falhas = [x for x in resultados if x.startswith(FAIL)]
    print()
    if len(resultados) != TOTAL_CASOS:
        print(f"ATENCAO: {len(resultados)} casos registrados, esperados {TOTAL_CASOS}.")
        sys.exit(1)
    if falhas:
        print(f"{len(falhas)}/{TOTAL_CASOS} casos FALHARAM")
        sys.exit(1)
    print(f"{TOTAL_CASOS}/{TOTAL_CASOS} casos OK")


if __name__ == "__main__":
    main()
