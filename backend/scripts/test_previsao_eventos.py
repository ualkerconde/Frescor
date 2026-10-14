"""
Testa os eventos no motor de previsão (Fase 3 / F3): ajuste no dia
previsto (proposta D26) e exclusão dos dias de evento da base e da
tendência (doc §4.3).

Parte 1, funções puras (sem banco), série constante de 10/dia até a
referência 12/10/2026 (segunda), alvo 13/10 (terça):
  E01 multiplicador 1,5 -> 15; a previsão sem evento continua 10
  E02 valor fixo 15 substitui a previsão
  E03 valor fixo sem histórico -> 15
  E04 multiplicador sem histórico -> continua None (nada a multiplicar)
  E05 dois multiplicadores no mesmo dia -> se multiplicam (1,5 × 2)
  E06 valor fixo + multiplicador no mesmo dia -> vale o fixo
  E07 dois valores fixos -> vale o de maior id
  E08 evento que não cobre o alvo -> sem ajuste
  E09 evento de outro produto -> ignorado
  E10 dia de evento passado sai da base (sem o evento, a base subiria)
  E11 dias de evento saem da tendência (sem isso, a tendência iria a 1,3)
  E12 multiplicador 0 (loja fechada) -> 0
  E13 evento de um dia só, exatamente no alvo -> aplica

Parte 2, serviço com banco (prever_central):
  negócio A: central A1 com L1, L2 e L3 (inativa); central A2 com L4
  negócio B: loja LB
  P1 (10/dia) e P2 (20/dia) em L1 e L2; P1 em L4; L1/P1 vendeu 40 na
  terça de 2 semanas atrás (dia de evento passado ev5)
  eventos (todos da central A1, salvo indicação): ev1 ×2 em L1 (todos os
  produtos) no alvo; ev2 fixo 50 em L2/P2 no alvo; ev3 "todas as lojas"
  ×3 para P1 no alvo + 1; ev4 do negócio B, "todas" ×5 no alvo; ev5
  L1/P1 ×1 no dia passado; ev6 da central A2 em L4 ×9 no alvo; ev7
  "todas" da central A2 ×7 no alvo + 1; ev8 antigo sem central, "todas"
  ×4 no alvo + 2
  S01 só lojas ativas da central A1, só produtos habilitados
  S02 L1/P1: base 10 (dia de evento passado fora), ×2 -> 20
  S03 L1/P2: ×2 -> 40
  S04 L2/P1: sem evento -> 10 (o ×5 do negócio B não vale)
  S05 L2/P2: valor fixo 50
  S06 alvo + 1: P1 ×3 nas duas lojas ("todas"); P2 sem ajuste
  S07 eventos_das_lojas: cada loja recebe só os seus eventos
  S08 sem o ev5, o dia de 40 entra na base de L1/P1 (15) -> prova que a
      exclusão vem do evento gravado
  S09 alvo igual à referência -> ValueError
  S10 "todas" da central A2 vale em L4 e não em L1/L2 (D27)
  S11 evento antigo sem central: "todas" vale para o negócio inteiro

Uso: python scripts/test_previsao_eventos.py
"""

import sys
import uuid
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.evento import EscopoLoja, EscopoProduto, Evento, EventoLoja, EventoProduto, TipoAjuste  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402
from app.services.eventos_service import eventos_das_lojas  # noqa: E402
from app.services.previsao_calculo import EventoAplicavel, aplicar_eventos, eventos_do_produto, prever  # noqa: E402
from app.services.previsao_service import prever_central  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 24
PREFIXO_NEGOCIO_TESTE = "_Teste Eventos Prev"
D = Decimal
REF = date(2026, 10, 12)  # segunda
ALVO = REF + timedelta(days=1)
MULT, FIXO = TipoAjuste.MULTIPLICADOR, TipoAjuste.VALOR_FIXO

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def serie(dias, valor):
    return {REF - timedelta(days=k): valor(REF - timedelta(days=k)) for k in range(dias)}


def ev(id_, tipo, valor, inicio=ALVO, fim=None, produtos=None):
    return EventoAplicavel(id=id_, nome=f"ev{id_}", data_inicio=inicio, data_fim=fim or inicio, tipo_ajuste=tipo,
                           valor_ajuste=D(valor), produto_ids=None if produtos is None else frozenset(produtos))


def completo(s, eventos, produto_id=1):
    """Previsão final como o serviço faz: exclusão + ajuste, só eventos do produto."""
    evs = eventos_do_produto(eventos, produto_id)
    c = prever(s, REF, ALVO, evs)
    final, aplicados = aplicar_eventos(c.previsao, evs, ALVO)
    return c, final, aplicados


def ids(aplicados):
    return [e.id for e in aplicados]


def parte_pura():
    s10 = serie(56, lambda d: D("10"))
    c, f, a = completo(s10, [ev(1, MULT, "1.5")])
    registrar("E01 multiplicador 1,5", f == D("15") and c.previsao == D("10") and ids(a) == [1],
              f"sem evento {c.previsao}, final {f}, eventos {ids(a)}")
    _, f, a = completo(s10, [ev(1, FIXO, "15")])
    registrar("E02 valor fixo substitui", f == D("15") and ids(a) == [1], f"final {f}")
    c, f, a = completo({}, [ev(1, FIXO, "15")])
    registrar("E03 valor fixo sem historico", c.previsao is None and f == D("15"), f"sem evento {c.previsao}, final {f}")
    c, f, a = completo({}, [ev(1, MULT, "2")])
    registrar("E04 multiplicador sem historico", f is None and ids(a) == [1], f"final {f}, eventos {ids(a)}")
    _, f, a = completo(s10, [ev(1, MULT, "1.5"), ev(2, MULT, "2")])
    registrar("E05 multiplicadores se multiplicam", f == D("30") and ids(a) == [1, 2], f"final {f}, eventos {ids(a)}")
    _, f, a = completo(s10, [ev(1, MULT, "3"), ev(2, FIXO, "12")])
    registrar("E06 fixo vence multiplicador", f == D("12") and ids(a) == [2], f"final {f}, eventos {ids(a)}")
    _, f, a = completo(s10, [ev(7, FIXO, "70"), ev(3, FIXO, "30")])
    registrar("E07 dois fixos -> maior id", f == D("70") and ids(a) == [7], f"final {f}, eventos {ids(a)}")
    _, f, a = completo(s10, [ev(1, MULT, "2", inicio=ALVO + timedelta(days=1), fim=ALVO + timedelta(days=3))])
    registrar("E08 evento fora do alvo", f == D("10") and a == (), f"final {f}")
    _, f, a = completo(s10, [ev(1, MULT, "2", produtos={99})])
    registrar("E09 evento de outro produto", f == D("10") and a == (), f"final {f}")

    # E10: a terça de 2 semanas atrás vendeu 40 (evento passado).
    dia_ev = ALVO - timedelta(weeks=2)
    s_pico = serie(56, lambda d: D("40") if d == dia_ev else D("10"))
    # Com a mediana (padrão, D25), um pico isolado já não move a base; a
    # média deixa visível que o dia de evento saiu da conta.
    sem = prever(s_pico, REF, ALVO, estatistica="media")
    com = prever(s_pico, REF, ALVO, [ev(1, MULT, "1", inicio=dia_ev)], estatistica="media")
    registrar("E10 dia de evento sai da base", com.base == D("10") and com.semanas_na_base == 5 and sem.base == D("15"),
              f"com evento base {com.base} ({com.semanas_na_base} sem); sem o evento base {sem.base}")

    # E11: 2 dos últimos 7 dias venderam 30 por causa de um evento.
    ev_ini = REF - timedelta(days=1)
    s_ult = serie(56, lambda d: D("30") if d >= ev_ini else D("10"))
    # Tendência pela soma de propósito: com a mediana (padrão, D31), dois dias
    # de pico já não movem o fator e o teste não mostraria a exclusão.
    sem = prever(s_ult, REF, ALVO, metodo_tendencia="soma")
    com = prever(s_ult, REF, ALVO, [ev(1, MULT, "3", inicio=ev_ini, fim=REF)], metodo_tendencia="soma")
    registrar("E11 dias de evento saem da tendencia",
              com.tendencia == D("1") and com.dias_na_tendencia == 5 and sem.tendencia == D("1.3"),
              f"com evento tendência {com.tendencia} ({com.dias_na_tendencia} dias); sem o evento {sem.tendencia}")

    _, f, _ = completo(s10, [ev(1, MULT, "0")])
    registrar("E12 multiplicador 0", f == D("0"), f"final {f}")
    _, f, a = completo(s10, [ev(1, MULT, "2", inicio=ALVO, fim=ALVO)])
    registrar("E13 evento de um dia no alvo", f == D("20") and ids(a) == [1], f"final {f}")


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
            db.flush()
            return lj

        l1, l2, l3 = loja(neg_a, c_a1, "L1"), loja(neg_a, c_a1, "L2"), loja(neg_a, c_a1, "L3", ativo=False)
        l4, lb = loja(neg_a, c_a2, "L4"), loja(neg_b, c_b, "LB")
        p1 = Produto(negocio_id=neg_a.id, nome="_P1", codigo="P1", unidade_medida=UnidadeMedida.UN, ativo=True)
        p2 = Produto(negocio_id=neg_a.id, nome="_P2", codigo="P2", unidade_medida=UnidadeMedida.UN, ativo=True)
        pb = Produto(negocio_id=neg_b.id, nome="_PB", codigo="PB", unidade_medida=UnidadeMedida.UN, ativo=True)
        db.add_all([p1, p2, pb])
        db.flush()
        for p, lj in ((p1, l1), (p2, l1), (p1, l2), (p2, l2), (p1, l3), (p1, l4), (pb, lb)):
            db.add(ProdutoLoja(produto_id=p.id, loja_id=lj.id))

        dia_pico = ALVO - timedelta(weeks=2)
        for k in range(56):
            dia = REF - timedelta(days=k)
            for neg, lj, p, q in ((neg_a, l1, p1, "40" if dia == dia_pico else "10"), (neg_a, l1, p2, "20"),
                                  (neg_a, l2, p1, "10"), (neg_a, l2, p2, "20"), (neg_a, l3, p1, "10"),
                                  (neg_a, l4, p1, "10"), (neg_b, lb, pb, "10")):
                db.add(VendaDiaria(negocio_id=neg.id, loja_id=lj.id, produto_id=p.id, data=dia,
                                   quantidade=D(q), origem=OrigemVenda.MANUAL))

        def evento(neg, central, nome, tipo, valor, inicio, lojas=None, produtos=None):
            e = Evento(negocio_id=neg.id, central_producao_id=central.id if central else None, nome=nome,
                       data_inicio=inicio, data_fim=inicio,
                       escopo_loja=EscopoLoja.TODAS if lojas is None else EscopoLoja.ESPECIFICAS,
                       escopo_produto=EscopoProduto.TODOS if produtos is None else EscopoProduto.ESPECIFICOS,
                       tipo_ajuste=tipo, valor_ajuste=D(valor))
            db.add(e)
            db.flush()
            for lj in lojas or []:
                db.add(EventoLoja(evento_id=e.id, loja_id=lj.id, negocio_id=neg.id))
            for p in produtos or []:
                db.add(EventoProduto(evento_id=e.id, produto_id=p.id, negocio_id=neg.id))
            return e

        alvo2, alvo3 = ALVO + timedelta(days=1), ALVO + timedelta(days=2)
        ev1 = evento(neg_a, c_a1, "ev1", MULT, "2", ALVO, lojas=[l1])
        ev2 = evento(neg_a, c_a1, "ev2", FIXO, "50", ALVO, lojas=[l2], produtos=[p2])
        ev3 = evento(neg_a, c_a1, "ev3", MULT, "3", alvo2, produtos=[p1])
        ev4 = evento(neg_b, c_b, "ev4", MULT, "5", ALVO)
        ev5 = evento(neg_a, c_a1, "ev5", MULT, "1", dia_pico, lojas=[l1], produtos=[p1])
        ev6 = evento(neg_a, c_a2, "ev6", MULT, "9", ALVO, lojas=[l4])
        ev7 = evento(neg_a, c_a2, "ev7", MULT, "7", alvo2)  # "todas" da central A2 (D27)
        ev8 = evento(neg_a, None, "ev8", MULT, "4", alvo3)  # antigo, sem central: "todas" = negócio inteiro
        db.commit()

        def por_chave(lista):
            return {(x.loja_id, x.produto_id): x for x in lista}

        prev = por_chave(prever_central(db, neg_a.id, c_a1.id, REF, ALVO))
        # Ids de loja e de produto vêm de sequências diferentes e podem coincidir.
        nl = {l1.id: "L1", l2.id: "L2", l3.id: "L3", l4.id: "L4"}
        npr = {p1.id: "P1", p2.id: "P2"}
        print("Previsões de 13/10 (central A1):")
        for (lid, pid), x in prev.items():
            print(f"  {nl[lid]}/{npr[pid]}: base {x.componentes.base} ({x.componentes.semanas_na_base} sem), "
                  f"sem evento {x.previsao_sem_evento}, final {x.previsao}, eventos {[e.nome for e in x.eventos]}")

        registrar("S01 so lojas ativas da central e produtos habilitados",
                  sorted(prev) == sorted([(l1.id, p1.id), (l1.id, p2.id), (l2.id, p1.id), (l2.id, p2.id)]),
                  f"{sorted((nl[a], npr[b]) for a, b in prev)}")
        x = prev[(l1.id, p1.id)]
        registrar("S02 L1/P1: base sem o dia de evento, x2",
                  x.componentes.base == D("10") and x.previsao == D("20") and [e.id for e in x.eventos] == [ev1.id],
                  f"base {x.componentes.base}, final {x.previsao}")
        x = prev[(l1.id, p2.id)]
        registrar("S03 L1/P2 x2", x.previsao == D("40"), f"final {x.previsao}")
        x = prev[(l2.id, p1.id)]
        registrar("S04 L2/P1 sem evento (o x5 do negocio B nao vale)", x.previsao == D("10") and x.eventos == (),
                  f"final {x.previsao}")
        x = prev[(l2.id, p2.id)]
        registrar("S05 L2/P2 valor fixo 50", x.previsao == D("50") and x.previsao_sem_evento == D("20"),
                  f"sem evento {x.previsao_sem_evento}, final {x.previsao}")

        prev2 = por_chave(prever_central(db, neg_a.id, c_a1.id, REF, alvo2))
        finais = {(nl[a], npr[b]): x.previsao for (a, b), x in prev2.items()}
        registrar("S06 alvo+1: P1 x3 nas duas lojas, P2 sem ajuste (x7 da central A2 nao vale)",
                  finais == {("L1", "P1"): D("30"), ("L1", "P2"): D("20"), ("L2", "P1"): D("30"), ("L2", "P2"): D("20")},
                  f"{finais}")

        carregados = eventos_das_lojas(db, neg_a.id, [l1.id, l2.id], REF - timedelta(days=48), alvo3)
        obtido = {nl[lid]: sorted(e.nome for e in evs) for lid, evs in carregados.items()}
        registrar("S07 eventos_das_lojas por loja",
                  obtido == {"L1": ["ev1", "ev3", "ev5", "ev8"], "L2": ["ev2", "ev3", "ev8"]},
                  f"{obtido} (ev4 de B, ev6 de L4 e ev7 'todas' da A2 fora)")
        x4 = por_chave(prever_central(db, neg_a.id, c_a2.id, REF, alvo2)).get((l4.id, p1.id))
        registrar("S10 'todas' da central A2 vale em L4 (D27)",
                  x4 is not None and x4.previsao == D("70") and [e.nome for e in x4.eventos] == ["ev7"],
                  f"L4/P1 final {x4.previsao if x4 else None}, eventos {[e.nome for e in x4.eventos] if x4 else None}")
        prev3 = por_chave(prever_central(db, neg_a.id, c_a1.id, REF, alvo3))
        x4b = por_chave(prever_central(db, neg_a.id, c_a2.id, REF, alvo3)).get((l4.id, p1.id))
        registrar("S11 evento antigo sem central: 'todas' = negocio inteiro",
                  prev3[(l1.id, p1.id)].previsao == D("40") and prev3[(l2.id, p2.id)].previsao == D("80")
                  and x4b is not None and x4b.previsao == D("40"),
                  f"L1/P1 {prev3[(l1.id, p1.id)].previsao}, L2/P2 {prev3[(l2.id, p2.id)].previsao}, "
                  f"L4/P1 {x4b.previsao if x4b else None}")

        db.query(EventoProduto).filter(EventoProduto.evento_id == ev5.id).delete(synchronize_session=False)
        db.query(EventoLoja).filter(EventoLoja.evento_id == ev5.id).delete(synchronize_session=False)
        db.query(Evento).filter(Evento.id == ev5.id).delete(synchronize_session=False)
        db.commit()
        # Média de propósito: com a mediana (padrão), o pico isolado não moveria a base.
        x = por_chave(prever_central(db, neg_a.id, c_a1.id, REF, ALVO, estatistica="media"))[(l1.id, p1.id)]
        registrar("S08 sem o ev5 o dia de 40 entra na base", x.componentes.base == D("15"),
                  f"base {x.componentes.base}")

        try:
            prever_central(db, neg_a.id, c_a1.id, REF, REF)
            registrar("S09 alvo = referencia", False, "nao levantou erro")
        except ValueError as e:
            registrar("S09 alvo = referencia", True, f"ValueError: {e}")
        _ = (ev4, ev6, ev7, ev8, lb)
    finally:
        try:
            db.rollback()
            _limpar(db, negocio_ids)
        except Exception as e:
            print(f"[aviso] Erro na limpeza: {e}")
        db.close()


def main():
    try:
        parte_pura()
        parte_banco()
    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    print("\n=== Resultado do teste de eventos na previsão ===")
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
