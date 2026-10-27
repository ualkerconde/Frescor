"""
Rateio da produção entre as lojas (Fase 5 / E3, doc §4.8; D70). Funções
puras: sem banco e sem relógio.

Para cada produto da ordem aprovada, quanto sugerir a cada loja no
romaneio, dado o disponível (produção real do produzido ou disponível do
distribuído, D69):

- disponível >= planejado (Σ das finais da ordem): cada loja recebe a sua
  final da ordem. O que passa do planejado fica na central, com o aviso
  "sobra" (não é rateado: D70).
- disponível < planejado (escassez): rateio proporcional à FINAL da ordem
  (a decisão do gestor, não a sugestão do sistema). Cada loja recebe a sua
  parte arredondada para baixo no passo da unidade (UN: 1; KG: 0,1 kg, como
  a D37), e os passos que sobram vão um a um para as lojas de maior resto;
  empate pelo código da loja (e pelo id, se o código faltar). Assim, Σ
  sugerida = disponível em UN, e em KG fica abaixo em menos de 0,1 kg.
  Nenhuma loja recebe mais do que a sua final: com final em KG de 3 casas
  (ex.: 10,55), o passo a mais que a passaria da final vai para a próxima
  da fila; se nenhuma puder levá-lo, ele fica na sobra.

A conta é feita em inteiros (milésimos), para o resto ser exato: com
decimais, dois restos iguais (1/3 e 1/3) poderiam sair diferentes na
última casa e o empate não cairia no código da loja.

É só sugestão: o gestor ajusta a final do romaneio (regra de ouro 4, D71).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.models.produto import UnidadeMedida

AVISO_ESCASSEZ = "escassez"  # disponível abaixo do planejado: houve rateio
AVISO_SEM_PRODUCAO = "sem_producao"  # disponível 0 com planejado > 0
AVISO_SOBRA = "sobra"  # disponível acima do planejado: o excedente fica na central

_MILESIMOS = 1000
# Passo do arredondamento, em milésimos (UN: 1 unidade; KG: 0,1 kg).
_PASSO = {UnidadeMedida.UN: 1000, UnidadeMedida.KG: 100}


@dataclass(frozen=True)
class LojaRateio:
    """Uma loja no rateio de um produto: a final da ordem é o peso dela."""

    loja_id: int
    codigo: str | None
    final_ordem: Decimal


@dataclass(frozen=True)
class ResultadoRateio:
    unidade: UnidadeMedida
    disponivel: Decimal
    planejado: Decimal
    escassez: bool
    sugeridas: dict[int, Decimal]  # loja_id -> quantidade sugerida
    sobra: Decimal  # disponível que não foi para nenhuma loja
    avisos: tuple[str, ...]


def lojas_para_rateio(linhas: Iterable) -> list[LojaRateio]:
    """Linhas da ordem aprovada -> entradas do rateio, pela FINAL (D70).

    Cada linha precisa de `loja_id`, `codigo_loja` e `quantidade_final`
    (a sugerida da ordem não entra: o peso é a decisão do gestor).
    """
    return [LojaRateio(l.loja_id, l.codigo_loja, Decimal(l.quantidade_final)) for l in linhas]


def _milesimos(valor: Decimal, nome: str) -> int:
    if valor < 0:
        raise ValueError(f"{nome} não pode ser negativo: {valor}")
    em_milesimos = valor * _MILESIMOS
    if em_milesimos != em_milesimos.to_integral_value():
        raise ValueError(f"{nome} com mais de 3 casas decimais: {valor}")
    return int(em_milesimos)


def _quantidade(milesimos: int) -> Decimal:
    return (Decimal(milesimos) / _MILESIMOS).quantize(Decimal("0.001"))


def ratear(disponivel: Decimal, unidade: UnidadeMedida, lojas: Sequence[LojaRateio]) -> ResultadoRateio:
    """Sugestão por loja de um produto (D70). Ver o docstring do módulo."""
    passo = _PASSO[unidade]
    d = _milesimos(Decimal(disponivel), "disponível")
    if unidade == UnidadeMedida.UN and d % passo:
        raise ValueError(f"disponível em UN precisa ser inteiro: {disponivel}")
    finais = {}
    for loja in lojas:
        if loja.loja_id in finais:
            raise ValueError(f"loja {loja.loja_id} repetida no rateio")
        finais[loja.loja_id] = _milesimos(Decimal(loja.final_ordem), "final da ordem")
    p = sum(finais.values())

    if d >= p:
        sugeridas = dict(finais)
        avisos = (AVISO_SOBRA,) if d > p else ()
        escassez = False
    else:
        # Parte de cada loja em passos: d * f / (p * passo), para baixo; o resto exato decide quem leva os
        # passos que sobram.
        divisor = p * passo
        base, resto = {}, {}
        for loja_id, f in finais.items():
            base[loja_id], resto[loja_id] = divmod(d * f, divisor)
        faltam = d // passo - sum(base.values())
        ordem = sorted(lojas, key=lambda l: (-resto[l.loja_id], l.codigo is None, l.codigo or "", l.loja_id))
        for loja in ordem:
            if faltam == 0 or resto[loja.loja_id] == 0:
                break
            # Final em KG com 3 casas (ex.: 10,55): o passo a mais não pode levar a loja acima da final;
            # ele passa para a próxima da fila.
            if (base[loja.loja_id] + 1) * passo <= finais[loja.loja_id]:
                base[loja.loja_id] += 1
                faltam -= 1
        sugeridas = {loja_id: n * passo for loja_id, n in base.items()}
        avisos = (AVISO_ESCASSEZ, AVISO_SEM_PRODUCAO) if d == 0 else (AVISO_ESCASSEZ,)
        escassez = True

    return ResultadoRateio(
        unidade=unidade,
        disponivel=_quantidade(d),
        planejado=_quantidade(p),
        escassez=escassez,
        sugeridas={loja_id: _quantidade(m) for loja_id, m in sugeridas.items()},
        sobra=_quantidade(d - sum(sugeridas.values())),
        avisos=avisos,
    )
