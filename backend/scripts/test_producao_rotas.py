"""
Testa a API da ordem de produção (Fase 4 / N7) por HTTP, com o TestClient:
autenticação, gerar, listar, detalhar, editar, aprovar, apagar, escopo da
central (D8) e isolamento entre negócios.

A API usa a data de hoje do servidor: o cenário monta as datas a partir de
`date.today()` (D = amanhã, o padrão das rotas). Previsões gravadas com
referência ontem (em dia: a geração não chama o motor).

Cenário: negócio A, central A1 (prazo 0) com L1 e L2; central A2 com L3;
negócio B com LB. Produtos de A: P1 (diário, validade 1, UN; previsão 40
por dia nas duas lojas) e P4 (sem calendário). Usuários: gestor A1, gestor
A2, gestor B, gestor A1 sem acesso web, operador da L1.

Casos:
  A1 sem token -> 401 nas 6 rotas · A2 token do app -> 401 · A3 gestor sem
     acesso web -> 403
  R1 POST /producao/ordens/gerar sem corpo -> amanhã; 2 itens, 4 linhas,
     2 sem quantidade (P4)
  R2 data que já passou, além de D+6 e data inválida -> 422 em português
  C1 GET /producao/ordens (padrão amanhã) -> 1 ordem em rascunho, totais UN
     sugerido 88 e final 88, 0 editadas, 2 sem quantidade
  C2 GET /producao/ordens/{id}: P1 com 44 + 44 e a conta (mínimo 40);
     P4 com aviso sem_calendario
  C3 ordem de A1 pedida pelo gestor A2, pelo gestor B e id inexistente ->
     404 com a mesma resposta · C4 lista do gestor A2 e do B no dia -> vazia
  E1 PATCH da linha P1/L1 para 50 com motivo -> editada; o resumo passa a
     1 editada e final 94 (é o número que a tela mostra antes de regerar, D58)
  E2 PATCH inválido: UN fracionada, negativa, motivo com mais de 255
     caracteres, sem quantidade -> 422
  E3 PATCH de linha pela URL de outra ordem e pelo gestor A2 -> 404
  G1 regerar o rascunho -> 200, substituiu_rascunho, 0 editadas
  P1 aprovar com P4 sem quantidade -> 422, continua rascunho
  P2 informar o P4 e aprovar -> aprovada, aprovado_por = nome do gestor
  P3 ordem aprovada: editar (PATCH), regerar (gerar de novo) e apagar
     (DELETE) -> 409 em cada uma (caso explícito, com o código de cada ação)
  P4 a ordem aprovada continua igual depois das três tentativas
  D1 DELETE de rascunho de outra central -> 404 (não apaga); da própria
     -> 204, e some
  O1 OpenAPI: as 5 rotas existem e nenhuma recebe central_id

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_producao_rotas.py
"""

import re
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import PORTA_WEB, criar_access_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.calendario_producao import CalendarioProducao, DiaSemana  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.estoque_atual import EstoqueAtual  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.ordem_producao import OrdemProducao  # noqa: E402
from app.models.ordem_producao_item import OrdemProducaoItem  # noqa: E402
from app.models.ordem_producao_linha import OrdemProducaoLinha  # noqa: E402
from app.models.previsao_diaria import EstatisticaBase, MetodoPrevisao, PrevisaoDiaria  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 19
PREFIXO_NEGOCIO_TESTE = "_Teste Producao Rotas"
EMAIL_TESTE = re.compile(r"^tpro_[a-z_0-9]+_[0-9a-f]{8}@teste[.]com$")
DEC = Decimal
HOJE = date.today()
D = HOJE + timedelta(days=1)
INEXISTENTE = 2_000_000_000

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
    """Mensagem da resposta, mesmo quando o corpo não é JSON (ex.: erro 500 em texto)."""
    b = corpo(r)
    return str(b.get("detail") if isinstance(b, dict) else b)[:80]


def h(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    lojas = [i for (i,) in db.query(Loja.id).filter(Loja.negocio_id.in_(negocio_ids))]
    db.query(OrdemProducao).filter(OrdemProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (OrdemProducaoLinha, OrdemProducaoItem, PrevisaoDiaria, EstoqueAtual, CalendarioProducao):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    if lojas:
        db.query(ProdutoLoja).filter(ProdutoLoja.loja_id.in_(lojas)).delete(synchronize_session=False)
    db.query(Usuario).filter(Usuario.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Produto).filter(Produto.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Loja).filter(Loja.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(CentralProducao).filter(CentralProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
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

        neg_a = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} A", ativo=True))
        neg_b = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} B", ativo=True))
        negocio_ids = [neg_a.id, neg_b.id]
        a1 = add(CentralProducao(negocio_id=neg_a.id, nome="_A1", ativa=True))
        a2 = add(CentralProducao(negocio_id=neg_a.id, nome="_A2", ativa=True))
        cb = add(CentralProducao(negocio_id=neg_b.id, nome="_B", ativa=True))

        def loja(codigo, neg, central):
            return add(Loja(negocio_id=neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}",
                            codigo=codigo, horario_zeragem=time(6, 0), ativo=True))

        l1, l2, l3 = loja("L1", neg_a, a1), loja("L2", neg_a, a1), loja("L3", neg_a, a2)
        loja("LB", neg_b, cb)

        def usuario(rotulo, neg, **campos):
            padrao = dict(tipo_usuario=TipoUsuario.GESTOR_CENTRAL, tem_acesso_web=True, tem_acesso_app=False)
            padrao.update(campos)
            return add(Usuario(negocio_id=neg.id, nome=f"Gestor {rotulo}", email=f"tpro_{rotulo}_{run}@teste.com",
                               senha_hash=hash_senha("x"), **padrao))

        g_a1 = usuario("a1", neg_a, central_producao_id=a1.id)
        g_a2 = usuario("a2", neg_a, central_producao_id=a2.id)
        g_b = usuario("b", neg_b, central_producao_id=cb.id)
        g_sem_web = usuario("sem_web", neg_a, central_producao_id=a1.id, tem_acesso_web=False)
        operador = usuario("operador", neg_a, tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=l1.id,
                           tem_acesso_web=False, tem_acesso_app=True)

        p1 = add(Produto(negocio_id=neg_a.id, nome="_P1", codigo="P1", unidade_medida=UnidadeMedida.UN, ativo=True,
                         dias_validade=1))
        p4 = add(Produto(negocio_id=neg_a.id, nome="_P4", codigo="P4", unidade_medida=UnidadeMedida.UN, ativo=True,
                         dias_validade=2))
        for d in DiaSemana:
            db.add(CalendarioProducao(negocio_id=neg_a.id, produto_id=p1.id, dia_semana=d))
        for lj in (l1, l2, l3):
            for p in (p1, p4):
                db.add(ProdutoLoja(produto_id=p.id, loja_id=lj.id))
            for k in range(7):
                db.add(PrevisaoDiaria(
                    negocio_id=neg_a.id, central_producao_id=lj.central_producao_id, loja_id=lj.id, produto_id=p1.id,
                    data=HOJE + timedelta(days=k), data_referencia=HOJE - timedelta(days=1), previsao=DEC(40),
                    metodo=MetodoPrevisao.SEMANAL, estatistica=EstatisticaBase.MEDIANA, semanas_na_base=6,
                    tendencia=DEC(1), dias_na_tendencia=7, peso_historico=DEC(1), versao_metodo="teste"))
        # Contagem no fechamento de hoje (21:00 local), gravada em UTC como o app grava.
        contagem = datetime.combine(HOJE, time(21, 0)).astimezone(timezone.utc).replace(tzinfo=None)
        db.add(EstoqueAtual(negocio_id=neg_a.id, loja_id=l1.id, produto_id=p1.id, quantidade_inventariada=12,
                            estoque_atual_calculado=DEC(12), atualizado_em=contagem))
        db.commit()

        tk = lambda u: criar_access_token(u.id, u.negocio_id, porta=PORTA_WEB)  # noqa: E731
        t_a1, t_a2, t_b = tk(g_a1), tk(g_a2), tk(g_b)

        # ---- A: autenticação ----
        rotas = [("post", "/producao/ordens/gerar"), ("get", "/producao/ordens"), ("get", "/producao/ordens/1"),
                 ("patch", "/producao/ordens/1/linhas/1"), ("post", "/producao/ordens/1/aprovar"),
                 ("delete", "/producao/ordens/1")]

        def chamar(metodo, url, token=None, **kw):
            return getattr(cliente, metodo)(url, headers=h(token), **kw)

        sem_token = [chamar(m, u).status_code for m, u in rotas]
        registrar("A1 sem token -> 401", sem_token == [401] * 6, f"{sem_token}")
        app_tk = criar_access_token(operador.id, operador.negocio_id)
        r = chamar("get", "/producao/ordens", app_tk)
        registrar("A2 token do app -> 401", r.status_code == 401, f"{r.status_code}")
        r = chamar("get", "/producao/ordens", tk(g_sem_web))
        registrar("A3 sem acesso web -> 403", r.status_code == 403, f"{r.status_code} {corpo(r)}")

        # ---- R: gerar ----
        r = chamar("post", "/producao/ordens/gerar", t_a1)
        b = corpo(r)
        ordem_id = b.get("ordem_id") if isinstance(b, dict) else None
        ok = (r.status_code == 200 and b["data_producao"] == str(D) and b["data_entrega"] == str(D)
              and b["itens"] == 2 and b["linhas"] == 4 and b["sem_quantidade"] == 2
              and not b["substituiu_rascunho"] and not b["previsao_atualizada"])
        registrar("R1 gerar sem corpo (amanha)", ok, f"{r.status_code} {b}")

        r_passado = chamar("post", "/producao/ordens/gerar", t_a1, json={"data_producao": str(HOJE - timedelta(days=1))})
        r_longe = chamar("post", "/producao/ordens/gerar", t_a1, json={"data_producao": str(HOJE + timedelta(days=7))})
        r_invalida = chamar("post", "/producao/ordens/gerar", t_a1, json={"data_producao": "31/12/2026"})
        ok = all(x.status_code == 422 and isinstance(corpo(x).get("detail"), str) for x in (r_passado, r_longe,
                                                                                              r_invalida))
        registrar("R2 datas invalidas -> 422", ok, " | ".join(f"{x.status_code} {corpo(x).get('detail')}"
                                                             for x in (r_passado, r_longe, r_invalida)))

        # ---- C: consultar ----
        def resumo_do_dia(token, dia=None):
            r_ = chamar("get", "/producao/ordens" + (f"?data={dia}" if dia else ""), token)
            return r_, corpo(r_)

        r, b = resumo_do_dia(t_a1)
        o = b["ordens"][0] if r.status_code == 200 and b["ordens"] else {}
        ok = (r.status_code == 200 and b["data_producao"] == str(D) and len(b["ordens"]) == 1
              and o.get("status") == "rascunho" and o.get("linhas_editadas") == 0
              and o.get("linhas_sem_quantidade") == 2
              and o.get("totais") == [{"unidade": "UN", "sugerido": "88.000", "final": "88.000"}])
        registrar("C1 lista do dia (padrao amanha)", ok, f"{r.status_code} totais={o.get('totais')} "
                  f"editadas={o.get('linhas_editadas')} sem_quantidade={o.get('linhas_sem_quantidade')}")

        r = chamar("get", f"/producao/ordens/{ordem_id}", t_a1)
        b = corpo(r)
        itens = {i["produto"]["codigo"]: i for i in b.get("itens", [])} if r.status_code == 200 else {}
        p1_linhas = {x["loja"]["codigo"]: x for x in itens.get("P1", {}).get("linhas", [])}
        p4_linhas = itens.get("P4", {}).get("linhas", [])
        ok = (r.status_code == 200 and itens.get("P1", {}).get("total_final") == "88.000"
              and p1_linhas.get("L1", {}).get("quantidade_sugerida") == "44.000"
              and DEC(p1_linhas.get("L1", {}).get("componentes", {}).get("minimo", "0")) == DEC(40)
              and all(x["avisos"] == ["sem_calendario"] and x["quantidade_final"] is None for x in p4_linhas)
              and len(p4_linhas) == 2)
        registrar("C2 detalhe da ordem", ok, f"{r.status_code} P1={itens.get('P1', {}).get('total_final')} "
                  f"P4 avisos={[x['avisos'] for x in p4_linhas]}")

        r_a2 = chamar("get", f"/producao/ordens/{ordem_id}", t_a2)
        r_b = chamar("get", f"/producao/ordens/{ordem_id}", t_b)
        r_x = chamar("get", f"/producao/ordens/{INEXISTENTE}", t_a1)
        ok = all(x.status_code == 404 for x in (r_a2, r_b, r_x)) and corpo(r_a2) == corpo(r_b) == corpo(r_x)
        registrar("C3 ordem fora do escopo -> 404 igual", ok, f"{[x.status_code for x in (r_a2, r_b, r_x)]} "
                  f"{corpo(r_a2)}")
        (ra2, ba2), (rb, bb) = resumo_do_dia(t_a2, D), resumo_do_dia(t_b, D)
        registrar("C4 outras centrais nao veem a ordem", ra2.status_code == rb.status_code == 200
                  and ba2["ordens"] == [] and bb["ordens"] == [], f"A2={ba2['ordens']} B={bb['ordens']}")

        # ---- E: editar ----
        linha_l1 = p1_linhas["L1"]["id"]
        url_l1 = f"/producao/ordens/{ordem_id}/linhas/{linha_l1}"
        r = chamar("patch", url_l1, t_a1, json={"quantidade_final": "50", "motivo": "festa no bairro"})
        b = corpo(r)
        _, resumo = resumo_do_dia(t_a1)
        o = resumo["ordens"][0]
        ok = (r.status_code == 200 and b["quantidade_final"] == "50.000" and b["quantidade_sugerida"] == "44.000"
              and b["editada"] and b["motivo_edicao"] == "festa no bairro" and o["linhas_editadas"] == 1
              and o["totais"][0]["final"] == "94.000")
        registrar("E1 editar a linha", ok, f"{r.status_code} final={b.get('quantidade_final')} "
                  f"editadas={o['linhas_editadas']} total_final={o['totais'][0]['final']}")

        invalidos = [chamar("patch", url_l1, t_a1, json=j) for j in (
            {"quantidade_final": "50.5"}, {"quantidade_final": "-1"},
            {"quantidade_final": "1", "motivo": "x" * 256}, {})]
        ok = all(x.status_code == 422 and isinstance(corpo(x).get("detail"), str) for x in invalidos)
        registrar("E2 edicoes invalidas -> 422", ok, " | ".join(f"{x.status_code} {str(corpo(x).get('detail'))[:50]}"
                                                               for x in invalidos))

        r_outra = chamar("patch", f"/producao/ordens/{INEXISTENTE}/linhas/{linha_l1}", t_a1,
                         json={"quantidade_final": "1"})
        r_gestor = chamar("patch", url_l1, t_a2, json={"quantidade_final": "1"})
        r_det = corpo(chamar("get", f"/producao/ordens/{ordem_id}", t_a1))
        final_l1 = next(x["quantidade_final"] for i in r_det["itens"] for x in i["linhas"] if x["id"] == linha_l1)
        registrar("E3 linha por outra URL ou central -> 404", r_outra.status_code == r_gestor.status_code == 404
                  and final_l1 == "50.000", f"{r_outra.status_code} {r_gestor.status_code}; final continua {final_l1}")

        # ---- G1: regerar o rascunho ----
        r = chamar("post", "/producao/ordens/gerar", t_a1, json={"data_producao": str(D)})
        b = corpo(r)
        _, resumo = resumo_do_dia(t_a1)
        ok = (r.status_code == 200 and b["substituiu_rascunho"] and b["ordem_id"] != ordem_id
              and len(resumo["ordens"]) == 1 and resumo["ordens"][0]["linhas_editadas"] == 0)
        registrar("G1 regerar o rascunho", ok, f"{r.status_code} ordem {ordem_id} -> {b.get('ordem_id')}")
        ordem_id = b["ordem_id"]

        # ---- P: aprovar ----
        r = chamar("post", f"/producao/ordens/{ordem_id}/aprovar", t_a1)
        _, resumo = resumo_do_dia(t_a1)
        registrar("P1 aprovar sem quantidade -> 422", r.status_code == 422
                  and resumo["ordens"][0]["status"] == "rascunho", f"{r.status_code} {corpo(r)}")
        det = corpo(chamar("get", f"/producao/ordens/{ordem_id}", t_a1))
        for item in det["itens"]:
            for x in item["linhas"]:
                if x["quantidade_final"] is None:
                    chamar("patch", f"/producao/ordens/{ordem_id}/linhas/{x['id']}", t_a1,
                           json={"quantidade_final": "0"})
        r = chamar("post", f"/producao/ordens/{ordem_id}/aprovar", t_a1)
        b = corpo(r)
        registrar("P2 aprovar", r.status_code == 200 and b["status"] == "aprovada"
                  and b["aprovado_por"] == "Gestor a1" and b["aprovado_em"] is not None,
                  f"{r.status_code} status={b.get('status')} aprovado_por={b.get('aprovado_por')}")

        antes = corpo(chamar("get", f"/producao/ordens/{ordem_id}", t_a1))
        linha_qualquer = antes["itens"][0]["linhas"][0]["id"]
        r_patch = chamar("patch", f"/producao/ordens/{ordem_id}/linhas/{linha_qualquer}", t_a1,
                         json={"quantidade_final": "1"})
        r_gerar = chamar("post", "/producao/ordens/gerar", t_a1, json={"data_producao": str(D)})
        r_del = chamar("delete", f"/producao/ordens/{ordem_id}", t_a1)
        acoes = {"editar": r_patch, "regerar": r_gerar, "apagar": r_del}
        codigos = {nome: x.status_code for nome, x in acoes.items()}
        registrar("P3 ordem aprovada: editar, regerar e apagar -> 409", all(c == 409 for c in codigos.values()),
                  "; ".join(f"{nome} {x.status_code} {detalhe(x)}" for nome, x in acoes.items()))
        depois = corpo(chamar("get", f"/producao/ordens/{ordem_id}", t_a1))
        registrar("P4 ordem aprovada continua intacta", depois == antes,
                  "igual antes e depois" if depois == antes else "mudou")

        # ---- D1: apagar ----
        dia2 = HOJE + timedelta(days=2)
        b = corpo(chamar("post", "/producao/ordens/gerar", t_a1, json={"data_producao": str(dia2)}))
        rascunho = b["ordem_id"]
        r_outro = chamar("delete", f"/producao/ordens/{rascunho}", t_a2)
        ainda = chamar("get", f"/producao/ordens/{rascunho}", t_a1).status_code
        r_del = chamar("delete", f"/producao/ordens/{rascunho}", t_a1)
        sumiu = chamar("get", f"/producao/ordens/{rascunho}", t_a1).status_code
        registrar("D1 apagar rascunho", r_outro.status_code == 404 and ainda == 200 and r_del.status_code == 204
                  and sumiu == 404, f"outra central {r_outro.status_code}, ainda {ainda}; própria {r_del.status_code}, "
                  f"depois {sumiu}")

        # ---- O1: OpenAPI ----
        spec = cliente.get("/openapi.json").json()
        caminhos = {p: list(m) for p, m in spec["paths"].items() if p.startswith("/producao")}
        esperado = {"/producao/ordens/gerar": ["post"], "/producao/ordens": ["get"],
                    "/producao/ordens/{ordem_id}": ["get", "delete"],
                    "/producao/ordens/{ordem_id}/linhas/{linha_id}": ["patch"],
                    "/producao/ordens/{ordem_id}/aprovar": ["post"],
                    # N9b (D67): impressão e lista de setores.
                    "/producao/ordens/{ordem_id}/pdf": ["get"], "/producao/setores": ["get", "post"],
                    # Fase 6 / C1 (D102): cadastro de setores.
                    "/producao/setores/{setor_id}": ["patch"]}
        parametros = [x["name"] for p, m in spec["paths"].items() if p.startswith("/producao")
                      for op in m.values() for x in op.get("parameters", [])]
        ok = ({p: sorted(m) for p, m in caminhos.items()} == {p: sorted(m) for p, m in esperado.items()}
              and not any("central" in nome for nome in parametros))
        registrar("O1 OpenAPI sem central_id", ok, f"{sorted(caminhos)}; parâmetros={sorted(set(parametros))}")
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste da API da ordem de produção (N7) ===")
            for linha in resultados:
                print(linha)
            falhas = [x for x in resultados if x.startswith(FAIL)]
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

    if len(resultados) < TOTAL_CASOS or any(x.startswith(FAIL) for x in resultados):
        sys.exit(1)


if __name__ == "__main__":
    main()
