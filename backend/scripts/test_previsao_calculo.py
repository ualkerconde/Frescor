"""
Testa o núcleo de cálculo do motor de previsão (Fase 3 / F2), sem banco:
base por dia da semana em 6 semanas (D18), tendência limitada a 0,7–1,3
com mínimo de 5 dos 7 dias (D19) e previsão sem arredondamento (D21).

Séries montadas à mão, terminando na data de referência 12/10/2026
(segunda). Alvo padrão: 13/10 (terça).

Casos:
  C01 série constante -> previsão = constante, tendência 1
  C02 padrão semanal (fatores do seed) -> cada dia da semana sai com o seu
      fator, nos 7 dias seguintes (horizonte da D22)
  C03 alta moderada na última semana (+20%) -> tendência 1,2 (base pela
      mediana, D25)
  C04 queda forte (-50%) -> tendência limitada a 0,7 (bruta 0,5)
  C05 alta forte (+100%) -> tendência limitada a 1,3 (bruta 2,0)
  C06 ruído de ±20% em volta do padrão semanal -> erro pequeno, tendência ~1
  C07 só 2 semanas de histórico -> base com 2 semanas, tendência calculada
  C08 só 1 semana de histórico -> base com 1 semana, tendência 1 (sem base
      para comparar)
  C09 sem histórico -> base e previsão None
  C10 dias faltantes ficam fora da média (não contam como zero)
  C11 4 de 7 dias na tendência -> fator 1, mesmo com +50%
  C12 exatamente 5 de 7 dias -> tendência calculada (limite da D19)
  C13 histórico todo zero -> previsão 0, sem divisão por zero
  C14 dados depois da referência são ignorados
  C15 alvo igual ou antes da referência -> ValueError
  C16 sem arredondamento: KG com 3 casas e média 10,5 em UN
  C17 só 6 semanas: a 7ª semana para trás não entra na base
  C18 previsão = base × tendência
  C19 a base padrão é a mediana (D25): um pico não move a base (com a
      média, moveria)
  C20 D31: pico nos últimos 7 dias -> tendência pela mediana das razões
      diárias (padrão) fica 1; pela soma iria a 1,3
  C21 D31: alta real de 20% nos 7 dias -> as duas dão 1,2

Uso: python scripts/test_previsao_calculo.py
"""

import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.previsao_calculo import prever  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 21
D = Decimal
REF = date(2026, 10, 12)  # segunda
ALVO = REF + timedelta(days=1)  # terça
# Fatores do seed_vendas, por weekday() (0 = segunda).
FATORES = {0: D("0.85"), 1: D("0.85"), 2: D("1"), 3: D("1"), 4: D("1"), 5: D("1.35"), 6: D("1.25")}
TOL = D("0.000000001")

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def perto(a, b, tol=TOL):
    return a is not None and b is not None and abs(a - b) <= tol


def serie(dias, valor):
    """Série de `dias` dias terminando em REF; `valor(dia)` dá a quantidade (ou None)."""
    return {REF - timedelta(days=k): valor(REF - timedelta(days=k)) for k in range(dias)}


def fmt(x):
    return "None" if x is None else f"{x:.4f}"


def resumo(c):
    return (f"base {fmt(c.base)} ({c.semanas_na_base} sem), tendência {fmt(c.tendencia)} "
            f"(bruta {fmt(c.tendencia_bruta)}, {c.dias_na_tendencia} dias), previsão {fmt(c.previsao)}")


def main():
    try:
        # C01
        c = prever(serie(56, lambda d: D("10")), REF, ALVO)
        registrar("C01 constante", c.previsao == D("10") and c.tendencia == D("1") and c.semanas_na_base == 6, resumo(c))

        # C02: 7 dias seguintes, cada um com o seu fator.
        s = serie(56, lambda d: D("100") * FATORES[d.weekday()])
        erros = []
        detalhes = []
        for h in range(1, 8):
            alvo = REF + timedelta(days=h)
            c = prever(s, REF, alvo)
            esperado = D("100") * FATORES[alvo.weekday()]
            detalhes.append(f"{alvo:%a} {c.previsao:.2f}")
            if not perto(c.previsao, esperado) or c.tendencia != D("1"):
                erros.append(f"{alvo} previu {c.previsao}, esperado {esperado}")
        registrar("C02 padrao semanal, horizonte de 7 dias", not erros, "; ".join(erros) or ", ".join(detalhes))

        # C03: 100 até a semana passada, 120 nos últimos 7 dias.
        s = serie(56, lambda d: D("120") if d > REF - timedelta(days=7) else D("100"))
        c = prever(s, REF, ALVO)
        # base = mediana de [120, 100×5] = 100 (D25); previsão = 100 × 1,2 = 120
        registrar("C03 alta de 20%", c.base == D("100") and c.tendencia == D("1.2") and c.previsao == D("120"),
                  resumo(c))

        # C04 e C05: limites.
        s = serie(56, lambda d: D("50") if d > REF - timedelta(days=7) else D("100"))
        c = prever(s, REF, ALVO)
        registrar("C04 queda de 50% -> limite 0,7", c.tendencia == D("0.7") and c.tendencia_bruta == D("0.5"), resumo(c))
        s = serie(56, lambda d: D("200") if d > REF - timedelta(days=7) else D("100"))
        c = prever(s, REF, ALVO)
        registrar("C05 alta de 100% -> limite 1,3", c.tendencia == D("1.3") and c.tendencia_bruta == D("2"), resumo(c))

        # C06: ruído determinístico.
        rnd = random.Random(42)
        s = serie(56, lambda d: D("100") * FATORES[d.weekday()] * D(str(round(rnd.uniform(0.8, 1.2), 3))))
        # Tendência pela mediana (padrão, D31) é um pouco mais sensível a ruído
        # que a soma: o limite é 12% para ela e 10% para a soma (os dois números
        # aparecem na saída; o custo foi medido no backtest e aceito na D31).
        piores = {"mediana": [], "soma": []}
        for h in range(1, 8):
            alvo = REF + timedelta(days=h)
            esperado = D("100") * FATORES[alvo.weekday()]
            for m in piores:
                c = prever(s, REF, alvo, metodo_tendencia=m)
                piores[m].append(abs(c.previsao - esperado) / esperado)
        tend = prever(s, REF, ALVO).tendencia
        pior, pior_soma = max(piores["mediana"]), max(piores["soma"])
        registrar("C06 ruido de 20% -> erro pequeno, tendencia ~1",
                  pior < D("0.12") and pior_soma < D("0.10") and D("0.9") <= tend <= D("1.1"),
                  f"maior erro nos 7 dias: {pior:.1%} (padrão, mediana) / {pior_soma:.1%} (soma); "
                  f"tendência {tend:.4f}")

        # C07 e C08: pouco histórico.
        c = prever(serie(14, lambda d: D("10")), REF, ALVO)
        registrar("C07 2 semanas", c.semanas_na_base == 2 and c.previsao == D("10") and c.dias_na_tendencia == 7,
                  resumo(c))
        c = prever(serie(7, lambda d: D("10")), REF, ALVO)
        registrar("C08 1 semana -> tendencia 1", c.semanas_na_base == 1 and c.tendencia == D("1")
                  and c.tendencia_bruta is None and c.dias_na_tendencia == 0 and c.previsao == D("10"), resumo(c))

        # C09
        c = prever({}, REF, ALVO)
        registrar("C09 sem historico", c.base is None and c.previsao is None and c.semanas_na_base == 0, resumo(c))

        # C10: duas terças faltantes; se contassem como zero, a base cairia para 6,67.
        faltam = {ALVO - timedelta(weeks=2), ALVO - timedelta(weeks=4)}
        c = prever(serie(56, lambda d: None if d in faltam else D("10")), REF, ALVO)
        registrar("C10 faltantes fora da media", c.base == D("10") and c.semanas_na_base == 4, resumo(c))

        # C11 e C12: mínimo de dias na tendência. Última semana a 150; os
        # dias marcados como faltantes saem da tendência.
        def ultima_semana(faltantes):
            def valor(d):
                if d > REF - timedelta(days=7):
                    return None if (REF - d).days < faltantes else D("150")
                return D("100")
            return valor

        c = prever(serie(56, ultima_semana(3)), REF, ALVO)
        registrar("C11 4 de 7 dias -> fator 1", c.dias_na_tendencia == 4 and c.tendencia == D("1")
                  and c.tendencia_bruta is None, resumo(c))
        c = prever(serie(56, ultima_semana(2)), REF, ALVO)
        registrar("C12 5 de 7 dias -> calcula", c.dias_na_tendencia == 5 and c.tendencia == D("1.3")
                  and c.tendencia_bruta == D("1.5"), resumo(c))

        # C13
        c = prever(serie(56, lambda d: D("0")), REF, ALVO)
        registrar("C13 historico zero", c.previsao == D("0") and c.tendencia == D("1"), resumo(c))

        # C14: valores enormes depois da referência não mudam nada.
        s = serie(56, lambda d: D("10"))
        s_vazada = dict(s) | {REF + timedelta(days=k): D("9999") for k in range(1, 15)}
        c, c_vaz = prever(s, REF, ALVO), prever(s_vazada, REF, ALVO)
        registrar("C14 dados depois da referencia ignorados", c == c_vaz, resumo(c_vaz))

        # C15
        erros = []
        for alvo in (REF, REF - timedelta(days=1)):
            try:
                prever(s, REF, alvo)
                erros.append(f"alvo {alvo} aceito")
            except ValueError:
                pass
        registrar("C15 alvo <= referencia -> ValueError", not erros, "; ".join(erros) or "recusado nos 2 casos")

        # C16: sem arredondamento.
        c_kg = prever(serie(56, lambda d: D("2.345")), REF, ALVO)
        alterna = {ALVO - timedelta(weeks=k): D("10") if k % 2 else D("11") for k in range(1, 7)}
        c_un = prever(alterna, REF, ALVO)
        registrar("C16 sem arredondamento", c_kg.previsao == D("2.345") and c_un.previsao == D("10.5"),
                  f"KG {c_kg.previsao}, UN {c_un.previsao}")

        # C17: 1000 na 7ª terça para trás; dentro de 6 semanas tudo 10.
        fora = ALVO - timedelta(weeks=7)
        c = prever(serie(56, lambda d: D("1000") if d == fora else D("10")), REF, ALVO)
        registrar("C17 janela de 6 semanas", c.base == D("10") and c.semanas_na_base == 6, resumo(c))

        # C18
        rnd = random.Random(7)
        s = serie(56, lambda d: D(str(rnd.randint(50, 150))))
        c = prever(s, REF, ALVO)
        registrar("C18 previsao = base x tendencia", c.previsao == c.base * c.tendencia, resumo(c))

        # C19: um pico (100) na terça de 3 semanas atrás, num histórico de 10.
        pico = ALVO - timedelta(weeks=3)
        s = serie(56, lambda d: D("100") if d == pico else D("10"))
        padrao, media = prever(s, REF, ALVO).base, prever(s, REF, ALVO, estatistica="media").base
        registrar("C19 padrao = mediana (D25): pico nao move a base", padrao == D("10") and media == D("25"),
                  f"base padrão {padrao}; com a média seria {media}")

        # C20/C21 (D31): tendência pela mediana das razões diárias (padrão) x soma.
        pico_recente = REF - timedelta(days=2)
        s = serie(56, lambda d: D("100") if d == pico_recente else D("10"))
        soma, mediana = prever(s, REF, ALVO, metodo_tendencia="soma"), prever(s, REF, ALVO)
        registrar("C20 pico nos ultimos 7 dias: soma infla, mediana (padrao) nao",
                  soma.tendencia == D("1.3") and mediana.tendencia == D("1") and mediana.previsao == D("10"),
                  f"soma: tendência {soma.tendencia} (bruta {soma.tendencia_bruta:.4f}), previsão {soma.previsao}; "
                  f"mediana: tendência {mediana.tendencia}, previsão {mediana.previsao}")
        s = serie(56, lambda d: D("12") if d > REF - timedelta(days=7) else D("10"))
        soma, mediana = prever(s, REF, ALVO, metodo_tendencia="soma"), prever(s, REF, ALVO)
        registrar("C21 alta real de 20%: as duas captam", soma.tendencia == D("1.2") and mediana.tendencia == D("1.2"),
                  f"soma {soma.tendencia}, mediana {mediana.tendencia}")

    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")

    print("=== Resultado do teste do núcleo de cálculo da previsão ===")
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
