"""
Testa o núcleo de cálculo da necessidade (Fase 4 / N3), sem banco:
cobertura pelo calendário e pela validade (D36), contagem válida pela hora
local da loja com 2 h de folga (D33, D44), margem (D34), arredondamento
(D37), projeção até a chegada com prazo 0 e 1 e trânsito dentro dela
(D43, D45), validade do estoque (D35) e avisos.

Data de produção padrão D = segunda 19/10/2026. Fuso America/Sao_Paulo
(UTC−3, sem horário de verão). Fechamento padrão 21:00 -> a contagem vale
desde domingo 18/10 às 19:00 local = 22:00 UTC. Contagem padrão: 21:00
local de 18/10 = 00:00 UTC de 19/10.

Casos (conta à mão no próprio caso):
  N01 diário, validade 1: a sobra contada vence antes da chegada -> conta 0
  N02 seg/qua/sex, validade 3, margem 5%: cobertura seg+ter; estoque conta
  N03 sexta, seg/qua/sex: cobertura de 3 dias (sex, sáb, dom)
  N04 seg/qui, validade 2: cobertura de 3 dias limitada a 2, com aviso
  N05 sem calendário -> sem necessidade, aviso (D42)
  N06 dia fora do calendário -> ValueError
  N07 sem previsão para um dia da cobertura -> sem necessidade, aviso
  N08 limite da folga: contagem exatamente no fechamento − 2 h vale; 1 s
      antes não vale (conta 0, aviso)
  N09 fuso: 21:30 UTC de 18/10 = 18:30 local, antes do limite -> não vale
  N10 nunca contado -> conta 0, aviso
  N11 estoque acima do alvo -> necessidade 0, aviso
  N12 margem: padrão 10%, do produto, pouco histórico pelo menos 20%
  N13 arredondamento: UN para cima no inteiro; KG para cima em 0,1
  N14 D45, prazo 0 x prazo 1 com o mesmo estoque: prazo 1 desconta a venda
      de D antes da chegada
  N15 D45, prazo 1 com trânsito: o lote que chega em D é vendido em D; só a
      sobra conta (fora da projeção daria 3 em vez de 18)
  N16 prazo 1, venda de D maior que o estoque -> estoque na chegada 0
  N17 trânsito antes de D ou na chegada não entra na projeção
  N18 prazo 1, validade 2: estoque contado e sobra do trânsito vencem antes
      da chegada
  N19 validade menor ou igual ao prazo -> nada chega dentro da validade
  N20 KG: necessidade com uma casa, para cima
  N21 pouco histórico de ponta a ponta: margem 20%
  N22 previsão zero -> necessidade 0, sem aviso de estoque acima

Uso: python scripts/test_necessidade_calculo.py
"""

import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.necessidade_calculo import (  # noqa: E402
    AVISO_COBERTURA_MAIOR_QUE_VALIDADE,
    AVISO_CONTAGEM_DESATUALIZADA,
    AVISO_ESTOQUE_ACIMA_DO_MAXIMO,
    AVISO_SEM_CALENDARIO,
    AVISO_SEM_CONTAGEM,
    AVISO_SEM_PREVISAO,
    AVISO_VALIDADE_MENOR_QUE_PRAZO,
    ORIGEM_MARGEM_PADRAO,
    ORIGEM_MARGEM_POUCO_HISTORICO,
    ORIGEM_MARGEM_PRODUTO,
    Contagem,
    EntradaNecessidade,
    LoteTransito,
    arredondar,
    calcular_necessidade,
    margem_aplicada,
)

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 22
D = Decimal
SEG = date(2026, 10, 19)
SEX = date(2026, 10, 23)
TODOS = frozenset(range(7))
SEG_QUA_SEX = frozenset({0, 2, 4})
SEG_QUI = frozenset({0, 3})
# 21:00 local de domingo 18/10 (UTC−3).
CONTAGEM_PADRAO_UTC = datetime(2026, 10, 19, 0, 0)

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def dia(base, k):
    return base + timedelta(days=k)


def entrada(**kw):
    padrao = dict(
        data_producao=SEG, prazo_entrega_dias=0, dias_producao=TODOS, dias_validade=None, margem_produto=None,
        unidade="UN", previsoes={}, pouco_historico=False, contagem=None, transito=(),
    )
    padrao.update(kw)
    return EntradaNecessidade(**padrao)


def contagem(qtd, quando=CONTAGEM_PADRAO_UTC):
    return Contagem(quantidade=D(qtd), atualizado_em_utc=quando)


def resumo(r):
    return (f"cobertura={[d.strftime('%d/%m') for d in r.dias_cobertura]} minimo={r.minimo} margem={r.margem} "
            f"alvo={r.alvo} estoque_chegada={r.estoque_na_chegada} nec={r.necessidade} avisos={list(r.avisos)}")


def caso(nome, e, *, necessidade, avisos=(), **esperados):
    """Roda o cálculo e confere a necessidade, os avisos e campos extras."""
    try:
        r = calcular_necessidade(e)
    except Exception as ex:
        registrar(nome, False, f"erro {type(ex).__name__}: {ex}")
        return None
    erros = []
    if r.necessidade != (None if necessidade is None else D(necessidade)):
        erros.append(f"necessidade {r.necessidade} != {necessidade}")
    if sorted(r.avisos) != sorted(avisos):
        erros.append(f"avisos {list(r.avisos)} != {list(avisos)}")
    for campo, valor in esperados.items():
        obtido = getattr(r, campo)
        if obtido != valor:
            erros.append(f"{campo} {obtido} != {valor}")
    registrar(nome, not erros, resumo(r) + (f" | {'; '.join(erros)}" if erros else ""))
    return r


def main():
    # N01: cobertura [seg]; mínimo 40; alvo 40 × 1,10 = 44. Contado 12 em 18/10,
    # validade 1 -> vale até 18/10 -> vencido na chegada (19/10). Necessidade 44.
    caso("N01 validade 1: sobra contada vence", entrada(
        dias_validade=1, previsoes={SEG: D(40)}, contagem=contagem(12)),
        necessidade=44, estoque_na_chegada=D(0), vencido_ate_chegada=D(12), estoque_considerado=D(12))

    # N02: seg/qua/sex -> cobre seg e ter (qua tem produção). 20 + 15 = 35;
    # × 1,05 = 36,75. Contado 10 em 18/10, validade 3 -> vale até 20/10: conta.
    # 36,75 − 10 = 26,75 -> 27.
    caso("N02 seg/qua/sex, margem 5%", entrada(
        dias_producao=SEG_QUA_SEX, dias_validade=3, margem_produto=D("5"),
        previsoes={SEG: D(20), dia(SEG, 1): D(15)}, contagem=contagem(10)),
        necessidade=27, minimo=D(35), origem_margem=ORIGEM_MARGEM_PRODUTO, estoque_na_chegada=D(10),
        dias_cobertura=(SEG, dia(SEG, 1)))

    # N03: sexta -> cobre sex, sáb, dom (próxima produção na segunda). 10 + 20 + 18
    # = 48; × 1,10 = 52,8. Contado 0 (contagem válida, 21:00 local de 22/10). -> 53.
    caso("N03 sexta: cobertura de 3 dias", entrada(
        data_producao=SEX, dias_producao=SEG_QUA_SEX, dias_validade=3,
        previsoes={SEX: D(10), dia(SEX, 1): D(20), dia(SEX, 2): D(18)},
        contagem=contagem(0, datetime(2026, 10, 23, 0, 0))),
        necessidade=53, minimo=D(48), dias_cobertura=(SEX, dia(SEX, 1), dia(SEX, 2)))

    # N04: seg/qui -> 3 dias (seg, ter, qua); validade 2 -> só seg e ter.
    # 10 + 10 = 20 (não 30); × 1,10 = 22.
    caso("N04 cobertura limitada pela validade", entrada(
        dias_producao=SEG_QUI, dias_validade=2, contagem=contagem(0),
        previsoes={SEG: D(10), dia(SEG, 1): D(10), dia(SEG, 2): D(10)}),
        necessidade=22, avisos=(AVISO_COBERTURA_MAIOR_QUE_VALIDADE,), minimo=D(20),
        dias_cobertura_sem_limite=3)

    caso("N05 sem calendario", entrada(dias_producao=frozenset(), previsoes={SEG: D(10)}),
         necessidade=None, avisos=(AVISO_SEM_CALENDARIO,))

    try:
        calcular_necessidade(entrada(data_producao=dia(SEG, 1), dias_producao=SEG_QUI, previsoes={}))
        registrar("N06 dia fora do calendario", False, "não levantou erro")
    except ValueError as ex:
        registrar("N06 dia fora do calendario", True, f"ValueError: {ex}")

    caso("N07 sem previsao num dia da cobertura", entrada(
        dias_producao=SEG_QUA_SEX, dias_validade=3, previsoes={SEG: D(20), dia(SEG, 1): None},
        contagem=contagem(0)),
        necessidade=None, avisos=(AVISO_SEM_PREVISAO,))

    # N08: limite = 18/10 21:00 local − 2 h = 19:00 local = 22:00 UTC.
    # Validade 5, contado 30, previsão 20 -> alvo 22.
    no_limite = caso("N08a contagem exatamente no limite vale", entrada(
        dias_validade=5, previsoes={SEG: D(20)}, contagem=contagem(30, datetime(2026, 10, 18, 22, 0, 0))),
        necessidade=0, avisos=(AVISO_ESTOQUE_ACIMA_DO_MAXIMO,), contagem_valida=True)
    antes = caso("N08b contagem 1 s antes do limite nao vale", entrada(
        dias_validade=5, previsoes={SEG: D(20)}, contagem=contagem(30, datetime(2026, 10, 18, 21, 59, 59))),
        necessidade=22, avisos=(AVISO_CONTAGEM_DESATUALIZADA,), contagem_valida=False, estoque_considerado=D(0))
    # Os dois juntos contam como um caso no total.
    if no_limite is not None and antes is not None:
        a, b = resultados.pop(), resultados.pop()
        ok = a.startswith(PASS) and b.startswith(PASS)
        registrar("N08 folga de 2 h no limite", ok, f"{b} || {a}")

    # N09: 21:30 UTC = 18:30 local < 19:00 -> não vale. Tratando o UTC como hora
    # local (erro de fuso), 21:30 >= 19:00 e valeria.
    r = caso("N09 fuso: hora UTC convertida para a local", entrada(
        dias_validade=5, previsoes={SEG: D(20)}, contagem=contagem(30, datetime(2026, 10, 18, 21, 30))),
        necessidade=22, avisos=(AVISO_CONTAGEM_DESATUALIZADA,), contagem_valida=False)
    if r is not None and r.contagem_local is not None and r.contagem_local.time() != time(18, 30):
        resultados[-1] = f"{FAIL} N09 fuso: hora local {r.contagem_local} != 18:30"

    caso("N10 nunca contado", entrada(dias_validade=5, previsoes={SEG: D(20)}),
         necessidade=22, avisos=(AVISO_SEM_CONTAGEM,), estoque_contado=None)

    caso("N11 estoque acima do alvo", entrada(dias_validade=5, previsoes={SEG: D(20)}, contagem=contagem(100)),
         necessidade=0, avisos=(AVISO_ESTOQUE_ACIMA_DO_MAXIMO,), estoque_na_chegada=D(100))

    margens = {
        (None, False): (D(10), ORIGEM_MARGEM_PADRAO),
        (D(5), False): (D(5), ORIGEM_MARGEM_PRODUTO),
        (D(0), False): (D(0), ORIGEM_MARGEM_PRODUTO),
        (None, True): (D(20), ORIGEM_MARGEM_POUCO_HISTORICO),
        (D(5), True): (D(20), ORIGEM_MARGEM_POUCO_HISTORICO),
        (D(30), True): (D(30), ORIGEM_MARGEM_PRODUTO),
    }
    erradas = {k: margem_aplicada(*k) for k, v in margens.items() if margem_aplicada(*k) != v}
    registrar("N12 margem (D34)", not erradas, "6 combinações certas" if not erradas else f"erradas: {erradas}")

    arred = {("10.01", "UN"): "11", ("12", "UN"): "12", ("0", "UN"): "0",
             ("4.31", "KG"): "4.4", ("4.30", "KG"): "4.3", ("0.01", "KG"): "0.1"}
    erradas = {k: arredondar(D(k[0]), k[1]) for k, v in arred.items() if arredondar(D(k[0]), k[1]) != D(v)}
    registrar("N13 arredondamento (D37)", not erradas, "6 valores certos" if not erradas else f"errados: {erradas}")

    # N14: validade 5, contado 30 em 18/10.
    # prazo 0: cobre seg (20) -> alvo 22 < 30 -> 0.
    # prazo 1: chega ter; seg vende 20 do estoque -> sobra 10; cobre ter (25) ->
    # alvo 27,5 − 10 = 17,5 -> 18.
    prev = {SEG: D(20), dia(SEG, 1): D(25)}
    p0 = caso("N14a prazo 0", entrada(dias_validade=5, previsoes=prev, contagem=contagem(30)),
              necessidade=0, avisos=(AVISO_ESTOQUE_ACIMA_DO_MAXIMO,), dias_ate_chegada=())
    p1 = caso("N14b prazo 1", entrada(dias_validade=5, prazo_entrega_dias=1, previsoes=prev, contagem=contagem(30)),
              necessidade=18, chegada=dia(SEG, 1), dias_ate_chegada=(SEG,), consumo_ate_chegada=D(20),
              estoque_na_chegada=D(10), dias_cobertura=(dia(SEG, 1),))
    if p0 is not None and p1 is not None:
        a, b = resultados.pop(), resultados.pop()
        registrar("N14 D45: prazo 0 x prazo 1", a.startswith(PASS) and b.startswith(PASS), f"{b} || {a}")

    # N15: prazo 1, contado 5, trânsito de 25 chegando seg. Seg vende 20: sai
    # primeiro o contado (vence antes), depois 15 do trânsito -> sobra 10 na
    # chegada; alvo 27,5 − 10 = 17,5 -> 18. Com o trânsito fora da projeção:
    # 27,5 − max(0, 5 − 20) − 25 = 2,5 -> 3 (faltaria um dia de venda).
    caso("N15 D45: transito dentro da projecao", entrada(
        dias_validade=5, prazo_entrega_dias=1, previsoes=prev, contagem=contagem(5),
        transito=(LoteTransito(SEG, D(25)),)),
        necessidade=18, transito_considerado=D(25), estoque_na_chegada=D(10), consumo_ate_chegada=D(20))

    # N16: contado 5 e venda de 20 na seg -> nada sobra; 27,5 -> 28.
    caso("N16 venda antes da chegada maior que o estoque", entrada(
        dias_validade=5, prazo_entrega_dias=1, previsoes=prev, contagem=contagem(5)),
        necessidade=28, estoque_na_chegada=D(0), consumo_ate_chegada=D(5))

    # N17: lotes que chegam no domingo (já estão na contagem) e na terça (o dia
    # da chegada) ficam fora; mesmo número do N16.
    caso("N17 transito fora da janela ignorado", entrada(
        dias_validade=5, prazo_entrega_dias=1, previsoes=prev, contagem=contagem(5),
        transito=(LoteTransito(dia(SEG, -1), D(50)), LoteTransito(dia(SEG, 1), D(50)))),
        necessidade=28, transito_considerado=D(0))

    # N18: prazo 1, validade 2. Contado 5 em 18/10: fabricado 17/10, vale até
    # 18/10 -> vence antes de seg. Trânsito 30 entregue seg: fabricado dom,
    # vale até seg; seg vende 20, sobram 10 que vencem antes de ter. Estoque na
    # chegada 0; vencido 5 + 10 = 15; cobre ter (fabricado seg, vale até ter):
    # 25 × 1,10 = 27,5 -> 28.
    caso("N18 validade na projecao", entrada(
        dias_validade=2, prazo_entrega_dias=1, previsoes=prev, contagem=contagem(5),
        transito=(LoteTransito(SEG, D(30)),)),
        necessidade=28, estoque_na_chegada=D(0), vencido_ate_chegada=D(15), consumo_ate_chegada=D(20))

    # N19: prazo 1, validade 1 -> fabricado seg, vale só seg; chega ter.
    caso("N19 validade menor ou igual ao prazo", entrada(
        dias_validade=1, prazo_entrega_dias=1, previsoes=prev, contagem=contagem(0)),
        necessidade=None, avisos=(AVISO_COBERTURA_MAIOR_QUE_VALIDADE, AVISO_VALIDADE_MENOR_QUE_PRAZO))

    # N20: KG, 30,123 × 1,10 = 33,1353 -> 33,2.
    caso("N20 KG com uma casa para cima", entrada(
        unidade="KG", dias_validade=1, previsoes={SEG: D("30.123")}, contagem=contagem(0)),
        necessidade=D("33.2"))

    # N21: pouco histórico, sem margem no produto -> 20%: 40 × 1,2 = 48.
    caso("N21 pouco historico: margem 20%", entrada(
        dias_validade=1, previsoes={SEG: D(40)}, pouco_historico=True),
        necessidade=48, avisos=(AVISO_SEM_CONTAGEM,), margem=D(20), origem_margem=ORIGEM_MARGEM_POUCO_HISTORICO)

    caso("N22 previsao zero", entrada(dias_validade=1, previsoes={SEG: D(0)}, contagem=contagem(0)),
         necessidade=0, alvo=D(0))

    print("\n=== Resultado do teste do cálculo da necessidade (N3) ===")
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
