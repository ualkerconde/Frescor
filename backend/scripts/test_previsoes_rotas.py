"""
Testa a API de previsão (Fase 3 / F8) por HTTP, com o TestClient:
autenticação, geração, consulta, qualidade, escopo da central (D8) e
isolamento entre negócios.

Cenário (vendas com variação determinística, 63 dias até 12/10/2026):
  negócio A, central A1: L1 (P1 UN ~10/dia, P2 KG ~2,5/dia) e L2 (P1 ~30/dia)
  central A2: L3 (P1 ~10/dia) · negócio B: LB (PB ~10/dia)
  evento ×2 em L1/P1 no dia 14/10
Usuários: gestor A1, gestor A2, gestor B, gestor A1 sem acesso web, operador.

Casos:
  A1..A5 sem token / token do app / sem acesso web -> 401/401/403/401/401
  R1 POST /previsoes/gerar com referência 12/10 -> 21 previsões (3 × 7 dias)
  R2 referência hoje -> 422 em português · R3 sem corpo -> referência = ontem
  C1 GET /previsoes?data=13/10: 3 itens, componentes, venda da semana
     passada (06/10) e totais por unidade
  C2 filtro de loja · C3 loja de outra central -> 404 · C4 loja de outro
  negócio -> 404 · C5 as respostas 404 são iguais · C6 filtro de produto
  C7 gestor A2 vê só a própria central (antes e depois de gerar)
  C8 gestor B não vê nada do negócio A
  C9 dia sem geração -> lista vazia · C10 data inválida -> 422 em português
  C11 evento aparece no item e dobra a previsão
  Q1 GET /previsoes/qualidade 29/09 a 12/10: pares por unidade e WAPE/viés
     iguais ao cálculo de referência (prever_central + métricas)
  Q2 WAPE do ingênuo igual à conta feita à mão com as vendas do teste
  Q3 filtro de loja · Q4 loja de outra central -> 404
  Q5 período inválido (mais de 28 dias, até hoje, início depois do fim) -> 422
  Q6 gestor B mede só o negócio dele · Q7 sem datas -> 28 dias até ontem

Uso: python scripts/test_previsoes_rotas.py
"""

import random
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
from app.models.evento import EscopoLoja, EscopoProduto, Evento, EventoLoja, EventoProduto, TipoAjuste  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.previsao_diaria import PrevisaoDiaria  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402
from app.services.previsao_gravacao import VERSAO_METODO  # noqa: E402
from app.services.previsao_metricas import medir  # noqa: E402
from app.services.previsao_service import prever_central  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 26
PREFIXO_NEGOCIO_TESTE = "_Teste Previsoes Rotas"
EMAIL_TESTE = re.compile(r"^tpr_[a-z_0-9]+_[0-9a-f]{8}@teste[.]com$")
D = Decimal
REF = date(2026, 10, 12)
INEXISTENTE = 2_000_000_000
QUALIDADE = (REF - timedelta(days=13), REF)

cliente = TestClient(app)
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def q4(x):
    """Métricas saem da API com 4 casas."""
    return x.quantize(D("0.0001"))


def corpo(r):
    try:
        return r.json()
    except ValueError:
        return r.text


def h(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    db.query(PrevisaoDiaria).filter(PrevisaoDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    ev_ids = [e.id for e in db.query(Evento).filter(Evento.negocio_id.in_(negocio_ids))]
    if ev_ids:
        db.query(EventoLoja).filter(EventoLoja.evento_id.in_(ev_ids)).delete(synchronize_session=False)
        db.query(EventoProduto).filter(EventoProduto.evento_id.in_(ev_ids)).delete(synchronize_session=False)
        db.query(Evento).filter(Evento.id.in_(ev_ids)).delete(synchronize_session=False)
    db.query(VendaDiaria).filter(VendaDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
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
        avulsos = [u for u in db.query(Usuario).filter(Usuario.email.like("tpr_%@teste.com")).all()
                   if EMAIL_TESTE.match(u.email) and u.negocio_id not in [n.id for n in negocios]]
        if not negocios and not avulsos:
            print("[limpeza inicial] Nenhum resíduo de teste encontrado.")
            return
        print("[limpeza inicial] Resíduos de execuções anteriores encontrados:")
        for n in negocios:
            print(f"  negocio id={n.id} nome={n.nome!r}")
        for u in avulsos:
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
            db.flush()
            return lj

        l1, l2, l3, lb = loja(neg_a, c_a1, "L1"), loja(neg_a, c_a1, "L2"), loja(neg_a, c_a2, "L3"), loja(neg_b, c_b, "LB")

        def produto(neg, codigo, unidade=UnidadeMedida.UN):
            p = Produto(negocio_id=neg.id, nome=f"_{codigo}", codigo=codigo, unidade_medida=unidade, ativo=True)
            db.add(p)
            db.flush()
            return p

        p1, p2, pb = produto(neg_a, "P1"), produto(neg_a, "P2", UnidadeMedida.KG), produto(neg_b, "PB")
        rnd = random.Random(7)
        vendas = {}
        for neg, lj, p, base in ((neg_a, l1, p1, 10), (neg_a, l1, p2, 2.5), (neg_a, l2, p1, 30),
                                 (neg_a, l3, p1, 10), (neg_b, lb, pb, 10)):
            db.add(ProdutoLoja(produto_id=p.id, loja_id=lj.id))
            for k in range(63):
                dia = REF - timedelta(days=k)
                fator = rnd.uniform(0.8, 1.2)
                q = D(str(round(base * fator))) if p.unidade_medida == UnidadeMedida.UN else D(f"{base * fator:.3f}")
                vendas.setdefault((lj.id, p.id), {})[dia] = q
                db.add(VendaDiaria(negocio_id=neg.id, loja_id=lj.id, produto_id=p.id, data=dia, quantidade=q,
                                   origem=OrigemVenda.MANUAL))
        ev = Evento(negocio_id=neg_a.id, central_producao_id=c_a1.id, nome="Dobra P1", data_inicio=REF + timedelta(days=2),
                    data_fim=REF + timedelta(days=2), escopo_loja=EscopoLoja.ESPECIFICAS,
                    escopo_produto=EscopoProduto.ESPECIFICOS, tipo_ajuste=TipoAjuste.MULTIPLICADOR, valor_ajuste=D("2"))
        db.add(ev)
        db.flush()
        db.add_all([EventoLoja(evento_id=ev.id, loja_id=l1.id, negocio_id=neg_a.id),
                    EventoProduto(evento_id=ev.id, produto_id=p1.id, negocio_id=neg_a.id)])

        def usuario(rotulo, neg, **campos):
            u = Usuario(negocio_id=neg.id, nome=f"Teste {rotulo}", email=f"tpr_{rotulo}_{run_id}@teste.com",
                        senha_hash=hash_senha("x"), status=StatusUsuario.ATIVO, **campos)
            db.add(u)
            db.flush()
            return u

        gestor = dict(tipo_usuario=TipoUsuario.GESTOR_CENTRAL, tem_acesso_app=False)
        g_a1 = usuario("gestor_a1", neg_a, central_producao_id=c_a1.id, tem_acesso_web=True, **gestor)
        g_a2 = usuario("gestor_a2", neg_a, central_producao_id=c_a2.id, tem_acesso_web=True, **gestor)
        g_b = usuario("gestor_b", neg_b, central_producao_id=c_b.id, tem_acesso_web=True, **gestor)
        g_sem_web = usuario("gestor_sem_web", neg_a, central_producao_id=c_a1.id, tem_acesso_web=False, **gestor)
        operador = usuario("operador", neg_a, tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=l1.id,
                           tem_acesso_web=False, tem_acesso_app=True)
        db.commit()
        tk = lambda u: criar_access_token(u.id, u.negocio_id, porta=PORTA_WEB)  # noqa: E731
        ta1, ta2, tb = tk(g_a1), tk(g_a2), tk(g_b)
        hoje = date.today()
        dia1 = REF + timedelta(days=1)

        def gerar(token, **corpo_):
            return cliente.post("/previsoes/gerar", json=corpo_ or None, headers=h(token))

        def previsoes(token, **params):
            return cliente.get("/previsoes", params=params, headers=h(token))

        def qualidade(token, **params):
            return cliente.get("/previsoes/qualidade", params=params, headers=h(token))

        # ---------------- autenticação ----------------
        r = gerar(None, data_referencia=str(REF))
        registrar("A1 gerar sem token", r.status_code == 401, f"{r.status_code}")
        r = gerar(criar_access_token(operador.id, operador.negocio_id), data_referencia=str(REF))
        registrar("A2 gerar com token do app", r.status_code == 401, f"{r.status_code}")
        r = gerar(tk(g_sem_web), data_referencia=str(REF))
        registrar("A3 gestor sem acesso web", r.status_code == 403, f"{r.status_code}")
        r = previsoes(None, data=str(dia1))
        registrar("A4 consultar sem token", r.status_code == 401, f"{r.status_code}")
        r = qualidade(None)
        registrar("A5 qualidade sem token", r.status_code == 401, f"{r.status_code}")

        # ---------------- geração ----------------
        r = gerar(ta1, data_referencia=str(REF))
        b = corpo(r)
        registrar("R1 gerar com referencia 12/10",
                  r.status_code == 200 and b["gravadas"] == 21 and b["data_inicio"] == str(dia1)
                  and b["data_fim"] == str(REF + timedelta(days=7)) and b["versao_metodo"] == VERSAO_METODO,
                  f"{r.status_code} -> {b}")
        r = gerar(ta1, data_referencia=str(hoje))
        registrar("R2 referencia hoje -> 422", r.status_code == 422 and "no máximo ontem" in str(corpo(r).get("detail")),
                  f"{r.status_code} -> {corpo(r)}")
        r = gerar(ta1)
        b = corpo(r)
        registrar("R3 sem corpo -> referencia ontem",
                  r.status_code == 200 and b["data_referencia"] == str(hoje - timedelta(days=1)),
                  f"{r.status_code} -> referência {b.get('data_referencia') if isinstance(b, dict) else b}")

        # ---------------- consulta ----------------
        r = previsoes(ta1, data=str(dia1))
        b = corpo(r)
        itens = b.get("itens", []) if isinstance(b, dict) else []
        chaves = sorted((i["loja"]["codigo"], i["produto"]["codigo"]) for i in itens)
        db.expire_all()
        gravado = {(x.loja_id, x.produto_id): x for x in db.query(PrevisaoDiaria).filter(
            PrevisaoDiaria.negocio_id == neg_a.id, PrevisaoDiaria.data == dia1)}
        semana = dia1 - timedelta(days=7)
        ok_itens = all(
            D(i["previsao"]) == gravado[(i["loja"]["id"], i["produto"]["id"])].previsao
            and D(i["venda_semana_passada"]) == vendas[(i["loja"]["id"], i["produto"]["id"])][semana]
            and i["estatistica"] == "mediana" and i["metodo"] == "semanal" and i["pouco_historico"] is False
            for i in itens)
        tot = {t["unidade"]: (D(t["previsto"]), D(t["vendido_semana_passada"])) for t in b.get("totais", [])}
        esperado_un = (gravado[(l1.id, p1.id)].previsao + gravado[(l2.id, p1.id)].previsao,
                       vendas[(l1.id, p1.id)][semana] + vendas[(l2.id, p1.id)][semana])
        registrar("C1 consulta do dia com componentes e totais",
                  r.status_code == 200 and chaves == [("L1", "P1"), ("L1", "P2"), ("L2", "P1")] and ok_itens
                  and tot.get("UN") == esperado_un and tot.get("KG") == (gravado[(l1.id, p2.id)].previsao,
                                                                           vendas[(l1.id, p2.id)][semana]),
                  f"{r.status_code}; itens {chaves}; totais {tot}")
        print("Exemplo de item:", {k: itens[0][k] for k in ("loja", "produto", "previsao", "base", "tendencia",
                                                             "venda_semana_passada", "peso_historico", "eventos")}
              if itens else None)
        r = previsoes(ta1, data=str(dia1), loja_id=l2.id)
        registrar("C2 filtro de loja", r.status_code == 200 and [i["loja"]["codigo"] for i in corpo(r)["itens"]] == ["L2"],
                  f"{r.status_code} -> {[i['loja']['codigo'] for i in corpo(r).get('itens', [])]}")
        respostas = []
        for nome, lid in (("C3 loja de outra central", l3.id), ("C4 loja de outro negocio", lb.id)):
            r = previsoes(ta1, data=str(dia1), loja_id=lid)
            respostas.append((r.status_code, r.text))
            registrar(nome, r.status_code == 404, f"{r.status_code} -> {corpo(r)}")
        r = previsoes(ta1, data=str(dia1), loja_id=INEXISTENTE)
        respostas.append((r.status_code, r.text))
        registrar("C5 404 iguais (outra central, outro negocio, inexistente)", len(set(respostas)) == 1,
                  f"{len(set(respostas))} resposta(s) distinta(s)")
        r = previsoes(ta1, data=str(dia1), produto_id=p2.id)
        registrar("C6 filtro de produto",
                  r.status_code == 200 and [(i["produto"]["codigo"], i["unidade"]) for i in corpo(r)["itens"]] == [("P2", "KG")],
                  f"{[(i['produto']['codigo'], i['unidade']) for i in corpo(r).get('itens', [])]}")
        antes = [i["loja"]["codigo"] for i in corpo(previsoes(ta2, data=str(dia1)))["itens"]]
        gerar(ta2, data_referencia=str(REF))
        depois = [i["loja"]["codigo"] for i in corpo(previsoes(ta2, data=str(dia1)))["itens"]]
        registrar("C7 gestor A2 ve so a propria central", antes == [] and depois == ["L3"],
                  f"antes de gerar {antes}; depois {depois}")
        r = previsoes(tb, data=str(dia1))
        registrar("C8 gestor B nao ve o negocio A", r.status_code == 200 and corpo(r)["itens"] == [],
                  f"{r.status_code} -> {len(corpo(r)['itens'])} itens")
        r = previsoes(ta1, data=str(REF + timedelta(days=30)))
        registrar("C9 dia sem geracao -> vazio", r.status_code == 200 and corpo(r)["itens"] == [] and corpo(r)["totais"] == [],
                  f"{r.status_code} -> {corpo(r)}")
        r = previsoes(ta1, data="2026-02-30")
        registrar("C10 data invalida -> 422 em portugues",
                  r.status_code == 422 and corpo(r)["detail"] == "Data inválida em 'data'. Use o formato AAAA-MM-DD.",
                  f"{r.status_code} -> {corpo(r).get('detail')}")
        r = previsoes(ta1, data=str(REF + timedelta(days=2)), loja_id=l1.id, produto_id=p1.id)
        item = corpo(r)["itens"][0] if r.status_code == 200 and corpo(r)["itens"] else {}
        registrar("C11 evento no item",
                  item.get("eventos") and item["eventos"][0]["nome"] == "Dobra P1"
                  and D(item["previsao"]) == 2 * D(item["previsao_sem_evento"]),
                  f"previsão {item.get('previsao')} (sem evento {item.get('previsao_sem_evento')}), eventos {item.get('eventos')}")

        # ---------------- qualidade ----------------
        ini, fim = QUALIDADE
        r = qualidade(ta1, data_inicio=str(ini), data_fim=str(fim))
        b = corpo(r)
        print("Qualidade A1:", b)
        dias = [ini + timedelta(days=k) for k in range((fim - ini).days + 1)]
        oraculo = {"UN": [], "KG": []}
        for dia in dias:
            for x in prever_central(db, neg_a.id, c_a1.id, dia - timedelta(days=1), dia):
                u = "KG" if x.produto_id == p2.id else "UN"
                real, ing = vendas[(x.loja_id, x.produto_id)][dia], vendas[(x.loja_id, x.produto_id)][dia - timedelta(days=7)]
                oraculo[u].append((real, x.previsao, ing))
        obtido = {u["unidade"]: u for u in b.get("por_unidade", [])} if isinstance(b, dict) else {}
        divergencias = []
        for u, pares in oraculo.items():
            m = medir((r_, p) for r_, p, _ in pares)
            o = obtido.get(u)
            if o is None or o["pares"] != m.n or D(o["wape"]) != q4(m.wape) or D(o["vies"]) != q4(m.vies):
                divergencias.append(f"{u}: {o} != pares {m.n}, wape {m.wape}, viés {m.vies}")
        registrar("Q1 qualidade = calculo de referencia",
                  r.status_code == 200 and not divergencias and obtido["UN"]["pares"] == 28 and obtido["KG"]["pares"] == 14,
                  "; ".join(divergencias) or f"UN {obtido['UN']['pares']} pares, WAPE {D(obtido['UN']['wape']):.2%}; "
                  f"KG {obtido['KG']['pares']} pares, WAPE {D(obtido['KG']['wape']):.2%}")
        erros = []
        for u, pares in oraculo.items():
            soma_real = sum(r_ for r_, _, _ in pares)
            manual = sum(abs(r_ - i) for r_, _, i in pares) / soma_real
            if D(obtido[u]["ingenuo_wape"]) != q4(manual):
                erros.append(f"{u}: {obtido[u]['ingenuo_wape']} != {q4(manual)}")
            motor_exato = medir((r_, p) for r_, p, _ in pares).wape
            if obtido[u]["vence_ingenuo"] != (motor_exato < manual):
                erros.append(f"{u}: vence_ingenuo incoerente")
        registrar("Q2 ingenuo conferido a mao", not erros,
                  "; ".join(erros) or f"UN ingênuo {D(obtido['UN']['ingenuo_wape']):.2%} "
                  f"(vence: {obtido['UN']['vence_ingenuo']}); KG ingênuo {D(obtido['KG']['ingenuo_wape']):.2%} "
                  f"(vence: {obtido['KG']['vence_ingenuo']})")
        r = qualidade(ta1, data_inicio=str(ini), data_fim=str(fim), loja_id=l1.id)
        pares = {u["unidade"]: u["pares"] for u in corpo(r).get("por_unidade", [])}
        registrar("Q3 filtro de loja", r.status_code == 200 and pares == {"KG": 14, "UN": 14}, f"{r.status_code} -> {pares}")
        r = qualidade(ta1, data_inicio=str(ini), data_fim=str(fim), loja_id=l3.id)
        registrar("Q4 loja de outra central -> 404", r.status_code == 404, f"{r.status_code}")
        invalidos = [
            (dict(data_inicio=str(fim - timedelta(days=28)), data_fim=str(fim)), "no máximo 28 dias"),
            (dict(data_inicio=str(hoje - timedelta(days=3)), data_fim=str(hoje)), "até ontem"),
            (dict(data_inicio=str(fim), data_fim=str(ini)), "depois da final"),
        ]
        erros = []
        for params, trecho in invalidos:
            r = qualidade(ta1, **params)
            if r.status_code != 422 or trecho not in str(corpo(r).get("detail")):
                erros.append(f"{params}: {r.status_code} {corpo(r)}")
        registrar("Q5 periodo invalido -> 422", not erros, "; ".join(erros) or "29 dias, até hoje e invertido recusados")
        r = qualidade(tb, data_inicio=str(ini), data_fim=str(fim))
        pares = {u["unidade"]: u["pares"] for u in corpo(r).get("por_unidade", [])}
        registrar("Q6 gestor B mede so o negocio dele", r.status_code == 200 and pares == {"UN": 14},
                  f"{r.status_code} -> {pares}")
        r = qualidade(tb)
        b = corpo(r)
        registrar("Q7 sem datas -> 28 dias ate ontem",
                  r.status_code == 200 and b["data_fim"] == str(hoje - timedelta(days=1))
                  and b["data_inicio"] == str(hoje - timedelta(days=28)),
                  f"{r.status_code} -> {b.get('data_inicio')} a {b.get('data_fim')}")

    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste da API de previsão ===")
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
