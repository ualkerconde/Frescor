"""
Testa o rateio da produção entre as lojas (Fase 5 / E3; D70), sem banco:
`app/services/distribuicao_calculo.py`.

Casos (conta à mão em cada número):
  R01 disponível = planejado -> cada loja recebe a final da ordem, sem aviso
  R02 disponível 15 > planejado 12 -> finais da ordem, sobra 3, aviso "sobra"
  R03 exemplo da D70: 10 un para finais 6/4/2 -> 5/3/2 (resto 1 para a 3ª loja)
  R04 KG em 0,1: 15,0 kg para 10,5/6,0/3,5 -> 7,9/4,5/2,6
  R05 KG com disponível fora do passo: 10,05 kg para 6/4 -> 6,0/4,0, sobra 0,05
  R06 empate de restos -> o passo vai para o MENOR código de loja, não para a
      primeira da lista (lojas entram fora de ordem)
  R07 disponível 0 -> todas 0, avisos "escassez" e "sem_producao"
  R08 loja com final 0 fica com 0 (5 un para 6/0/4 -> 3/0/2)
  R09 uma loja só, com escassez -> recebe todo o disponível
  R10 propriedades em 2.000 casos sorteados (semente fixa), UN e KG: múltiplos
      do passo; nenhuma loja acima da final; Σ ≤ disponível; com finais no
      passo, Σ = disponível arredondado para baixo no passo e cada loja a
      menos de um passo da parte exata
  R11 todas as finais 0 -> todas 0, o disponível inteiro é sobra
  R12 entradas inválidas -> ValueError (disponível negativo, final negativa,
      UN com fração, mais de 3 casas, loja repetida)
  R13 lojas_para_rateio usa a FINAL da ordem, não a sugerida
      (sugeridas 9/1, finais 6/4, 5 un -> 3/2; pela sugerida daria 5/0)
  R14 a ordem de entrada não muda o resultado
  R15 final em KG com 3 casas: o passo a mais não passa nenhuma loja da final
      (1,0 kg para 0,45/0,45/0,15 -> 0,4/0,4/0,1, sobra 0,1)

Saída ASCII ([OK]/[FALHA]), exit 1 se algo falhar.

Uso: python scripts/test_distribuicao_calculo.py
"""

import random
import sys
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.models.produto import UnidadeMedida  # noqa: E402
from app.services.distribuicao_calculo import (  # noqa: E402
    AVISO_ESCASSEZ,
    AVISO_SEM_PRODUCAO,
    AVISO_SOBRA,
    LojaRateio,
    lojas_para_rateio,
    ratear,
)

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 15
UN = UnidadeMedida.UN
KG = UnidadeMedida.KG
D = Decimal

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def lojas(*finais, codigos=None):
    codigos = codigos or [f"{i + 1:03d}" for i in range(len(finais))]
    return [LojaRateio(i + 1, c, D(str(f))) for i, (f, c) in enumerate(zip(finais, codigos))]


def por_codigo(resultado, entradas):
    return [str(resultado.sugeridas[l.loja_id]) for l in sorted(entradas, key=lambda l: l.codigo)]


def caso(nome, disponivel, unidade, entradas, esperado, sobra=None, avisos=None):
    try:
        r = ratear(D(str(disponivel)), unidade, entradas)
    except Exception as e:
        registrar(nome, False, f"erro inesperado -> {type(e).__name__}: {e}")
        return None
    obtido = por_codigo(r, entradas)
    ok = obtido == esperado
    detalhe = f"{obtido}"
    if sobra is not None:
        ok = ok and r.sobra == D(sobra)
        detalhe += f", sobra {r.sobra}"
    if avisos is not None:
        ok = ok and r.avisos == avisos
        detalhe += f", avisos {list(r.avisos)}"
    registrar(nome, ok, detalhe + ("" if ok else f" (esperado {esperado}, sobra {sobra}, avisos {avisos})"))
    return r


def propriedades():
    rng = random.Random("frescor-rateio-e3")
    problemas = []
    for n in range(2000):
        unidade = UN if n % 2 == 0 else KG
        passo = D(1) if unidade == UN else D("0.1")
        qtd_lojas = rng.randint(1, 6)
        if unidade == UN:
            finais = [D(rng.randint(0, 50)) for _ in range(qtd_lojas)]
        else:
            finais = [D(rng.randint(0, 300)) / 10 for _ in range(qtd_lojas)]
        planejado = sum(finais)
        if planejado == 0:
            continue
        if unidade == UN:
            disponivel = D(rng.randint(0, int(planejado) - 1)) if planejado > 1 else D(0)
        else:
            disponivel = (planejado * D(rng.random())).quantize(D("0.001"), rounding=ROUND_FLOOR)
        entradas = [LojaRateio(i + 1, f"{rng.randint(1, 999):03d}-{i}", f) for i, f in enumerate(finais)]
        r = ratear(disponivel, unidade, entradas)
        soma = sum(r.sugeridas.values())
        esperado_soma = (disponivel / passo).to_integral_value(rounding=ROUND_FLOOR) * passo
        for l in entradas:
            s = r.sugeridas[l.loja_id]
            exata = disponivel * l.final_ordem / planejado
            if s % passo or s > l.final_ordem or abs(s - exata) >= passo:
                problemas.append((n, unidade.value, str(disponivel), [str(f) for f in finais], l.loja_id, str(s)))
        if soma > disponivel or soma != esperado_soma or r.sobra != disponivel - soma or not r.escassez:
            problemas.append((n, unidade.value, str(disponivel), [str(f) for f in finais], "soma", str(soma)))
    return problemas


def main():
    # R01-R02: sem escassez.
    caso("R01 disponivel igual ao planejado", 12, UN, lojas(6, 4, 2), ["6.000", "4.000", "2.000"], "0.000", ())
    caso("R02 sobra fica na central", 15, UN, lojas(6, 4, 2), ["6.000", "4.000", "2.000"], "3.000",
         (AVISO_SOBRA,))
    # R03: 10 x 6/12 = 5; 10 x 4/12 = 3,33; 10 x 2/12 = 1,67 -> 5/3/1 e o passo que sobra vai para o maior resto (0,67).
    caso("R03 exemplo da D70 (10 un para 6/4/2)", 10, UN, lojas(6, 4, 2), ["5.000", "3.000", "2.000"], "0.000",
         (AVISO_ESCASSEZ,))
    # R04: 15 x 10,5/20 = 7,875 -> 7,8 (resto 0,075); 15 x 6/20 = 4,5 (resto 0); 15 x 3,5/20 = 2,625 -> 2,6 (resto 0,025).
    #      Soma 14,9; o 0,1 que falta vai para a 1ª loja -> 7,9 / 4,5 / 2,6 = 15,0.
    caso("R04 KG em 0,1 kg", "15.0", KG, lojas("10.5", "6.0", "3.5"), ["7.900", "4.500", "2.600"], "0.000")
    # R05: 10,05 x 6/10 = 6,03 -> 6,0; 10,05 x 4/10 = 4,02 -> 4,0; 100 passos de 0,1 cabem em 10,05 e já foram dados.
    caso("R05 KG fora do passo", "10.05", KG, lojas(6, 4), ["6.000", "4.000"], "0.050")
    # R06: 4 un para 2/2/2 -> 1,33 cada; 1/1/1 e um passo para o menor código ("001"), que entra por último.
    empate = lojas(2, 2, 2, codigos=["003", "002", "001"])
    caso("R06 empate vai para o menor codigo", 4, UN, empate, ["2.000", "1.000", "1.000"])
    caso("R07 disponivel zero", 0, UN, lojas(6, 4), ["0.000", "0.000"], "0.000",
         (AVISO_ESCASSEZ, AVISO_SEM_PRODUCAO))
    # R08: 5 x 6/10 = 3; 5 x 0 = 0; 5 x 4/10 = 2.
    caso("R08 loja com final zero", 5, UN, lojas(6, 0, 4), ["3.000", "0.000", "2.000"], "0.000")
    caso("R09 uma loja so", 7, UN, lojas(10), ["7.000"], "0.000", (AVISO_ESCASSEZ,))

    problemas = propriedades()
    registrar("R10 propriedades em 2000 casos sorteados", not problemas,
              "todas valem" if not problemas else f"{len(problemas)} problemas; primeiros: {problemas[:3]}")

    caso("R11 todas as finais zero", 5, UN, lojas(0, 0), ["0.000", "0.000"], "5.000", (AVISO_SOBRA,))

    invalidos = {
        "disponivel negativo": (D(-1), UN, lojas(1)),
        "final negativa": (D(1), UN, lojas(-1)),
        "UN com fracao": (D("1.5"), UN, lojas(2)),
        "mais de 3 casas": (D("1.0001"), KG, lojas(2)),
        "loja repetida": (D(1), UN, [LojaRateio(1, "001", D(1)), LojaRateio(1, "001", D(1))]),
    }
    aceitos = []
    for nome, args in invalidos.items():
        try:
            ratear(*args)
            aceitos.append(nome)
        except ValueError:
            pass
    registrar("R12 entradas invalidas recusadas", not aceitos,
              f"{len(invalidos)} recusadas" if not aceitos else f"aceitas: {aceitos}")

    @dataclass
    class Linha:  # o que o serviço (E4) vai ler da linha da ordem
        loja_id: int
        codigo_loja: str
        quantidade_sugerida: Decimal
        quantidade_final: Decimal

    # Sugeridas 9/1, finais 6/4 (o gestor ajustou). 5 un pela final: 3/2. Pela sugerida seria 4,5/0,5 -> 5/0.
    linhas = [Linha(1, "001", D(9), D(6)), Linha(2, "002", D(1), D(4))]
    entradas = lojas_para_rateio(linhas)
    caso("R13 rateio pela final da ordem", 5, UN, entradas, ["3.000", "2.000"])

    base = lojas(7, 5, 3, 3, 1, codigos=["005", "001", "004", "002", "003"])
    r1 = ratear(D(13), UN, base)
    embaralhadas = list(base)
    random.Random(7).shuffle(embaralhadas)
    r2 = ratear(D(13), UN, list(reversed(base)))
    r3 = ratear(D(13), UN, embaralhadas)
    registrar("R14 ordem de entrada nao muda o resultado", r1.sugeridas == r2.sugeridas == r3.sugeridas,
              f"{por_codigo(r1, base)}")

    # R15: 1,0 x 0,45/1,05 = 0,4286 -> 0,4 (resto 0,0286); igual na 2ª; 1,0 x 0,15/1,05 = 0,1429 -> 0,1 (resto 0,0429).
    #      Falta um passo; a 3ª (maior resto) iria a 0,2 > 0,15 e as outras a 0,5 > 0,45: ninguém leva, sobra 0,1.
    caso("R15 passo a mais nao passa da final", "1.0", KG, lojas("0.45", "0.45", "0.15"),
         ["0.400", "0.400", "0.100"], "0.100")

    print("\n=== Resultado do teste do rateio (E3, D70) ===")
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
