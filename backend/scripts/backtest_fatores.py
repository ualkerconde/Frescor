"""
Teste no passado dos fatores de calendário (D114): cada fator só fica
ligado se melhora a previsão. Sem dado real de cliente ainda (Fase 7),
o teste usa séries SINTÉTICAS com ruído, de dois tipos:

- com o padrão que o fator procura (semana do pagamento, feriado que vende
  menos, estação do ano): o fator tem de reduzir o erro;
- sem padrão nenhum (só dia da semana + ruído): o fator NÃO pode piorar o
  erro de forma relevante (é o risco de "aprender ruído").

Erro = WAPE (soma |previsto − real| ÷ soma real) nos alvos de D+1 a D+7,
com uma referência por semana durante ~6 meses. Mesma semente de ruído
para todos, para comparar só o efeito do fator.

Isto NÃO substitui o teste com dado real da Fase 7: lá os ganhos podem ser
menores (ou o padrão não existir) e a decisão de ligar cada fator deve ser
refeita com a venda do piloto.

Uso: python scripts/backtest_fatores.py
"""

import math
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.previsao_calculo import prever  # noqa: E402
from app.services.previsao_fatores import (  # noqa: E402
    FATOR_ANO,
    FATOR_DIA_MES,
    FATOR_FERIADO,
    FATOR_SEMANA_MES,
    TODOS_OS_FATORES,
    feriado,
)

SEMANA = [1.0, 0.9, 0.9, 1.0, 1.2, 1.5, 1.3]
INICIO, FIM = date(2024, 6, 1), date(2026, 10, 31)
REFS = [date(2026, 4, 1) + timedelta(days=7 * k + d) for k in range(26) for d in (0, 3)]


def gerar(semente: int, pagamento=1.0, dia_5_20=1.0, fator_feriado=1.0, estacao=0.0, pico_junho=1.0, ruido=0.12):
    rnd = random.Random(semente)
    serie = {}
    d = INICIO
    while d <= FIM:
        v = 100 * SEMANA[d.weekday()]
        if d.day <= 7:
            v *= pagamento
        if d.day in (5, 20):
            v *= dia_5_20
        if d.month == 6 and 15 <= d.day <= 24:  # um período fixo do ano (ex.: festa junina)
            v *= pico_junho
        if feriado(d):
            v *= fator_feriado
        v *= 1 + estacao * math.sin(2 * math.pi * d.timetuple().tm_yday / 365.25)
        v *= max(0.0, rnd.gauss(1, ruido))
        serie[d] = Decimal(str(round(v)))
        d += timedelta(days=1)
    return serie


def wape(serie, fatores):
    erro = real = 0.0
    for ref in REFS:
        conhecida = {d: v for d, v in serie.items() if d <= ref}
        for h in range(1, 8):
            alvo = ref + timedelta(days=h)
            p = prever(conhecida, ref, alvo, fatores=fatores).previsao
            if p is None:
                continue
            erro += abs(float(p) - float(serie[alvo]))
            real += float(serie[alvo])
    return erro / real


CENARIOS = [
    ("sem padrao (so ruido)", {}),
    ("semana do pagamento x1,25", {"pagamento": 1.25}),
    ("dias 5 e 20 x1,4", {"dia_5_20": 1.4}),
    ("feriado vende x0,6", {"fator_feriado": 0.6}),
    ("estacao do ano +-25%", {"estacao": 0.25}),
    ("15 a 24/06 x1,5 todo ano", {"pico_junho": 1.5}),
    ("tudo junto", {"pagamento": 1.25, "dia_5_20": 1.4, "fator_feriado": 0.6, "estacao": 0.25,
                    "pico_junho": 1.5}),
]
CONFIGS = [
    ("nenhum", frozenset()),
    ("so semana_mes", frozenset({FATOR_SEMANA_MES})),
    ("so dia_mes", frozenset({FATOR_DIA_MES})),
    ("so ano", frozenset({FATOR_ANO})),
    ("so feriado", frozenset({FATOR_FERIADO})),
    ("todos", TODOS_OS_FATORES),
    ("todos menos ano", TODOS_OS_FATORES - {FATOR_ANO}),
]


def main():
    sementes = (1, 2, 3)
    print(f"WAPE medio em {len(sementes)} series por cenario; {len(REFS)} referencias x 7 dias\n")
    print(f"{'cenario':30}" + "".join(f"{nome:>17}" for nome, _ in CONFIGS))
    for nome, params in CENARIOS:
        series = [gerar(s, **params) for s in sementes]
        linha = [sum(wape(s, cfg) for s in series) / len(series) for _, cfg in CONFIGS]
        print(f"{nome:30}" + "".join(f"{100 * w:16.2f}%" for w in linha))


if __name__ == "__main__":
    main()
