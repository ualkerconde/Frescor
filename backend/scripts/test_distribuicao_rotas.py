"""
Testa a API da distribuição do SaaS (Fase 5 / E6, D82) por HTTP, com o
TestClient: autenticação, produção real, romaneio (listar, gerar,
detalhar, ajustar, aprovar, apagar), saída, divergências, escopo da
central e isolamento entre negócios; códigos 404/409/422 (D65).

Cenário: negócio A, central A1 com L1 (001) e L2 (002); central A2 com L3;
negócio B. Ordens montadas direto no banco (a geração da ordem é da Fase 4):
  OA (A1, aprovada, entrega amanhã): PA (UN) finais 6 / 4; PB (KG) 2,5 / 1,5
  OR (A1, rascunho, entrega depois de amanhã): PA 3 na L1
  O2 (A2, aprovada, entrega amanhã): PA 5 na L3
  OB (negócio B, aprovada): PX 5
Conta à mão: produção PA 8 (planejado 10) -> 8 x 6/10 = 4,8 e 8 x 4/10 =
3,2 -> 4/3 + 1 para o maior resto (L1) -> 5 / 3. PB 4,0 = planejado -> 2,5
/ 1,5, sem rateio.

Casos:
  A1 sem token -> 401 nas 10 rotas · A2 token do app -> 401 · A3 gestor sem
     acesso web -> 403
  P1 registrar a produção da OA -> 200, 2 itens
  P2 produção inválida (UN fracionada, item repetido, item de outra ordem,
     lista vazia) -> 422/404 em português, nada gravado
  P3 produção da ordem em rascunho -> 409
  P4 produção da OA pelo gestor A2, pelo gestor B e de ordem inexistente ->
     404 com a mesma resposta
  L1 GET /distribuicao/romaneios?data_entrega=amanhã -> a OA com planejado e
     produzido de cada produto, sem romaneio; o gestor A2 vê só a O2
  G1 gerar o romaneio da OA -> 200, 2 entregas, 4 itens, escassez no PA
  G2 gerar da ordem em rascunho -> 409; da O2 pelo gestor A1 -> 404; sem
     corpo -> 422
  D1 detalhe: entregas 001 e 002 na ordem do código, PA 5 / 3, PB 2,5 / 1,5,
     "aguardando_saida", não desatualizado
  D2 detalhe pelo gestor A2, pelo gestor B e inexistente -> 404 igual
  E1 PATCH L1/PA para 4 com motivo -> 200, final 4, sugerida 5
  E2 PATCH inválido (UN fracionada, negativa, motivo > 255, sem quantidade)
     -> 422 em português
  E3 PATCH pela URL da OA de um item de outro romaneio da mesma central
     (OC, A1, entrega depois de amanhã) e de um da O2; PATCH pelo gestor A2
     -> 404, e nenhum item muda (lição do N7)
  U1 corrigir a produção com o rascunho -> romaneio_desatualizado; o
     detalhe diz "desatualizado"; gerar de novo -> substituiu, ajuste perdido
  R1 aprovar com Σ PA (6 + 3 = 9) acima do produzido (8) -> 422 citando o
     produto; corrigir para 5 e aprovar -> 200 "aprovado"
  R2 romaneio aprovado: ajustar, gerar de novo, apagar e mudar a produção ->
     409 em cada um
  S0 saída de romaneio em rascunho (O2) -> 409
  S1 saída da L1 -> 200; a L1 "a_caminho"
  S2 saída da L1 de novo -> 409
  S3 saída com uma entrega de outro romaneio (da A2) -> 404, nada sai
  S4 saída sem corpo -> a L2 (a que faltava); de novo -> 409
  V1 divergências: a L1 confirma 4 de 5 (falta) -> 1 linha, diferença −1,
     total UN; o gestor A2 não vê; período invertido e longo -> 422
  X1 apagar o rascunho da O2 pelo gestor A1 -> 404 (não apaga); pelo A2 ->
     204
  O1 OpenAPI: as 10 rotas (com o PDF do E8) existem e nenhuma recebe central_id

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_distribuicao_rotas.py
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
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida  # noqa: E402
from app.models.romaneio import Romaneio  # noqa: E402
from app.models.romaneio_entrega import RomaneioEntrega  # noqa: E402
from app.models.romaneio_item import RomaneioItem  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402
from app.services.recebimento_service import DiferencaItem, confirmar  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 26
PREFIXO_NEGOCIO_TESTE = "_Teste Distribuicao Rotas"
DEC = Decimal
HOJE = date.today()
AMANHA = HOJE + timedelta(days=1)
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
    b = corpo(r)
    return str(b.get("detail") if isinstance(b, dict) else b)[:90]


def h(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    db.query(Romaneio).filter(Romaneio.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (RomaneioItem, RomaneioEntrega):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(OrdemProducao).filter(OrdemProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (OrdemProducaoLinha, OrdemProducaoItem, Usuario, Produto, Loja, CentralProducao):
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

        neg_a = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} A", ativo=True))
        neg_b = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} B", ativo=True))
        negocio_ids = [neg_a.id, neg_b.id]
        a1 = add(CentralProducao(negocio_id=neg_a.id, nome="_A1", ativa=True, prazo_entrega_dias=1))
        a2 = add(CentralProducao(negocio_id=neg_a.id, nome="_A2", ativa=True, prazo_entrega_dias=1))
        cb = add(CentralProducao(negocio_id=neg_b.id, nome="_B", ativa=True))

        def loja(codigo, neg, central):
            return add(Loja(negocio_id=neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}",
                            codigo=codigo, horario_zeragem=time(6, 0), ativo=True))

        l1, l2, l3, lb = loja("001", neg_a, a1), loja("002", neg_a, a1), loja("003", neg_a, a2), loja("B1", neg_b, cb)

        def usuario(rotulo, neg, **campos):
            padrao = dict(tipo_usuario=TipoUsuario.GESTOR_CENTRAL, tem_acesso_web=True, tem_acesso_app=False)
            padrao.update(campos)
            return add(Usuario(negocio_id=neg.id, nome=f"Gestor {rotulo}", email=f"tdr_{rotulo}_{run}@teste.com",
                               senha_hash=hash_senha("x"), **padrao))

        g_a1 = usuario("a1", neg_a, central_producao_id=a1.id)
        g_a2 = usuario("a2", neg_a, central_producao_id=a2.id)
        g_b = usuario("b", neg_b, central_producao_id=cb.id)
        g_sem_web = usuario("sem_web", neg_a, central_producao_id=a1.id, tem_acesso_web=False)
        op_l1 = usuario("op1", neg_a, tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=l1.id, tem_acesso_web=False,
                        tem_acesso_app=True)

        def produto(neg, codigo, unidade):
            return add(Produto(negocio_id=neg.id, nome=f"_Produto {codigo}", codigo=codigo, unidade_medida=unidade,
                               ativo=True, tipo_abastecimento=TipoAbastecimento.PRODUZIDO))

        pa, pb, px = produto(neg_a, "PA", UnidadeMedida.UN), produto(neg_a, "PB", UnidadeMedida.KG), \
            produto(neg_b, "PX", UnidadeMedida.UN)
        agora = datetime.utcnow()

        def ordem(neg, central, producao, entrega, aprovada, itens):
            o = add(OrdemProducao(
                negocio_id=neg.id, central_producao_id=central.id, data_producao=producao, data_entrega=entrega,
                versao_metodo="teste", gerado_em=agora,
                status=StatusOrdemProducao.APROVADA if aprovada else StatusOrdemProducao.RASCUNHO,
                aprovado_em=agora if aprovada else None, aprovado_por_usuario_id=g_a1.id if aprovada else None))
            ids = {}
            for prod, linhas in itens.items():
                item = add(OrdemProducaoItem(negocio_id=neg.id, ordem_id=o.id, produto_id=prod.id,
                                             tipo_abastecimento=prod.tipo_abastecimento, unidade=prod.unidade_medida))
                ids[prod.codigo] = item.id
                for lj, final in linhas:
                    add(OrdemProducaoLinha(negocio_id=neg.id, item_id=item.id, loja_id=lj.id,
                                           quantidade_sugerida=DEC(final), quantidade_final=DEC(final)))
            return o, ids

        oa, oa_itens = ordem(neg_a, a1, HOJE, AMANHA, True, {pa: [(l1, "6"), (l2, "4")],
                                                             pb: [(l1, "2.5"), (l2, "1.5")]})
        o_r, or_itens = ordem(neg_a, a1, AMANHA, AMANHA + timedelta(days=1), False, {pa: [(l1, "3")]})
        o2, o2_itens = ordem(neg_a, a2, HOJE, AMANHA, True, {pa: [(l3, "5")]})
        ob, ob_itens = ordem(neg_b, cb, HOJE, HOJE, True, {px: [(lb, "5")]})
        oc, oc_itens = ordem(neg_a, a1, AMANHA + timedelta(days=1), AMANHA + timedelta(days=2), True,
                             {pa: [(l1, "2")]})
        db.commit()

        tk = lambda u: criar_access_token(u.id, u.negocio_id, porta=PORTA_WEB)  # noqa: E731
        t_a1, t_a2, t_b = tk(g_a1), tk(g_a2), tk(g_b)

        def chamar(metodo, url, token=None, **kw):
            return getattr(cliente, metodo)(url, headers=h(token), **kw)

        # ---- A: autenticação ----
        rotas = [("post", "/distribuicao/ordens/1/producao"), ("get", "/distribuicao/romaneios"),
                 ("post", "/distribuicao/romaneios/gerar"), ("get", "/distribuicao/romaneios/1"),
                 ("patch", "/distribuicao/romaneios/1/itens/1"), ("post", "/distribuicao/romaneios/1/aprovar"),
                 ("delete", "/distribuicao/romaneios/1"), ("post", "/distribuicao/romaneios/1/saida"),
                 ("get", "/distribuicao/romaneios/1/pdf"), ("get", "/distribuicao/divergencias")]
        sem_token = [chamar(m, u).status_code for m, u in rotas]
        registrar("A1 sem token -> 401", sem_token == [401] * len(rotas), f"{sem_token}")
        r = chamar("get", "/distribuicao/romaneios", criar_access_token(op_l1.id, op_l1.negocio_id))
        registrar("A2 token do app -> 401", r.status_code == 401, f"{r.status_code}")
        r = chamar("get", "/distribuicao/romaneios", tk(g_sem_web))
        registrar("A3 sem acesso web -> 403", r.status_code == 403, f"{r.status_code} {detalhe(r)}")

        def producao_oa():
            db.expire_all()
            return {k: db.get(OrdemProducaoItem, i).quantidade_produzida for k, i in oa_itens.items()}

        # ---- P: produção ----
        url_prod = f"/distribuicao/ordens/{oa.id}/producao"
        r = chamar("post", url_prod, t_a1, json={"itens": [{"item_id": oa_itens["PA"], "quantidade": "8"},
                                                          {"item_id": oa_itens["PB"], "quantidade": "4.0"}]})
        registrar("P1 registrar producao", r.status_code == 200 and corpo(r) == {"itens_registrados": 2,
                                                                                "romaneio_desatualizado": False}
                  and producao_oa() == {"PA": DEC("8.000"), "PB": DEC("4.000")}, f"{r.status_code} {corpo(r)}")
        tentativas = {
            "UN fracionada": (chamar("post", url_prod, t_a1, json={"itens": [{"item_id": oa_itens["PA"],
                                                                            "quantidade": "7.5"}]}), 422),
            "item repetido": (chamar("post", url_prod, t_a1, json={"itens": [
                {"item_id": oa_itens["PA"], "quantidade": "7"}, {"item_id": oa_itens["PA"], "quantidade": "6"}]}), 422),
            "item de outra ordem": (chamar("post", url_prod, t_a1, json={"itens": [{"item_id": o2_itens["PA"],
                                                                                  "quantidade": "1"}]}), 404),
            "lista vazia": (chamar("post", url_prod, t_a1, json={"itens": []}), 422),
        }
        ok = all(x.status_code == esperado and isinstance(corpo(x).get("detail"), str)
                 for x, esperado in tentativas.values()) and producao_oa() == {"PA": DEC("8.000"), "PB": DEC("4.000")}
        registrar("P2 producao invalida", ok, "; ".join(f"{k} {x.status_code} {detalhe(x)[:45]}"
                                                         for k, (x, _) in tentativas.items()))
        r = chamar("post", f"/distribuicao/ordens/{o_r.id}/producao", t_a1,
                   json={"itens": [{"item_id": or_itens["PA"], "quantidade": "3"}]})
        registrar("P3 producao de ordem em rascunho -> 409", r.status_code == 409, f"{r.status_code} {detalhe(r)}")
        respostas = [chamar("post", url_prod, t, json={"itens": [{"item_id": oa_itens["PA"], "quantidade": "1"}]})
                     for t in (t_a2, t_b)]
        respostas.append(chamar("post", f"/distribuicao/ordens/{INEXISTENTE}/producao", t_a1,
                                json={"itens": [{"item_id": oa_itens["PA"], "quantidade": "1"}]}))
        registrar("P4 producao fora do escopo -> 404 igual",
                  [x.status_code for x in respostas] == [404] * 3 and len({x.text for x in respostas}) == 1
                  and producao_oa()["PA"] == DEC("8.000"), f"{[x.status_code for x in respostas]} {detalhe(respostas[0])}")

        # ---- L1: o dia de entrega ----
        r = chamar("get", f"/distribuicao/romaneios?data_entrega={AMANHA}", t_a1)
        b = corpo(r)
        ordens = b.get("ordens", []) if isinstance(b, dict) else []
        itens = {i["produto"]["codigo"]: (i["planejado"], i["produzido"]) for i in (ordens[0]["itens"] if ordens else [])}
        r2 = chamar("get", f"/distribuicao/romaneios?data_entrega={AMANHA}", t_a2)
        ordens_a2 = [o["ordem_id"] for o in corpo(r2).get("ordens", [])]
        registrar("L1 ordens do dia de entrega",
                  r.status_code == 200 and [o["ordem_id"] for o in ordens] == [oa.id]
                  and itens == {"PA": ("10.000", "8.000"), "PB": ("4.000", "4.000")} and ordens[0]["romaneio"] is None
                  and ordens_a2 == [o2.id],
                  f"A1 {[o['ordem_id'] for o in ordens]} {itens}; A2 {ordens_a2}")

        # ---- G: gerar ----
        r = chamar("post", "/distribuicao/romaneios/gerar", t_a1, json={"ordem_id": oa.id})
        b = corpo(r)
        rom_id = b.get("romaneio_id") if isinstance(b, dict) else None
        registrar("G1 gerar romaneio", r.status_code == 200 and b["entregas"] == 2 and b["itens"] == 4
                  and b["produtos_com_escassez"] == [pa.id] and not b["substituiu_rascunho"], f"{r.status_code} {b}")
        r_rasc = chamar("post", "/distribuicao/romaneios/gerar", t_a1, json={"ordem_id": o_r.id})
        r_outra = chamar("post", "/distribuicao/romaneios/gerar", t_a1, json={"ordem_id": o2.id})
        r_sem = chamar("post", "/distribuicao/romaneios/gerar", t_a1)
        registrar("G2 gerar recusado", (r_rasc.status_code, r_outra.status_code, r_sem.status_code) == (409, 404, 422)
                  and isinstance(corpo(r_sem).get("detail"), str),
                  f"rascunho {r_rasc.status_code}, outra central {r_outra.status_code}, sem corpo {r_sem.status_code}"
                  f" {detalhe(r_sem)}")
        # Romaneio da O2 (central A2), para os casos de escopo.
        chamar("post", f"/distribuicao/ordens/{o2.id}/producao", t_a2,
               json={"itens": [{"item_id": o2_itens["PA"], "quantidade": "5"}]})
        rom2_id = corpo(chamar("post", "/distribuicao/romaneios/gerar", t_a2, json={"ordem_id": o2.id}))["romaneio_id"]
        rom2 = corpo(chamar("get", f"/distribuicao/romaneios/{rom2_id}", t_a2))
        item_o2 = rom2["entregas"][0]["itens"][0]["id"]
        entrega_o2 = rom2["entregas"][0]["id"]
        # Romaneio da OC (mesma central A1, outro dia), para o item de outro romaneio da mesma central.
        chamar("post", f"/distribuicao/ordens/{oc.id}/producao", t_a1,
               json={"itens": [{"item_id": oc_itens["PA"], "quantidade": "2"}]})
        romc_id = corpo(chamar("post", "/distribuicao/romaneios/gerar", t_a1, json={"ordem_id": oc.id}))["romaneio_id"]
        item_oc = corpo(chamar("get", f"/distribuicao/romaneios/{romc_id}", t_a1))["entregas"][0]["itens"][0]["id"]

        # ---- D: detalhe ----
        def detalhe_rom(token=t_a1, rid=None):
            return chamar("get", f"/distribuicao/romaneios/{rid or rom_id}", token)

        b = corpo(detalhe_rom())
        tabela = {(e["loja"]["codigo"], i["produto"]["codigo"]): (i["quantidade_sugerida"], i["quantidade_final"])
                  for e in b["entregas"] for i in e["itens"]}
        registrar("D1 detalhe do romaneio",
                  [e["loja"]["codigo"] for e in b["entregas"]] == ["001", "002"]
                  and tabela == {("001", "PA"): ("5.000", "5.000"), ("002", "PA"): ("3.000", "3.000"),
                                 ("001", "PB"): ("2.500", "2.500"), ("002", "PB"): ("1.500", "1.500")}
                  and all(e["situacao"]["situacao"] == "aguardando_saida" for e in b["entregas"])
                  and b["status"] == "rascunho" and not b["desatualizado"],
                  f"{tabela}; situacoes {[e['situacao']['situacao'] for e in b['entregas']]}")
        ent = {e["loja"]["codigo"]: e for e in b["entregas"]}
        item_l1_pa = next(i["id"] for i in ent["001"]["itens"] if i["produto"]["codigo"] == "PA")
        respostas = [detalhe_rom(t_a2), detalhe_rom(t_b), detalhe_rom(t_a1, INEXISTENTE)]
        registrar("D2 detalhe fora do escopo -> 404 igual",
                  [x.status_code for x in respostas] == [404] * 3 and len({x.text for x in respostas}) == 1,
                  f"{[x.status_code for x in respostas]} {detalhe(respostas[0])}")

        # ---- E: ajustar ----
        url_item = f"/distribuicao/romaneios/{rom_id}/itens/{item_l1_pa}"
        r = chamar("patch", url_item, t_a1, json={"quantidade_final": "4", "motivo": "loja pediu menos"})
        b = corpo(r)
        it = next((i for e in b.get("entregas", []) for i in e["itens"] if i["id"] == item_l1_pa), {})
        registrar("E1 ajustar item", r.status_code == 200 and it.get("quantidade_final") == "4.000"
                  and it.get("quantidade_sugerida") == "5.000" and it.get("motivo_edicao") == "loja pediu menos",
                  f"{r.status_code} final {it.get('quantidade_final')} sugerida {it.get('quantidade_sugerida')}")
        invalidos = [chamar("patch", url_item, t_a1, json=j) for j in (
            {"quantidade_final": "4.5"}, {"quantidade_final": "-1"}, {"quantidade_final": "4", "motivo": "x" * 256},
            {})]
        registrar("E2 ajuste invalido -> 422", [x.status_code for x in invalidos] == [422] * 4
                  and all(isinstance(corpo(x).get("detail"), str) for x in invalidos),
                  "; ".join(f"{x.status_code} {detalhe(x)[:40]}" for x in invalidos))

        def final_item(item_id):
            db.expire_all()
            return db.get(RomaneioItem, item_id).quantidade_final

        r_url = chamar("patch", f"/distribuicao/romaneios/{rom_id}/itens/{item_oc}", t_a1, json={"quantidade_final": "1"})
        r_o2 = chamar("patch", f"/distribuicao/romaneios/{rom_id}/itens/{item_o2}", t_a1, json={"quantidade_final": "1"})
        r_a2 = chamar("patch", url_item, t_a2, json={"quantidade_final": "1"})
        registrar("E3 item de outro romaneio ou central -> 404",
                  (r_url.status_code, r_o2.status_code, r_a2.status_code) == (404, 404, 404)
                  and final_item(item_oc) == DEC(2) and final_item(item_o2) == DEC(5)
                  and final_item(item_l1_pa) == DEC(4),
                  f"mesma central {r_url.status_code}, outra central {r_o2.status_code}, gestor A2 {r_a2.status_code};"
                  f" itens {final_item(item_oc)}, {final_item(item_o2)} e {final_item(item_l1_pa)}")

        # ---- U1: produção corrigida com o rascunho (D87) ----
        r = chamar("post", url_prod, t_a1, json={"itens": [{"item_id": oa_itens["PA"], "quantidade": "8"}]})
        desat = corpo(detalhe_rom())["desatualizado"]
        r_g = chamar("post", "/distribuicao/romaneios/gerar", t_a1, json={"ordem_id": oa.id})
        rom_id = corpo(r_g)["romaneio_id"]
        b = corpo(detalhe_rom())
        ent = {e["loja"]["codigo"]: e for e in b["entregas"]}
        item_l1_pa = next(i["id"] for i in ent["001"]["itens"] if i["produto"]["codigo"] == "PA")
        final_l1 = next(i["quantidade_final"] for i in ent["001"]["itens"] if i["produto"]["codigo"] == "PA")
        registrar("U1 producao corrigida e gerar de novo",
                  corpo(r)["romaneio_desatualizado"] and desat and corpo(r_g)["substituiu_rascunho"]
                  and not b["desatualizado"] and final_l1 == "5.000",
                  f"aviso {corpo(r)['romaneio_desatualizado']}, detalhe desatualizado {desat}; de novo: final L1 {final_l1}")

        # ---- R: aprovar ----
        url_item = f"/distribuicao/romaneios/{rom_id}/itens/{item_l1_pa}"
        chamar("patch", url_item, t_a1, json={"quantidade_final": "6"})
        r = chamar("post", f"/distribuicao/romaneios/{rom_id}/aprovar", t_a1)
        acima = (r.status_code, detalhe(r))
        chamar("patch", url_item, t_a1, json={"quantidade_final": "5"})
        r = chamar("post", f"/distribuicao/romaneios/{rom_id}/aprovar", t_a1)
        registrar("R1 aprovar", acima[0] == 422 and "_Produto PA" in acima[1] and r.status_code == 200
                  and corpo(r)["status"] == "aprovado" and corpo(r)["aprovado_em"],
                  f"acima do produzido {acima}; depois {r.status_code} {corpo(r).get('status')}")
        travado = {
            "ajustar": chamar("patch", url_item, t_a1, json={"quantidade_final": "1"}).status_code,
            "gerar": chamar("post", "/distribuicao/romaneios/gerar", t_a1, json={"ordem_id": oa.id}).status_code,
            "apagar": chamar("delete", f"/distribuicao/romaneios/{rom_id}", t_a1).status_code,
            "producao": chamar("post", url_prod, t_a1, json={"itens": [{"item_id": oa_itens["PA"],
                                                                       "quantidade": "1"}]}).status_code,
        }
        registrar("R2 romaneio aprovado travado -> 409", list(travado.values()) == [409] * 4
                  and final_item(item_l1_pa) == DEC(5) and producao_oa()["PA"] == DEC("8.000"), f"{travado}")

        # ---- S: saída ----
        r = chamar("post", f"/distribuicao/romaneios/{rom2_id}/saida", t_a2)
        registrar("S0 saida de rascunho -> 409", r.status_code == 409, f"{r.status_code} {detalhe(r)}")
        url_saida = f"/distribuicao/romaneios/{rom_id}/saida"
        id_l1, id_l2 = ent["001"]["id"], ent["002"]["id"]
        r = chamar("post", url_saida, t_a1, json={"entrega_ids": [id_l1]})
        sit = {e["loja"]["codigo"]: e["situacao"]["situacao"] for e in corpo(detalhe_rom())["entregas"]}
        registrar("S1 saida da L1", r.status_code == 200 and corpo(r) == {"entregas": [id_l1]}
                  and sit == {"001": "a_caminho", "002": "aguardando_saida"}, f"{r.status_code} {corpo(r)} {sit}")
        r = chamar("post", url_saida, t_a1, json={"entrega_ids": [id_l1]})
        registrar("S2 saida repetida -> 409", r.status_code == 409 and "_Loja 001" in detalhe(r),
                  f"{r.status_code} {detalhe(r)}")
        r = chamar("post", url_saida, t_a1, json={"entrega_ids": [id_l2, entrega_o2]})
        sit = {e["loja"]["codigo"]: e["situacao"]["situacao"] for e in corpo(detalhe_rom())["entregas"]}
        sit_o2 = corpo(detalhe_rom(t_a2, rom2_id))["entregas"][0]["situacao"]["situacao"]
        registrar("S3 saida com entrega de outra central -> 404, nada sai",
                  r.status_code == 404 and sit["002"] == "aguardando_saida" and sit_o2 == "aguardando_saida",
                  f"{r.status_code} {detalhe(r)}; 002 {sit['002']}, O2 {sit_o2}")
        r = chamar("post", url_saida, t_a1)
        r_de_novo = chamar("post", url_saida, t_a1)
        registrar("S4 saida das que faltam", r.status_code == 200 and corpo(r) == {"entregas": [id_l2]}
                  and r_de_novo.status_code == 409, f"{r.status_code} {corpo(r)}; de novo {r_de_novo.status_code}")

        # ---- V1: divergências ----
        item_l1 = next(i["id"] for i in ent["001"]["itens"] if i["produto"]["codigo"] == "PA")
        confirmar(db, neg_a.id, l1.id, id_l1, op_l1.id, {item_l1: DiferencaItem(DEC(4), "falta")})
        url_div = f"/distribuicao/divergencias?data_inicio={HOJE}&data_fim={AMANHA}"
        b = corpo(chamar("get", url_div, t_a1))
        linhas = [(d["loja"]["codigo"], d["produto"]["codigo"], d["quantidade_enviada"], d["quantidade_recebida"],
                   d["diferenca"], d["motivo"]) for d in b.get("divergencias", [])]
        vazio_a2 = corpo(chamar("get", url_div, t_a2)).get("divergencias")
        invertido = chamar("get", f"/distribuicao/divergencias?data_inicio={AMANHA}&data_fim={HOJE}", t_a1)
        longo = chamar("get", f"/distribuicao/divergencias?data_inicio={HOJE - timedelta(days=120)}&data_fim={HOJE}",
                       t_a1)
        registrar("V1 divergencias",
                  linhas == [("001", "PA", "5.000", "4.000", "-1.000", "falta")]
                  and b["totais"] == [{"unidade": "UN", "enviada": "5.000", "recebida": "4.000", "diferenca": "-1.000"}]
                  and vazio_a2 == [] and (invertido.status_code, longo.status_code) == (422, 422),
                  f"{linhas}; totais {b.get('totais')}; A2 {vazio_a2}; invertido {invertido.status_code} "
                  f"{detalhe(invertido)}; longo {longo.status_code}")

        # ---- X1: apagar ----
        r_a1 = chamar("delete", f"/distribuicao/romaneios/{rom2_id}", t_a1)
        existe = detalhe_rom(t_a2, rom2_id).status_code
        r_a2 = chamar("delete", f"/distribuicao/romaneios/{rom2_id}", t_a2)
        some = detalhe_rom(t_a2, rom2_id).status_code
        registrar("X1 apagar rascunho", (r_a1.status_code, existe, r_a2.status_code, some) == (404, 200, 204, 404),
                  f"pelo A1 {r_a1.status_code} (continua {existe}); pelo A2 {r_a2.status_code} (depois {some})")

        # ---- O1: OpenAPI ----
        esquema = cliente.get("/openapi.json").json()
        caminhos = {p: ops for p, ops in esquema["paths"].items() if p.startswith("/distribuicao")}
        esperados = {"/distribuicao/ordens/{ordem_id}/producao", "/distribuicao/romaneios",
                     "/distribuicao/romaneios/gerar", "/distribuicao/romaneios/{romaneio_id}",
                     "/distribuicao/romaneios/{romaneio_id}/itens/{item_id}",
                     "/distribuicao/romaneios/{romaneio_id}/aprovar", "/distribuicao/romaneios/{romaneio_id}/saida",
                     "/distribuicao/romaneios/{romaneio_id}/pdf", "/distribuicao/divergencias"}
        parametros = {p["name"] for ops in caminhos.values() for op in ops.values() for p in op.get("parameters", [])}
        registrar("O1 OpenAPI sem central_id", esperados <= set(caminhos) and "central_id" not in parametros
                  and "central_producao_id" not in parametros, f"{len(caminhos)} caminhos; parametros {sorted(parametros)}")
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste da API da distribuição (E6) ===")
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
