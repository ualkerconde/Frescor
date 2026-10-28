"""
Testa a API do recebimento no app (Fase 5 / E7, D77, D82) por HTTP, com o
TestClient: autenticação do app (`obter_usuario_autenticado`), lista,
detalhe e confirmação, sempre pela loja do token.

Exigência do Ualker (lição da SB3 do E2): as entregas são DIFERENTES por
loja (produtos e quantidades), para que um operador ligado à loja errada
seja pego pelo que vê, não só pelo perfil.

Cenário: negócio A, central A1 (lojas 001, 002, 003); negócio B.
Ordem OA (aprovada, entrega hoje), romaneio aprovado (produção = planejado):
  001: PA 5 un e PB 2,0 kg · 002: PC 7 un · 003: PA 1 un (sem saída)
Saída da 001 primeiro; a da 002 depois do caso L1.

Casos:
  A1 sem token -> 403 nas 3 rotas (comportamento antigo do app, mantido)
  A2 token do SaaS (gestor) -> 401
  A3 gestor com token do app -> 403
  A4 operador sem acesso ao app -> 403
  L1 o operador da 001 vê a entrega da 001 (PA 5, PB 2,0); o da 002 não vê
     nada (sem saída); o da 003 não vê nada
  L2 depois da saída da 002, o operador da 002 vê só a 002, com PC 7 (outro
     produto, outra quantidade); o da 001 continua vendo só a 001
  L3 `?loja_id=` da outra loja na URL é ignorado (a loja vem do token)
  V1 detalhe da entrega da 001 pelo operador da 002 e pelo do negócio B ->
     404; pelo da 001 -> 200
  V2 detalhe da entrega sem saída (003) -> 404
  C1 o operador da 002 confirma a entrega da 001 -> 404, nada gravado
  C2 confirmações inválidas (diferença sem motivo, motivo inválido, item
     repetido, UN fracionada) -> 422 em português, nada gravado
  C3 entrega sem saída (003) -> 409
  C4 o operador da 001 confirma com diferença (PB 1,5 kg, avaria) -> 200,
     "recebida" com diferença; PA 5 (não informado = igual ao enviado)
  C5 confirmar de novo -> 409
  C6 o operador da 002 confirma "tudo certo" (sem corpo) -> 200, PC 7
  C7 depois de confirmar, a lista das duas lojas fica vazia
  O1 OpenAPI: as rotas existem e nenhuma recebe loja_id

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_recebimentos_rotas.py
"""

import sys
import uuid
from datetime import date, datetime, time
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
from app.models.romaneio_entrega import RomaneioEntrega, SituacaoEntrega  # noqa: E402
from app.models.romaneio_item import RomaneioItem  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402
from app.services.distribuicao_service import (  # noqa: E402
    aprovar_romaneio,
    gerar_romaneio,
    registrar_producao,
    registrar_saida,
)

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 17
PREFIXO_NEGOCIO_TESTE = "_Teste Recebimentos Rotas"
DEC = Decimal
HOJE = date.today()

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
    return str(b.get("detail") if isinstance(b, dict) else b)[:80]


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

        neg = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} A", ativo=True))
        neg_b = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} B", ativo=True))
        negocio_ids = [neg.id, neg_b.id]
        a1 = add(CentralProducao(negocio_id=neg.id, nome="_A1", ativa=True))
        cb = add(CentralProducao(negocio_id=neg_b.id, nome="_B", ativa=True))

        def loja(codigo, n, central):
            return add(Loja(negocio_id=n.id, central_producao_id=central.id, nome=f"_Loja {codigo}", codigo=codigo,
                            horario_zeragem=time(6, 0), ativo=True))

        l1, l2, l3, lb = loja("001", neg, a1), loja("002", neg, a1), loja("003", neg, a1), loja("B1", neg_b, cb)

        def usuario(rotulo, n, **campos):
            padrao = dict(tipo_usuario=TipoUsuario.OPERADOR_LOJA, tem_acesso_app=True, tem_acesso_web=False)
            padrao.update(campos)
            return add(Usuario(negocio_id=n.id, nome=f"_U {rotulo}", email=f"trr_{rotulo}_{run}@teste.com",
                               senha_hash=hash_senha("x"), **padrao))

        op1, op2, op3 = usuario("op1", neg, loja_id=l1.id), usuario("op2", neg, loja_id=l2.id), \
            usuario("op3", neg, loja_id=l3.id)
        op_b = usuario("opb", neg_b, loja_id=lb.id)
        op_sem_app = usuario("semapp", neg, loja_id=l1.id, tem_acesso_app=False)
        gestor = usuario("gestor", neg, tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=a1.id,
                         tem_acesso_app=False, tem_acesso_web=True)

        def produto(codigo, unidade):
            return add(Produto(negocio_id=neg.id, nome=f"_Produto {codigo}", codigo=codigo, unidade_medida=unidade,
                               ativo=True, tipo_abastecimento=TipoAbastecimento.PRODUZIDO))

        pa, pb, pc = produto("PA", UnidadeMedida.UN), produto("PB", UnidadeMedida.KG), produto("PC", UnidadeMedida.UN)
        agora = datetime.utcnow()
        oa = add(OrdemProducao(negocio_id=neg.id, central_producao_id=a1.id, data_producao=HOJE, data_entrega=HOJE,
                               versao_metodo="teste", gerado_em=agora, status=StatusOrdemProducao.APROVADA,
                               aprovado_em=agora, aprovado_por_usuario_id=gestor.id))
        itens = {}
        for prod, linhas in {pa: [(l1, "5"), (l3, "1")], pb: [(l1, "2.0")], pc: [(l2, "7")]}.items():
            item = add(OrdemProducaoItem(negocio_id=neg.id, ordem_id=oa.id, produto_id=prod.id,
                                         tipo_abastecimento=prod.tipo_abastecimento, unidade=prod.unidade_medida))
            itens[item.id] = sum(DEC(q) for _, q in linhas)
            for lj, q in linhas:
                add(OrdemProducaoLinha(negocio_id=neg.id, item_id=item.id, loja_id=lj.id,
                                       quantidade_sugerida=DEC(q), quantidade_final=DEC(q)))
        db.commit()
        registrar_producao(db, neg.id, a1.id, oa.id, itens, gestor.id)
        rom_id = gerar_romaneio(db, neg.id, a1.id, oa.id, gestor.id).romaneio_id
        aprovar_romaneio(db, neg.id, a1.id, rom_id, gestor.id)
        entregas = {lj: e.id for e, lj in db.query(RomaneioEntrega, Loja.codigo)
                    .join(Loja, Loja.id == RomaneioEntrega.loja_id).filter(RomaneioEntrega.romaneio_id == rom_id)}
        registrar_saida(db, neg.id, a1.id, rom_id, gestor.id, [entregas["001"]])

        tk = lambda u: criar_access_token(u.id, u.negocio_id)  # noqa: E731
        t1, t2, t3, tb = tk(op1), tk(op2), tk(op3), tk(op_b)

        def chamar(metodo, url, token=None, **kw):
            return getattr(cliente, metodo)(url, headers=h(token), **kw)

        def lista(token, extra=""):
            r = chamar("get", f"/recebimentos{extra}", token)
            return [(e["id"], sorted((i["produto"]["codigo"], i["quantidade_expedida"]) for i in e["itens"]))
                    for e in corpo(r)] if r.status_code == 200 else r.status_code

        def itens_gravados(codigo):
            db.expire_all()
            e = db.get(RomaneioEntrega, entregas[codigo])
            return e.situacao.value, sorted(
                ((str(i.quantidade_recebida) if i.quantidade_recebida is not None else None)
                 for i in db.query(RomaneioItem).filter(RomaneioItem.entrega_id == e.id)), key=str)

        # ---- A: autenticação ----
        rotas = [("get", "/recebimentos"), ("get", "/recebimentos/1"), ("post", "/recebimentos/1/confirmar")]
        sem = [chamar(m, u).status_code for m, u in rotas]
        # O app mantém o comportamento antigo de obter_usuario_autenticado (403 "Not authenticated",
        # A4 do test_auth_web): não mudar, para não quebrar o app em produção.
        registrar("A1 sem token -> 403 (padrao do app)", sem == [403] * 3, f"{sem}")
        web = [chamar(m, u, criar_access_token(gestor.id, gestor.negocio_id, porta=PORTA_WEB)).status_code
               for m, u in rotas]
        registrar("A2 token do SaaS -> 401", web == [401] * 3, f"{web}")
        r = chamar("get", "/recebimentos", tk(gestor))
        registrar("A3 gestor com token do app -> 403", r.status_code == 403, f"{r.status_code} {detalhe(r)}")
        r = chamar("get", "/recebimentos", tk(op_sem_app))
        registrar("A4 operador sem acesso ao app -> 403", r.status_code == 403, f"{r.status_code} {detalhe(r)}")

        # ---- L: listas ----
        v1, v2, v3 = lista(t1), lista(t2), lista(t3)
        registrar("L1 cada loja ve so o que saiu para ela",
                  v1 == [(entregas["001"], [("PA", "5.000"), ("PB", "2.000")])] and v2 == [] and v3 == [],
                  f"001 {v1}; 002 {v2}; 003 {v3}")
        registrar_saida(db, neg.id, a1.id, rom_id, gestor.id, [entregas["002"]])
        v1, v2 = lista(t1), lista(t2)
        registrar("L2 entregas diferentes por loja",
                  v2 == [(entregas["002"], [("PC", "7.000")])]
                  and v1 == [(entregas["001"], [("PA", "5.000"), ("PB", "2.000")])], f"001 {v1}; 002 {v2}")
        v2_url = lista(t2, f"?loja_id={l1.id}")
        registrar("L3 loja_id na URL ignorado", v2_url == v2, f"002 com ?loja_id da 001: {v2_url}")

        # ---- V: detalhe ----
        url1 = f"/recebimentos/{entregas['001']}"
        respostas = [chamar("get", url1, t2), chamar("get", url1, tb)]
        r_ok = chamar("get", url1, t1)
        registrar("V1 detalhe so da propria loja",
                  [x.status_code for x in respostas] == [404, 404] and len({x.text for x in respostas}) == 1
                  and r_ok.status_code == 200 and corpo(r_ok)["situacao"]["situacao"] == "a_caminho",
                  f"002 {respostas[0].status_code}, B {respostas[1].status_code}, 001 {r_ok.status_code} "
                  f"{corpo(r_ok).get('situacao')}")
        r = chamar("get", f"/recebimentos/{entregas['003']}", t3)
        registrar("V2 entrega sem saida nao aparece", r.status_code == 404, f"{r.status_code} {detalhe(r)}")

        # ---- C: confirmar ----
        itens1 = {i["produto"]["codigo"]: i["id"] for i in corpo(r_ok)["itens"]}
        r = chamar("post", f"{url1}/confirmar", t2)
        registrar("C1 confirmar entrega de outra loja -> 404", r.status_code == 404
                  and itens_gravados("001") == ("expedida", [None, None]), f"{r.status_code}; {itens_gravados('001')}")
        invalidos = {
            "sem motivo": {"diferencas": [{"item_id": itens1["PB"], "quantidade_recebida": "1.5"}]},
            "motivo invalido": {"diferencas": [{"item_id": itens1["PB"], "quantidade_recebida": "1.5",
                                                "motivo": "sumiu"}]},
            "item repetido": {"diferencas": [{"item_id": itens1["PB"], "quantidade_recebida": "1.5",
                                              "motivo": "falta"},
                                             {"item_id": itens1["PB"], "quantidade_recebida": "1", "motivo": "falta"}]},
            "UN fracionada": {"diferencas": [{"item_id": itens1["PA"], "quantidade_recebida": "4.5",
                                              "motivo": "falta"}]},
        }
        rs = {k: chamar("post", f"{url1}/confirmar", t1, json=v) for k, v in invalidos.items()}
        registrar("C2 confirmacoes invalidas -> 422",
                  all(x.status_code == 422 and isinstance(corpo(x).get("detail"), str) for x in rs.values())
                  and itens_gravados("001") == ("expedida", [None, None]),
                  "; ".join(f"{k} {x.status_code} {detalhe(x)[:40]}" for k, x in rs.items()))
        r = chamar("post", f"/recebimentos/{entregas['003']}/confirmar", t3)
        registrar("C3 entrega sem saida -> 409", r.status_code == 409, f"{r.status_code} {detalhe(r)}")
        r = chamar("post", f"{url1}/confirmar", t1, json={"diferencas": [
            {"item_id": itens1["PB"], "quantidade_recebida": "1.5", "motivo": "avaria"}]})
        b = corpo(r)
        recebidas = {i["produto"]["codigo"]: (i["quantidade_recebida"], i["motivo_divergencia"])
                     for i in b.get("itens", [])} if isinstance(b, dict) else {}
        registrar("C4 confirmar com diferenca",
                  r.status_code == 200 and b["situacao"] == {"situacao": "recebida", "pode_confirmar": False,
                                                             "com_diferenca": True}
                  and recebidas == {"PA": ("5.000", None), "PB": ("1.500", "avaria")}, f"{r.status_code} {recebidas}")
        r = chamar("post", f"{url1}/confirmar", t1)
        registrar("C5 confirmar de novo -> 409", r.status_code == 409, f"{r.status_code} {detalhe(r)}")
        r = chamar("post", f"/recebimentos/{entregas['002']}/confirmar", t2)
        registrar("C6 recebi tudo certo", r.status_code == 200 and itens_gravados("002") == ("recebida", ["7.000"])
                  and not corpo(r)["situacao"]["com_diferenca"], f"{r.status_code} {itens_gravados('002')}")
        registrar("C7 listas vazias depois de confirmar", lista(t1) == [] and lista(t2) == [],
                  f"001 {lista(t1)}; 002 {lista(t2)}")

        esquema = cliente.get("/openapi.json").json()
        caminhos = {p: ops for p, ops in esquema["paths"].items() if p.startswith("/recebimentos")}
        parametros = {p["name"] for ops in caminhos.values() for op in ops.values() for p in op.get("parameters", [])}
        registrar("O1 OpenAPI sem loja_id", set(caminhos) == {"/recebimentos", "/recebimentos/{entrega_id}",
                                                              "/recebimentos/{entrega_id}/confirmar"}
                  and parametros == {"entrega_id"}, f"{sorted(caminhos)}; parametros {sorted(parametros)}")
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste da API do recebimento no app (E7) ===")
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
