"""
Teste no passado do motor de previsão (Fase 3 / F6) e comparação das três
bases da D25 (média, mediana, média aparada).

Para cada dia dos últimos N dias com venda (padrão 28), prevê o dia usando
só o que se sabia até a véspera e compara com o real. Métricas
(app/services/previsao_metricas.py): WAPE, viés e a mesma conta para o
"ingênuo" (mesmo dia da semana passada). Todas as versões são medidas
sobre o MESMO conjunto de pares (loja, produto, dia), para a comparação ser
justa.

Parte A, motor completo (prever_central) nos dados gravados:
  - total, sem cold start (peso 1), por dia da semana e por produto;
  - padrão semanal reencontrado: perfil previsto por dia da semana contra
    o perfil real e contra os fatores do seed_vendas.
Parte B, robustez a valores extremos (o motivo da D25): copia as séries
  em memória, multiplica alguns dias por um fator (picos determinísticos:
  promoção não cadastrada, erro de digitação) e mede só nos dias normais.
  Usa o núcleo puro (prever), sem cold start e sem gravar nada.

Critérios (saída 1 se falhar): a base padrão (mediana, D25) vence o
ingênuo no WAPE da parte A,
e o perfil semanal previsto fica a menos de 5 pontos percentuais do real
em todos os dias da semana.

Limitações: os dados do seed são sintéticos, estacionários e sem picos;
servem para provar que o código funciona, não para medir a precisão real
(isso só com dado real, D3).

Uso (na pasta backend/, com o venv ativo):
    python scripts/backtest_previsao.py [--dias 28] [--fim AAAA-MM-DD]
        [--email gestor@teste.com] [--pico-taxa 0.03] [--pico-fator 4]
"""

import argparse
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.produto import Produto  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402
from app.models.venda_diaria import VendaDiaria  # noqa: E402
from app.services.previsao_calculo import ESTATISTICA_PADRAO, ESTATISTICAS, prever  # noqa: E402
from app.services.previsao_metricas import medir, previsao_ingenua  # noqa: E402
from app.services.previsao_service import lojas_ativas_da_central, prever_central  # noqa: E402
from app.services.serie_vendas_service import series_da_loja  # noqa: E402

DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
PADRAO = ESTATISTICA_PADRAO
TOLERANCIA_PERFIL = Decimal("0.05")
UM_DIA = timedelta(days=1)


def pct(x):
    return "   —   " if x is None else f"{x * 100:6.1f}%"


def sinal(x):
    return "   —   " if x is None else f"{x * 100:+6.1f}%"


def tabela_metricas(titulo, linhas):
    """linhas: (rótulo, métricas do motor, métricas do ingênuo)."""
    print(f"\n{titulo}")
    print(f"  {'versão':<16} {'pares':>6}  {'WAPE':>7} {'viés':>7}   {'ingênuo WAPE':>12} {'viés':>7}   vence?")
    for rotulo, m, ing in linhas:
        vence = "sim" if m.wape is not None and ing.wape is not None and m.wape < ing.wape else "NÃO"
        print(f"  {rotulo:<16} {m.n:>6}  {pct(m.wape)} {sinal(m.vies)}   {pct(ing.wape):>12} {sinal(ing.vies)}   {vence}")


def main():
    args = argparse.ArgumentParser(description="Teste no passado do motor de previsão (F6).")
    args.add_argument("--dias", type=int, default=28)
    args.add_argument("--fim", type=date.fromisoformat, default=None)
    args.add_argument("--email", default="gestor@teste.com")
    args.add_argument("--pico-taxa", type=float, default=0.03)
    args.add_argument("--pico-fator", type=Decimal, default=Decimal("4"))
    a = args.parse_args()

    db = SessionLocal()
    try:
        gestor = db.query(Usuario).filter(Usuario.email == a.email).first()
        if gestor is None or gestor.central_producao_id is None:
            print(f"Gestor {a.email} não encontrado -> rode scripts/seed_dev.py e seed_vendas.py")
            sys.exit(1)
        negocio_id, central_id = gestor.negocio_id, gestor.central_producao_id
        loja_ids = lojas_ativas_da_central(db, negocio_id, central_id)
        fim = a.fim or db.query(func.max(VendaDiaria.data)).filter(
            VendaDiaria.negocio_id == negocio_id, VendaDiaria.loja_id.in_(loja_ids)).scalar()
        inicio_hist = db.query(func.min(VendaDiaria.data)).filter(
            VendaDiaria.negocio_id == negocio_id, VendaDiaria.loja_id.in_(loja_ids)).scalar()
        alvos = [fim - timedelta(days=k) for k in range(a.dias - 1, -1, -1)]
        codigo_loja = dict(db.query(Loja.id, Loja.codigo).filter(Loja.id.in_(loja_ids)))
        codigo_produto = dict(db.query(Produto.id, Produto.codigo).filter(Produto.negocio_id == negocio_id))
        reais = {
            (loja_id, pid): serie
            for loja_id in loja_ids
            for pid, serie in series_da_loja(db, negocio_id, loja_id, inicio_hist, fim).items()
        }
        print(f"Central {central_id} · lojas {sorted(codigo_loja.values())} · {len(reais)} séries loja+produto")
        print(f"Histórico desde {inicio_hist:%d/%m/%Y}; dias previstos: {alvos[0]:%d/%m/%Y} a {alvos[-1]:%d/%m/%Y} "
              f"({len(alvos)} dias), cada um com o que se sabia até a véspera.")

        # ------------------------------------------------ parte A
        previstos: dict[str, dict] = {e: {} for e in ESTATISTICAS}
        peso: dict = {}
        for est in ESTATISTICAS:
            for alvo in alvos:
                for x in prever_central(db, negocio_id, central_id, alvo - UM_DIA, alvo, est):
                    previstos[est][(x.loja_id, x.produto_id, alvo)] = x.previsao
                    peso[(x.loja_id, x.produto_id, alvo)] = x.peso_historico
        chaves = []
        for (loja_id, pid), serie in reais.items():
            for alvo in alvos:
                k = (loja_id, pid, alvo)
                if serie.get(alvo) is None or previsao_ingenua(serie, alvo) is None:
                    continue
                if all(previstos[e].get(k) is not None for e in ESTATISTICAS):
                    chaves.append(k)

        def real(k):
            return reais[(k[0], k[1])][k[2]]

        def ingenuo(k):
            return previsao_ingenua(reais[(k[0], k[1])], k[2])

        def comparar(titulo, ks):
            ing = medir((real(k), ingenuo(k)) for k in ks)
            tabela_metricas(titulo, [(e, medir((real(k), previstos[e][k]) for k in ks), ing) for e in ESTATISTICAS])
            return ing

        print("\n=============== PARTE A · motor completo nos dados gravados ===============")
        ing_total = comparar(f"Todos os dias ({len(chaves)} pares loja+produto+dia)", chaves)
        sem_cold = [k for k in chaves if peso[k] >= 1]
        comparar(f"Só sem cold start, peso 1 ({len(sem_cold)} pares; o seed começa em {inicio_hist:%d/%m})", sem_cold)

        print(f"\nPor dia da semana (base: {PADRAO}, padrão)")
        print(f"  {'dia':<4} {'pares':>5}  {'motor WAPE':>10} {'viés':>7}   {'ingênuo WAPE':>12}")
        for wd in range(7):
            ks = [k for k in chaves if k[2].weekday() == wd]
            m, ing = medir((real(k), previstos[PADRAO][k]) for k in ks), medir((real(k), ingenuo(k)) for k in ks)
            print(f"  {DIAS_SEMANA[wd]:<4} {m.n:>5}  {pct(m.wape):>10} {sinal(m.vies)}   {pct(ing.wape):>12}")

        print(f"\nPor produto (base: {PADRAO}, padrão; as duas lojas juntas)")
        print(f"  {'produto':<8} {'pares':>5}  {'motor WAPE':>10} {'viés':>7}   {'ingênuo WAPE':>12}   vence?")
        por_produto = defaultdict(list)
        for k in chaves:
            por_produto[k[1]].append(k)
        perdeu = []
        for pid in sorted(por_produto, key=lambda p: codigo_produto[p]):
            ks = por_produto[pid]
            m, ing = medir((real(k), previstos[PADRAO][k]) for k in ks), medir((real(k), ingenuo(k)) for k in ks)
            vence =m.wape < ing.wape
            if not vence:
                perdeu.append(codigo_produto[pid])
            print(f"  {codigo_produto[pid]:<8} {m.n:>5}  {pct(m.wape):>10} {sinal(m.vies)}   {pct(ing.wape):>12}   "
                  f"{'sim' if vence else 'NÃO'}")

        # Perfil semanal: participação de cada dia da semana no total da semana.
        from scripts.seed_vendas import FATOR_DIA_SEMANA  # noqa: E402

        soma_fator = sum(Decimal(str(f)) for f in FATOR_DIA_SEMANA.values())
        tot_real = defaultdict(Decimal)
        tot_prev = defaultdict(Decimal)
        for k in chaves:
            tot_real[k[2].weekday()] += real(k)
            tot_prev[k[2].weekday()] += previstos[PADRAO][k]
        print("\nPadrão semanal reencontrado (participação do dia na semana; seed = fatores do seed_vendas)")
        print(f"  {'dia':<4} {'seed':>7} {'real':>7} {'previsto':>9}")
        maior_desvio = Decimal("0")
        for wd in range(7):
            p_seed = Decimal(str(FATOR_DIA_SEMANA[wd])) / soma_fator
            p_real = tot_real[wd] / sum(tot_real.values())
            p_prev = tot_prev[wd] / sum(tot_prev.values())
            maior_desvio = max(maior_desvio, abs(p_prev - p_real))
            print(f"  {DIAS_SEMANA[wd]:<4} {pct(p_seed)} {pct(p_real)} {pct(p_prev):>9}")

        # ------------------------------------------------ parte B
        print("\n=============== PARTE B · robustez a valores extremos (em memória) ===============")
        rnd = random.Random(2026)
        contaminadas, picos = {}, set()
        for chave, serie in sorted(reais.items()):
            nova = {}
            for d, v in sorted(serie.items()):
                if v is not None and rnd.random() < a.pico_taxa:
                    nova[d] = v * a.pico_fator
                    picos.add((chave, d))
                else:
                    nova[d] = v
            contaminadas[chave] = nova
        print(f"{len(picos)} dias com pico (×{a.pico_fator}, {a.pico_taxa:.0%} dos dias) em {len(reais)} séries; "
              "métricas só nos dias sem pico, contra o real limpo.")
        linhas = []
        pares_b: dict = {e: {} for e in ESTATISTICAS}
        limpos: dict = {e: {} for e in ESTATISTICAS}
        for chave in reais:
            for alvo in alvos:
                if (chave, alvo) in picos or reais[chave].get(alvo) is None:
                    continue
                for e in ESTATISTICAS:
                    pares_b[e][(chave, alvo)] = prever(contaminadas[chave], alvo - UM_DIA, alvo, estatistica=e).previsao
                    limpos[e][(chave, alvo)] = prever(reais[chave], alvo - UM_DIA, alvo, estatistica=e).previsao
        ks_b = [k for k in pares_b["media"]
                if previsao_ingenua(contaminadas[k[0]], k[1]) is not None
                and all(pares_b[e][k] is not None and limpos[e][k] is not None for e in ESTATISTICAS)]
        ing_b = medir((reais[k[0]][k[1]], previsao_ingenua(contaminadas[k[0]], k[1])) for k in ks_b)
        print(f"\n  {'versão':<16} {'pares':>6}  {'WAPE limpo':>10}  {'WAPE c/ picos':>13} {'viés c/ picos':>13}"
              f"   {'ingênuo c/ picos':>16}")
        for e in ESTATISTICAS:
            m_limpo = medir((reais[k[0]][k[1]], limpos[e][k]) for k in ks_b)
            m_picos = medir((reais[k[0]][k[1]], pares_b[e][k]) for k in ks_b)
            linhas.append((e, m_limpo, m_picos))
            print(f"  {e:<16} {m_picos.n:>6}  {pct(m_limpo.wape):>10}  {pct(m_picos.wape):>13} {sinal(m_picos.vies):>13}"
                  f"   {pct(ing_b.wape):>16}")

        # ------------------------------------------------ critérios
        m_padrao = medir((real(k), previstos[PADRAO][k]) for k in chaves)
        criterios = [
            (f"motor ({PADRAO}, padrão) vence o ingênuo no WAPE", m_padrao.wape < ing_total.wape,
             f"{pct(m_padrao.wape).strip()} contra {pct(ing_total.wape).strip()}"),
            ("perfil semanal previsto a menos de 5 p.p. do real", maior_desvio < TOLERANCIA_PERFIL,
             f"maior desvio {maior_desvio * 100:.2f} p.p."),
        ]
        print("\n=============== Critérios ===============")
        for nome, ok, detalhe in criterios:
            print(f"{'[OK]' if ok else '[FALHA]'} {nome}: {detalhe}")
        if perdeu:
            print(f"[aviso] produtos em que o motor ({PADRAO}) não vence o ingênuo: {', '.join(perdeu)}")
        _ = codigo_loja
        if not all(ok for _, ok, _ in criterios):
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
