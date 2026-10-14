"""
Testa as métricas de qualidade da previsão (Fase 3 / F6), sem banco.

Casos:
  M01 previsão perfeita -> WAPE 0 e viés 0
  M02 conta conhecida: real 10 e 20, previsto 12 e 15 -> WAPE 7/30, viés -3/30
  M03 WAPE pondera pelo volume (não é média de erros percentuais):
      real 1 e 100, previsto 2 e 100 -> 1/101 (a média de % daria 50%)
  M04 sobra -> viés positivo; falta -> viés negativo
  M05 sem pares ou com real somando zero -> WAPE e viés None
  M06 ingênuo = mesmo dia da semana anterior (7 dias antes); faltante -> None

Uso: python scripts/test_previsao_metricas.py
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.previsao_metricas import medir, previsao_ingenua  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 6
D = Decimal

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def main():
    try:
        m = medir([(D(10), D(10)), (D(20), D(20))])
        registrar("M01 perfeita", m.wape == 0 and m.vies == 0 and m.n == 2, f"WAPE {m.wape}, viés {m.vies}")
        m = medir([(D(10), D(12)), (D(20), D(15))])
        registrar("M02 conta conhecida", m.wape == D(7) / 30 and m.vies == D(-3) / 30,
                  f"WAPE {m.wape:.4f} (7/30), viés {m.vies:.4f} (-3/30)")
        m = medir([(D(1), D(2)), (D(100), D(100))])
        registrar("M03 pondera pelo volume", m.wape == D(1) / 101, f"WAPE {m.wape:.4%} (média de % daria 50%)")
        sobra, falta = medir([(D(10), D(13))]), medir([(D(10), D(7))])
        registrar("M04 sinal do vies", sobra.vies == D("0.3") and falta.vies == D("-0.3"),
                  f"sobra {sobra.vies}, falta {falta.vies}")
        vazio, zero = medir([]), medir([(D(0), D(5))])
        registrar("M05 sem volume -> None", vazio.wape is None and vazio.vies is None and zero.wape is None,
                  f"vazio {vazio.wape}/{vazio.vies}, real zero {zero.wape}")
        s = {date(2026, 10, 5): D(40), date(2026, 10, 11): D(99), date(2026, 10, 6): None}
        ok = (previsao_ingenua(s, date(2026, 10, 12)) == D(40) and previsao_ingenua(s, date(2026, 10, 13)) is None
              and previsao_ingenua(s, date(2026, 10, 20)) is None)
        registrar("M06 ingenuo = 7 dias antes", ok,
                  f"12/10 -> {previsao_ingenua(s, date(2026, 10, 12))} (não o 99 de ontem); faltante -> None")
    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    print("=== Resultado do teste das métricas de previsão ===")
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
