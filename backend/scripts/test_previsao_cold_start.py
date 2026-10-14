"""
Testa o cold start do motor de previsão (Fase 3 / F4, doc §4.2 e D20):
peso do histórico próprio (0% na 1ª semana a 100% depois de 6 semanas) e
os proxies de produto novo (categoria = 1º nível da classificação, ou a
mesma unidade) e de loja nova (mesmo produto nas outras lojas da central).

Parte 1, funções puras:
  K01 peso_historico_proprio nos limites (sem histórico, 1, 6, 7, 13, 14,
      41, 42 e 100 dias, início depois da referência)
  K02 combinar_cold_start (peso 0, 0,5 e 1; sem proxy; sem própria; nada)

Parte 2, serviço com banco. Referência 12/10/2026 (segunda), alvo 13/10.
  Níveis do negócio A: 1 = Categoria, 2 = Subcategoria.
  Central A1: L1 e L2 com 56 dias de vendas; L3 nova (vende desde 03/10).
  Central A2: L4 (vende PA a 1000/dia; não pode entrar no proxy de L3).
  Produtos (UN, salvo KG):
    PA Pães    L1 10/dia · L2 30/dia · L3 6/dia desde 03/10 · L4 1000/dia
    PB Pães    L1 20/dia · habilitado em L3 sem vendas
    PD Doces   L1 100/dia
    PK Pães KG L1 5/dia
    PN Pães    L1 40/dia desde 29/09 (14 dias, peso 2/6)
    PC Bolos   L1 8/dia desde 22/09 (21 dias, peso 3/6); subcategoria
               "Pães" no 2º nível (não pode contar como categoria)
    PS sem categoria, L1 12/dia desde 10/10 (3 dias, peso 0)
    PNK Pães KG habilitado em L1, nunca vendeu
    PX Pães    só habilitado em L3, nunca vendeu
  Evento ×2 em L1/PS no alvo (o evento vem depois do cold start).

  K03 L1/PA histórico completo -> sem cold start, 10
  K04 L1/PN própria só com o histórico dele (40; os zeros de antes do
      lançamento não entram) e proxy da categoria Pães UN (PA 10, PB 20)
      -> 2/6 × 40 + 4/6 × 15
  K05 L1/PC categoria sem pares -> proxy da unidade (PA, PB, PD = 43,33)
      -> 0,5 × 8 + 0,5 × 43,33
  K06 L1/PS sem categoria, sem própria -> proxy da unidade 43,33; evento
      ×2 depois -> 86,67
  K07 L1/PNK nunca vendeu -> proxy da categoria Pães KG (PK 5)
  K08 L3/PA loja nova -> proxy outras lojas da central (L1 10, L2 30 = 20;
      L4 de fora) -> 1/6 × 6 + 5/6 × 20
  K09 L3/PB loja nova sem venda -> proxy de L1 (20)
  K10 L3/PX sem proxy possível -> previsão None
  K11 produto em cold start não serve de proxy para outro
  K12 seed: todas as previsões da central do gestor@teste.com com peso 1,
      sem proxy e com valor
  K13 a loja da outra central (L4) não recebe previsão da central A1
  K14 D28: nunca vendeu, habilitado há 21 dias (peso 0,5) -> 0,5 × 0
      (histórico próprio: zeros da D17) + 0,5 × proxy da categoria (15)
  K15 D28: nunca vendeu, habilitado há 49 dias -> histórico próprio (0),
      sem proxy

Uso: python scripts/test_previsao_cold_start.py
"""

import sys
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.evento import EscopoLoja, EscopoProduto, Evento, EventoLoja, EventoProduto, TipoAjuste  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.nivel_classificacao import NivelClassificacao  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.produto_classificacao import ProdutoClassificacao  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402
from app.services.previsao_calculo import combinar_cold_start, peso_historico_proprio  # noqa: E402
from app.services.previsao_service import prever_central  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 15
PREFIXO_NEGOCIO_TESTE = "_Teste Cold Start"
D = Decimal
REF = date(2026, 10, 12)  # segunda
ALVO = REF + timedelta(days=1)
TOL = D("0.000000001")

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def perto(a, b):
    return a is not None and b is not None and abs(a - b) <= TOL


def fmt(x):
    return "None" if x is None else f"{x:.4f}"


def parte_pura():
    casos = [(None, D("0")), (REF + timedelta(days=1), D("0"))]
    for dias, esperado in ((1, 0), (6, 0), (7, 1), (13, 1), (14, 2), (41, 5), (42, 6), (100, 6)):
        casos.append((REF - timedelta(days=dias - 1), D(esperado) / 6))
    erros = [f"{inicio}: {peso_historico_proprio(inicio, REF)} (esperado {esp})"
             for inicio, esp in casos if peso_historico_proprio(inicio, REF) != esp]
    registrar("K01 peso do historico proprio", not erros, "; ".join(erros) or
              "None/futuro 0; 1-6 dias 0; 7 e 13 dias 1/6; 14 dias 2/6; 41 dias 5/6; 42 e 100 dias 1")

    combinacoes = [
        ((D("40"), D("0"), D("10")), D("10")),
        ((D("40"), D("0.5"), D("10")), D("25")),
        ((D("40"), D("1"), D("10")), D("40")),
        ((D("40"), D("0.5"), None), D("40")),
        ((None, D("0.5"), D("10")), D("10")),
        ((None, D("0"), None), None),
    ]
    erros = [f"{args} -> {combinar_cold_start(*args)} (esperado {esp})"
             for args, esp in combinacoes if combinar_cold_start(*args) != esp]
    registrar("K02 combinar_cold_start", not erros, "; ".join(erros) or "6 combinações conferidas")


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    ev_ids = [e.id for e in db.query(Evento).filter(Evento.negocio_id.in_(negocio_ids))]
    if ev_ids:
        db.query(EventoLoja).filter(EventoLoja.evento_id.in_(ev_ids)).delete(synchronize_session=False)
        db.query(EventoProduto).filter(EventoProduto.evento_id.in_(ev_ids)).delete(synchronize_session=False)
        db.query(Evento).filter(Evento.id.in_(ev_ids)).delete(synchronize_session=False)
    db.query(VendaDiaria).filter(VendaDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    produto_ids = [p.id for p in db.query(Produto).filter(Produto.negocio_id.in_(negocio_ids))]
    if produto_ids:
        db.query(ProdutoLoja).filter(ProdutoLoja.produto_id.in_(produto_ids)).delete(synchronize_session=False)
        db.query(ProdutoClassificacao).filter(ProdutoClassificacao.produto_id.in_(produto_ids)).delete(
            synchronize_session=False)
    db.query(NivelClassificacao).filter(NivelClassificacao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
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
        print("[limpeza inicial] Resíduos de execuções anteriores encontrados:")
        for n in negocios:
            print(f"  negocio id={n.id} nome={n.nome!r}")
        _limpar(db, [n.id for n in negocios])
        print("[limpeza inicial] Resíduos apagados.")
    finally:
        db.close()


def parte_banco():
    _limpar_residuos()
    db = SessionLocal()
    negocio_ids = []
    try:
        run_id = uuid.uuid4().hex[:8]
        neg = Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run_id} A", ativo=True)
        db.add(neg)
        db.flush()
        negocio_ids = [neg.id]
        c_a1 = CentralProducao(negocio_id=neg.id, nome="_Central A1", ativa=True)
        c_a2 = CentralProducao(negocio_id=neg.id, nome="_Central A2", ativa=True)
        db.add_all([c_a1, c_a2])
        db.flush()
        n_cat = NivelClassificacao(negocio_id=neg.id, ordem=1, nome="Categoria")
        n_sub = NivelClassificacao(negocio_id=neg.id, ordem=2, nome="Subcategoria")
        db.add_all([n_cat, n_sub])
        db.flush()

        def loja(central, codigo):
            lj = Loja(negocio_id=neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}", codigo=codigo,
                      horario_zeragem=time(6, 0), ativo=True)
            db.add(lj)
            db.flush()
            return lj

        l1, l2, l3, l4 = loja(c_a1, "L1"), loja(c_a1, "L2"), loja(c_a1, "L3"), loja(c_a2, "L4")

        def produto(codigo, categoria=None, unidade=UnidadeMedida.UN, sub=None):
            p = Produto(negocio_id=neg.id, nome=f"_{codigo}", codigo=codigo, unidade_medida=unidade, ativo=True)
            db.add(p)
            db.flush()
            if categoria:
                db.add(ProdutoClassificacao(produto_id=p.id, nivel_id=n_cat.id, valor=categoria))
            if sub:
                db.add(ProdutoClassificacao(produto_id=p.id, nivel_id=n_sub.id, valor=sub))
            return p

        pa, pb, pd = produto("PA", "Pães"), produto("PB", "Pães"), produto("PD", "Doces")
        pk = produto("PK", "Pães", UnidadeMedida.KG)
        pn, pc = produto("PN", "Pães"), produto("PC", "Bolos", sub="Pães")
        ps, pnk = produto("PS"), produto("PNK", "Pães", UnidadeMedida.KG)
        px = produto("PX", "Pães")

        vendas = [  # (loja, produto, quantidade, dias de histórico até REF)
            (l1, pa, "10", 56), (l2, pa, "30", 56), (l3, pa, "6", 10), (l4, pa, "1000", 56),
            (l1, pb, "20", 56), (l1, pd, "100", 56), (l1, pk, "5", 56),
            (l1, pn, "40", 14), (l1, pc, "8", 21), (l1, ps, "12", 3),
        ]
        habilitar = {(lj.id, p.id) for lj, p, _, _ in vendas} | {(l3.id, pb.id), (l1.id, pnk.id), (l3.id, px.id)}
        for loja_id, produto_id in habilitar:
            db.add(ProdutoLoja(produto_id=produto_id, loja_id=loja_id))
        # D28: nunca venderam, habilitados há 21 dias (P21) e há 49 dias (P49).
        # P49 em categoria e unidade próprias: com histórico completo (zero), ele
        # serviria de par no proxy de outros produtos da mesma categoria/unidade.
        p21, p49 = produto("P21", "Pães"), produto("P49", "Congelados", UnidadeMedida.KG)
        db.add(ProdutoLoja(produto_id=p21.id, loja_id=l1.id, criado_em=datetime(2026, 9, 22, 10, 0)))
        db.add(ProdutoLoja(produto_id=p49.id, loja_id=l1.id, criado_em=datetime(2026, 8, 25, 10, 0)))
        for lj, p, q, dias in vendas:
            for k in range(dias):
                db.add(VendaDiaria(negocio_id=neg.id, loja_id=lj.id, produto_id=p.id, data=REF - timedelta(days=k),
                                   quantidade=D(q), origem=OrigemVenda.MANUAL))
        ev = Evento(negocio_id=neg.id, central_producao_id=c_a1.id, nome="ev_ps", data_inicio=ALVO, data_fim=ALVO, escopo_loja=EscopoLoja.ESPECIFICAS,
                    escopo_produto=EscopoProduto.ESPECIFICOS, tipo_ajuste=TipoAjuste.MULTIPLICADOR, valor_ajuste=D("2"))
        db.add(ev)
        db.flush()
        db.add_all([EventoLoja(evento_id=ev.id, loja_id=l1.id, negocio_id=neg.id),
                    EventoProduto(evento_id=ev.id, produto_id=ps.id, negocio_id=neg.id)])
        db.commit()

        prev = {(x.loja_id, x.produto_id): x for x in prever_central(db, neg.id, c_a1.id, REF, ALVO)}
        nl = {l1.id: "L1", l2.id: "L2", l3.id: "L3", l4.id: "L4"}
        npr = {p.id: p.codigo for p in (pa, pb, pd, pk, pn, pc, ps, pnk, px, p21, p49)}
        print("Previsões de 13/10 (central A1):")
        for (lid, pid), x in sorted(prev.items(), key=lambda kv: (nl[kv[0][0]], npr[kv[0][1]])):
            print(f"  {nl[lid]}/{npr[pid]:<3}: início {x.inicio_historico}, peso {fmt(x.peso_historico)}, "
                  f"própria {fmt(x.previsao_propria)}, proxy {fmt(x.proxy)} ({x.origem_proxy}), "
                  f"sem evento {fmt(x.previsao_sem_evento)}, final {fmt(x.previsao)}")

        x = prev[(l1.id, pa.id)]
        registrar("K03 L1/PA historico completo", x.peso_historico == 1 and x.proxy is None and x.previsao == D("10"),
                  f"peso {x.peso_historico}, final {fmt(x.previsao)}")
        x = prev[(l1.id, pn.id)]
        esperado = D(2) / 6 * 40 + D(4) / 6 * 15
        registrar("K04 L1/PN produto novo, proxy da categoria",
                  x.previsao_propria == D("40") and x.proxy == D("15") and x.origem_proxy == "categoria"
                  and perto(x.previsao, esperado),
                  f"própria {fmt(x.previsao_propria)}, proxy {fmt(x.proxy)} ({x.origem_proxy}), "
                  f"final {fmt(x.previsao)} (esperado {fmt(esperado)})")
        x = prev[(l1.id, pc.id)]
        unidade_l1 = (D(10) + 20 + 100) / 3
        esperado = D("0.5") * 8 + D("0.5") * unidade_l1
        registrar("K05 L1/PC categoria sem pares -> unidade",
                  x.origem_proxy == "unidade" and perto(x.proxy, unidade_l1) and perto(x.previsao, esperado),
                  f"proxy {fmt(x.proxy)} ({x.origem_proxy}), final {fmt(x.previsao)} (esperado {fmt(esperado)})")
        x = prev[(l1.id, ps.id)]
        registrar("K06 L1/PS sem categoria; evento depois do cold start",
                  x.previsao_propria is None and x.origem_proxy == "unidade" and perto(x.previsao_sem_evento, unidade_l1)
                  and perto(x.previsao, 2 * unidade_l1) and [e.nome for e in x.eventos] == ["ev_ps"],
                  f"própria {fmt(x.previsao_propria)}, sem evento {fmt(x.previsao_sem_evento)}, final {fmt(x.previsao)}")
        x = prev[(l1.id, pnk.id)]
        registrar("K07 L1/PNK nunca vendeu, habilitado depois da referencia -> categoria KG",
                  x.inicio_historico is not None and x.inicio_historico > REF and x.peso_historico == 0
                  and x.proxy == D("5")
                  and x.origem_proxy == "categoria" and x.previsao == D("5"),
                  f"proxy {fmt(x.proxy)} ({x.origem_proxy}), final {fmt(x.previsao)}")
        x = prev[(l3.id, pa.id)]
        esperado = D(1) / 6 * 6 + D(5) / 6 * 20
        registrar("K08 L3/PA loja nova -> outras lojas da central",
                  x.proxy == D("20") and x.origem_proxy == "outras_lojas" and perto(x.previsao, esperado),
                  f"peso {fmt(x.peso_historico)}, própria {fmt(x.previsao_propria)}, proxy {fmt(x.proxy)}, "
                  f"final {fmt(x.previsao)} (esperado {fmt(esperado)}; L4 com 1000/dia fora)")
        x = prev[(l3.id, pb.id)]
        registrar("K09 L3/PB loja nova sem venda -> L1", x.proxy == D("20") and x.previsao == D("20"),
                  f"proxy {fmt(x.proxy)} ({x.origem_proxy}), final {fmt(x.previsao)}")
        x = prev[(l3.id, px.id)]
        registrar("K10 L3/PX sem proxy possivel -> None", x.proxy is None and x.previsao is None,
                  f"proxy {fmt(x.proxy)}, final {fmt(x.previsao)}")
        # K11: PN (40) e PC (8) estão em cold start em L1; se servissem de par,
        # o proxy da unidade de PS deixaria de ser 43,33.
        registrar("K11 cold start nao serve de proxy", perto(prev[(l1.id, ps.id)].proxy, unidade_l1),
                  f"proxy de PS {fmt(prev[(l1.id, ps.id)].proxy)} (só PA, PB, PD)")
        x = prev[(l1.id, p21.id)]
        registrar("K14 D28: nunca vendeu, habilitado ha 21 dias -> metade proxy, metade zero",
                  x.inicio_historico == date(2026, 9, 22) and x.peso_historico == D("0.5")
                  and x.previsao_propria == D("0") and x.proxy == D("15") and x.previsao == D("7.5"),
                  f"início {x.inicio_historico}, peso {fmt(x.peso_historico)}, própria {fmt(x.previsao_propria)}, "
                  f"proxy {fmt(x.proxy)}, final {fmt(x.previsao)}")
        x = prev[(l1.id, p49.id)]
        registrar("K15 D28: nunca vendeu, habilitado ha 49 dias -> historico proprio (zero), sem proxy",
                  x.peso_historico == 1 and x.proxy is None and x.previsao == D("0"),
                  f"peso {fmt(x.peso_historico)}, proxy {fmt(x.proxy)}, final {fmt(x.previsao)}")
        registrar("K13 L4 fora da central A1", all(lid != l4.id for lid, _ in prev), "nenhuma previsão de L4")
    finally:
        try:
            db.rollback()
            _limpar(db, negocio_ids)
        except Exception as e:
            print(f"[aviso] Erro na limpeza: {e}")
        db.close()


def parte_seed():
    db = SessionLocal()
    try:
        gestor = db.query(Usuario).filter(Usuario.email == "gestor@teste.com").first()
        if gestor is None:
            registrar("K12 seed", False, "gestor@teste.com não existe -> rode scripts/seed_dev.py e seed_vendas.py")
            return
        prev = prever_central(db, gestor.negocio_id, gestor.central_producao_id, REF, ALVO)
        ruins = [x for x in prev if x.peso_historico != 1 or x.proxy is not None or x.previsao is None]
        registrar("K12 seed sem cold start", len(prev) == 22 and not ruins,
                  f"{len(prev)} previsões (2 lojas × 11 produtos), {len(ruins)} com cold start ou sem valor")
    finally:
        db.close()


def main():
    try:
        parte_pura()
        parte_banco()
        parte_seed()
    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    print("\n=== Resultado do teste de cold start ===")
    for r in resultados:
        print(r)
    falhas = [r for r in resultados if r.startswith(FAIL)]
    if len(resultados) < TOTAL_CASOS:
        print(f"\nTESTE INCOMPLETO: só {len(resultados)} de {TOTAL_CASOS} casos rodaram")
    else:
        print(f"\n{'TODOS OS CASOS PASSARAM' if not falhas else f'{len(falhas)} CASO(S) FALHARAM'}")
    if len(resultados) < TOTAL_CASOS or falhas:
        sys.exit(1)


if __name__ == "__main__":
    main()
