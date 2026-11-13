"""
Testa os fatores de calendário da previsão (D112–D114), só funções puras
(app/services/previsao_fatores.py e o uso em previsao_calculo.prever).

Séries sintéticas de ~420 dias até a referência, com padrão semanal fixo
(nenhum ruído, para cada caso isolar um efeito).

Casos:
  F1 Páscoa: 2025 = 20/04, 2026 = 05/04, 2027 = 28/03
  F2 feriados de 2026: Carnaval 16 e 17/02, Sexta-feira Santa 03/04,
     Corpus Christi 04/06, Consciência Negra 20/11 (e não em 2023)
  F3 série sem padrão de calendário: todos os fatores = 1 e a previsão
     igual à de antes (sem fatores)
  F4 semana do pagamento (1ª semana do mês ×1,3), referência na 3ª semana:
     alvo na 1ª semana sobe (> 1,1); alvo na 3ª semana fica ~1
  F5 desconto da tendência: referência no fim da 1ª semana (a tendência já
     viu a semana forte): alvo ainda na 1ª semana não sobe de novo (< 1,05)
  F6 ano anterior: a semana do alvo, um ano antes, vendeu ×1,5 -> fator
     do ano > 1,2 e ≤ 1,3 (limite)
  F7 feriado: feriados passados venderam ×0,5 -> alvo feriado com fator
     < 0,75; com evento cadastrado no alvo, o fator fica 1
  F8 feriado com venda zero nas últimas 6 semanas não derruba a base
  F9 pouco histórico (8 semanas): semana e dia do mês ficam 1
  F10 limite: 1ª semana ×3 -> fator da semana ≤ 1,15

Uso: python scripts/test_previsao_fatores.py
"""

import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.models.evento import TipoAjuste  # noqa: E402
from app.services.previsao_calculo import EventoAplicavel, prever  # noqa: E402
from app.services.previsao_fatores import feriado, feriados_nacionais, pascoa  # noqa: E402

D = Decimal
SEMANA = [D("1.0"), D("0.9"), D("0.9"), D("1.0"), D("1.2"), D("1.5"), D("1.3")]
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{'[OK]' if ok else '[FALHA]'} {nome}: {detalhe}")


def serie(ref: date, dias: int, f=lambda d: D(1)):
    return {ref - timedelta(days=k): D(100) * SEMANA[(ref - timedelta(days=k)).weekday()] * f(ref - timedelta(days=k))
            for k in range(dias)}


def main():
    registrar("F1 Pascoa", [pascoa(a) for a in (2025, 2026, 2027)]
              == [date(2025, 4, 20), date(2026, 4, 5), date(2027, 3, 28)], f"{[str(pascoa(a)) for a in (2025, 2026, 2027)]}")
    f26 = feriados_nacionais(2026)
    esperados = [date(2026, 2, 16), date(2026, 2, 17), date(2026, 4, 3), date(2026, 6, 4), date(2026, 11, 20)]
    registrar("F2 feriados 2026", all(d in f26 for d in esperados) and date(2023, 11, 20) not in feriados_nacionais(2023),
              f"{[f26.get(d) for d in esperados]}")

    # Referência numa quarta da 3ª semana, fora de feriado; alvo no dia seguinte.
    ref = date(2026, 9, 16)
    alvo = ref + timedelta(days=1)
    s = serie(ref, 420)
    com, sem = prever(s, ref, alvo), prever(s, ref, alvo, fatores=frozenset())
    f = com.fatores
    registrar("F3 sem padrao: fatores 1", (f.ano, f.semana_mes, f.dia_mes, f.feriado) == (1, 1, 1, 1)
              and com.previsao == sem.previsao, f"{f} {com.previsao} {sem.previsao}")

    pagamento = lambda d: D("1.3") if d.day <= 7 else D(1)  # noqa: E731
    s = serie(ref, 420, pagamento)
    semana1 = prever(s, ref, date(2026, 10, 1)).fatores.semana_mes  # quinta, 1ª semana (alvo a 15 dias)
    semana3 = prever(s, ref, alvo).fatores.semana_mes
    registrar("F4 semana do pagamento", semana1 > D("1.1") and abs(semana3 - 1) < D("0.05"),
              f"1a semana {semana1}, 3a semana {semana3}")

    ref5 = date(2026, 10, 6)  # terça da 1ª semana: a tendência já viu os dias fortes
    s5 = serie(ref5, 420, pagamento)
    f5 = prever(s5, ref5, ref5 + timedelta(days=1)).fatores.semana_mes
    registrar("F5 tendencia ja contem a semana", f5 < D("1.05"), f"{f5}")

    ancora = alvo - timedelta(days=364)
    anual = lambda d: D("1.5") if abs((d - ancora).days) <= 3 else D(1)  # noqa: E731
    fa = prever(serie(ref, 420, anual), ref, alvo).fatores.ano
    registrar("F6 ano anterior", D("1.2") < fa <= D("1.3"), f"{fa}")

    ref7 = date(2026, 11, 14)  # sábado; alvo 15/11 (domingo, Proclamação da República)
    s7 = serie(ref7, 420, lambda d: D("0.5") if feriado(d) else D(1))
    ff = prever(s7, ref7, ref7 + timedelta(days=1)).fatores
    ev = EventoAplicavel(1, "Feira", ref7 + timedelta(days=1), ref7 + timedelta(days=1), TipoAjuste.MULTIPLICADOR,
                         D("1.2"), None)
    ff_ev = prever(s7, ref7, ref7 + timedelta(days=1), eventos=[ev]).fatores
    registrar("F7 feriado (e evento manda)", ff.feriado < D("0.75") and ff.nome_feriado and ff_ev.feriado == 1,
              f"{ff.nome_feriado} {ff.feriado}; com evento {ff_ev.feriado}")

    ref8 = date(2026, 10, 19)  # segunda depois do feriado de 12/10 (segunda)
    s8 = serie(ref8, 420, lambda d: D(0) if feriado(d) else D(1))
    b8 = prever(s8, ref8, ref8 + timedelta(days=7)).base  # outra segunda
    registrar("F8 feriado fora da base", b8 == D(100), f"base {b8}")

    f9 = prever(serie(ref, 56, pagamento), ref, date(2026, 10, 1)).fatores
    registrar("F9 pouco historico: sem fator de mes", (f9.semana_mes, f9.dia_mes) == (1, 1), f"{f9}")

    f10 = prever(serie(ref, 420, lambda d: D(3) if d.day <= 7 else D(1)), ref, date(2026, 10, 1)).fatores.semana_mes
    registrar("F10 limite da semana", f10 <= D("1.15") * D("1.0001"), f"{f10}")

    print()
    for r in resultados:
        print(r)
    falhas = [r for r in resultados if r.startswith("[FALHA]")]
    print()
    print(f"{len(falhas)} CASO(S) FALHARAM" if falhas else "TODOS OS CASOS PASSARAM")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
