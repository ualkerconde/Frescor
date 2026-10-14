"""
Testa o ramo sazonal do motor de previsão (Fase 3 / F5, versão mínima,
doc §4.1), a vigência (D30, proposta) e as estatísticas da base (D25).

Parte 1, funções puras:
  Z01 vigente(): período fixo, sem datas, recorrente no mesmo ano e
      recorrente virando o ano
  Z02 prever_sazonal sem ano anterior -> None (1ª temporada)
  Z03 prever_sazonal com ano anterior: base 80, real 20% acima -> 96
  Z04 dia de evento no ano anterior fica fora da base
  Z05 tendência com menos de 5 dias comparáveis -> fator 1
  Z06 resumir(): média, mediana (ímpar e par), média aparada (com 4+ e
      com menos de 4) e estatística desconhecida

Parte 2, serviço com banco (uma loja que vende todo dia desde 01/10/2025):
  PA  semanal, categoria Pães, 50/dia
  PZ  sazonal recorrente 01/11 a 31/12, categoria Panetones:
      2025: novembro 30/dia, dezembro 80/dia; 2026: novembro 36, dezembro 96
  PY  sazonal recorrente 01/11 a 31/12, categoria Pães, 1ª temporada
      (vende 40/dia só desde 01/11/2026)
  PT  semanal com vigência fixa até 01/12/2026, categoria Outros, 20/dia
  Z07 PZ em 22/12/2026: método sazonal, base 80 (dezembro de 2025),
      tendência 1,2 -> 96 (a base semanal misturaria novembro e dezembro)
  Z08 PZ em 03/11/2026 (início da temporada): base 30 com 3 semanas; os
      zeros de outubro de 2025 (fora da vigência) não entram
  Z09 PY em 10/11/2026: 1ª temporada -> método semanal com cold start
      (peso 1/6, proxy da categoria Pães = PA 50)
  Z10 PT em 10/11/2026 (vigente) recebe previsão
  Z11 em 22/12/2026, PT (vigência acabou em 01/12) não recebe previsão
  Z12 em 05/01/2027, PZ e PY (fora da temporada) não recebem previsão; PA sim
  Z13 em 20/10/2026, PZ (antes da temporada) não recebe previsão
  Z14 D30 vale para qualquer produto: PL (semanal, lançamento em
      01/12/2026, nunca vendeu) não recebe previsão em 10/11; em 22/12
      recebe, com o histórico começando no lançamento (não na habilitação,
      que é anterior): peso 0,5 e proxy da categoria

Uso: python scripts/test_previsao_sazonal.py
"""

import sys
import uuid
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.evento import TipoAjuste  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.nivel_classificacao import NivelClassificacao  # noqa: E402
from app.models.produto import CicloPrevisao, Produto, UnidadeMedida  # noqa: E402
from app.models.produto_classificacao import ProdutoClassificacao  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402
from app.services.previsao_calculo import EventoAplicavel, prever_sazonal, resumir, vigente  # noqa: E402
from app.services.previsao_service import prever_central  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 14
PREFIXO_NEGOCIO_TESTE = "_Teste Sazonal"
D = Decimal
UM_DIA = timedelta(days=1)
TOL = D("0.000000001")

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def perto(a, b):
    return a is not None and b is not None and abs(a - b) <= TOL


def fmt(x):
    return "None" if x is None else f"{x:.4f}"


def dias(inicio, fim):
    return [inicio + timedelta(days=k) for k in range((fim - inicio).days + 1)]


def parte_pura():
    casos = [
        (date(2026, 6, 1), date(2026, 1, 1), date(2026, 12, 1), False, True),
        (date(2026, 12, 2), date(2026, 1, 1), date(2026, 12, 1), False, False),
        (date(2025, 12, 31), date(2026, 1, 1), None, False, False),
        (date(2030, 1, 1), None, None, False, True),
        (date(2027, 11, 15), date(2026, 11, 1), date(2026, 12, 31), True, True),
        (date(2027, 10, 31), date(2026, 11, 1), date(2026, 12, 31), True, False),
        (date(2027, 1, 3), date(2026, 12, 1), date(2027, 1, 6), True, True),
        (date(2026, 12, 31), date(2026, 12, 1), date(2027, 1, 6), True, True),
        (date(2027, 2, 1), date(2026, 12, 1), date(2027, 1, 6), True, False),
    ]
    erros = [f"{dia} em {ini}..{fim} rec={rec}: {vigente(dia, ini, fim, rec)}"
             for dia, ini, fim, rec, esp in casos if vigente(dia, ini, fim, rec) != esp]
    registrar("Z01 vigente()", not erros, "; ".join(erros) or f"{len(casos)} casos conferidos")

    ref, alvo = date(2026, 12, 21), date(2026, 12, 22)
    so_este_ano = {d: D("96") for d in dias(date(2026, 11, 1), ref)}
    registrar("Z02 sem ano anterior -> None", prever_sazonal(so_este_ano, ref, alvo) is None, "1ª temporada")

    ano_passado = {d: D("80") for d in dias(date(2025, 12, 1), date(2025, 12, 31))}
    serie = ano_passado | {d: D("96") for d in dias(date(2026, 12, 1), ref)}
    c = prever_sazonal(serie, ref, alvo)
    registrar("Z03 base do ano anterior x tendencia",
              c is not None and c.base == D("80") and c.tendencia == D("1.2") and c.previsao == D("96")
              and c.metodo == "sazonal" and c.semanas_na_base == 4,  # +2 semanas = 06/01/2026, sem dado
              f"base {fmt(c.base)} ({c.semanas_na_base} sem), tendência {fmt(c.tendencia)}, previsão {fmt(c.previsao)}")

    dia_ev = alvo - timedelta(days=364)
    com_pico = serie | {dia_ev: D("400")}
    ev = EventoAplicavel(1, "ev", dia_ev, dia_ev, TipoAjuste.MULTIPLICADOR, D("1"), None)
    # Média de propósito: com a mediana (padrão), o pico isolado não moveria a base.
    sem_ev = prever_sazonal(com_pico, ref, alvo, estatistica="media")
    com_ev = prever_sazonal(com_pico, ref, alvo, [ev], estatistica="media")
    registrar("Z04 evento do ano anterior fora da base",
              com_ev.base == D("80") and com_ev.semanas_na_base == 3 and sem_ev.base == D("160"),
              f"com evento {fmt(com_ev.base)} ({com_ev.semanas_na_base} sem); sem o evento {fmt(sem_ev.base)}")

    poucos = ano_passado | {d: D("120") for d in dias(ref - timedelta(days=3), ref)}
    c = prever_sazonal(poucos, ref, alvo)
    registrar("Z05 menos de 5 dias na tendencia -> 1", c.tendencia == D("1") and c.dias_na_tendencia == 4,
              f"tendência {fmt(c.tendencia)} ({c.dias_na_tendencia} dias)")

    v = [D(x) for x in ("10", "10", "10", "10", "10", "100")]
    obtidos = (resumir(v, "media"), resumir(v), resumir(v, "media_aparada"),
               resumir([D(1), D(2), D(3), D(4)], "mediana"), resumir([D(1), D(2), D(9)], "mediana"),
               resumir([D(1), D(2), D(9)], "media_aparada"))
    try:
        resumir(v, "moda")
        recusou = False
    except ValueError:
        recusou = True
    registrar("Z06 resumir: media, mediana, media aparada",
              obtidos == (D(25), D(10), D(10), D("2.5"), D(2), D(4)) and recusou,
              f"[10×5, 100]: média {obtidos[0]}, mediana (padrão) {obtidos[1]}, aparada {obtidos[2]}; "
              f"mediana [1..4] {obtidos[3]}; [1,2,9]: mediana {obtidos[4]}, aparada {obtidos[5]}; 'moda' recusada: {recusou}")


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
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
        neg = Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run_id}", ativo=True)
        db.add(neg)
        db.flush()
        negocio_ids = [neg.id]
        central = CentralProducao(negocio_id=neg.id, nome="_Central", ativa=True)
        db.add(central)
        db.flush()
        nivel = NivelClassificacao(negocio_id=neg.id, ordem=1, nome="Categoria")
        lj = Loja(negocio_id=neg.id, central_producao_id=central.id, nome="_Loja", codigo="L1",
                  horario_zeragem=time(6, 0), ativo=True)
        db.add_all([nivel, lj])
        db.flush()

        def produto(codigo, categoria, sazonal=False, inicio=None, fim=None, recorrente=False):
            p = Produto(negocio_id=neg.id, nome=f"_{codigo}", codigo=codigo, unidade_medida=UnidadeMedida.UN,
                        ativo=True, ciclo_previsao=CicloPrevisao.SAZONAL if sazonal else CicloPrevisao.SEMANAL,
                        data_inicio_vigencia=inicio, data_fim_vigencia=fim, vigencia_recorrente=recorrente)
            db.add(p)
            db.flush()
            db.add(ProdutoClassificacao(produto_id=p.id, nivel_id=nivel.id, valor=categoria))
            db.add(ProdutoLoja(produto_id=p.id, loja_id=lj.id))
            return p

        temporada = dict(sazonal=True, inicio=date(2025, 11, 1), fim=date(2025, 12, 31), recorrente=True)
        pa = produto("PA", "Pães")
        pz = produto("PZ", "Panetones", **temporada)
        py = produto("PY", "Pães", **temporada)
        pt = produto("PT", "Outros", fim=date(2026, 12, 1))
        pl = produto("PL", "Pães", inicio=date(2026, 12, 1))  # semanal, lançamento em 01/12, nunca vendeu

        def vender(p, inicio, fim, quantidade):
            for d in dias(inicio, fim):
                db.add(VendaDiaria(negocio_id=neg.id, loja_id=lj.id, produto_id=p.id, data=d,
                                   quantidade=D(quantidade(d)), origem=OrigemVenda.MANUAL))

        vender(pa, date(2025, 10, 1), date(2027, 1, 4), lambda d: "50")
        vender(pz, date(2025, 11, 1), date(2025, 12, 31), lambda d: "30" if d.month == 11 else "80")
        vender(pz, date(2026, 11, 1), date(2026, 12, 31), lambda d: "36" if d.month == 11 else "96")
        vender(py, date(2026, 11, 1), date(2026, 12, 31), lambda d: "40")
        vender(pt, date(2025, 10, 1), date(2026, 12, 1), lambda d: "20")
        db.commit()
        nomes = {pa.id: "PA", pz.id: "PZ", py.id: "PY", pt.id: "PT", pl.id: "PL"}

        def prever_em(alvo):
            prev = {x.produto_id: x for x in prever_central(db, neg.id, central.id, alvo - UM_DIA, alvo)}
            print(f"Previsões de {alvo:%d/%m/%Y}:")
            for pid, x in sorted(prev.items(), key=lambda kv: nomes[kv[0]]):
                c = x.componentes
                print(f"  {nomes[pid]}: método {c.metodo}, base {fmt(c.base)} ({c.semanas_na_base} sem), "
                      f"tendência {fmt(c.tendencia)}, peso {fmt(x.peso_historico)}, proxy {fmt(x.proxy)} "
                      f"({x.origem_proxy}), final {fmt(x.previsao)}")
            return prev

        prev = prever_em(date(2026, 12, 22))
        x = prev.get(pz.id)
        registrar("Z07 PZ em 22/12: ano anterior",
                  x is not None and x.componentes.metodo == "sazonal" and x.componentes.base == D("80")
                  and x.componentes.tendencia == D("1.2") and x.previsao == D("96") and x.proxy is None,
                  f"método {x.componentes.metodo if x else None}, final {fmt(x.previsao) if x else None}")
        registrar("Z11 PT com vigencia encerrada nao recebe previsao", pt.id not in prev and pa.id in prev,
                  f"produtos com previsão: {sorted(nomes[p] for p in prev)}")
        pl_depois = prev.get(pl.id)

        prev = prever_em(date(2026, 11, 3))
        x = prev.get(pz.id)
        registrar("Z08 PZ no inicio da temporada: so dias vigentes",
                  x is not None and x.componentes.base == D("30") and x.componentes.semanas_na_base == 3
                  and x.previsao == D("30"),
                  f"base {fmt(x.componentes.base) if x else None} ({x.componentes.semanas_na_base if x else 0} sem), "
                  f"final {fmt(x.previsao) if x else None}")

        prev = prever_em(date(2026, 11, 10))
        x = prev.get(py.id)
        esperado = D(1) / 6 * 40 + D(5) / 6 * 50
        registrar("Z09 PY 1a temporada -> cold start",
                  x is not None and x.componentes.metodo == "semanal" and x.inicio_historico == date(2026, 11, 1)
                  and x.peso_historico == D(1) / 6 and x.proxy == D("50") and x.origem_proxy == "categoria"
                  and perto(x.previsao, esperado),
                  f"início {x.inicio_historico if x else None}, peso {fmt(x.peso_historico) if x else None}, "
                  f"final {fmt(x.previsao) if x else None} (esperado {fmt(esperado)})")
        registrar("Z10 PT vigente recebe previsao", pt.id in prev and prev[pt.id].previsao == D("20"),
                  f"PT final {fmt(prev[pt.id].previsao) if pt.id in prev else None}")
        # Depois do lançamento (21 dias de vigência, nunca vendeu): o histórico
        # começa em 01/12, não na habilitação -> peso 0,5 e metade proxy
        # (categoria Pães: PA 50 e PY 40) -> 0,5 × 0 + 0,5 × 45 = 22,5.
        registrar("Z14 D30 semanal antes do lancamento: sem previsao; depois, cold start desde o lancamento",
                  pl.id not in prev and pl_depois is not None and pl_depois.inicio_historico == date(2026, 12, 1)
                  and pl_depois.peso_historico == D("0.5") and pl_depois.origem_proxy == "categoria"
                  and pl_depois.previsao == D("22.5"),
                  f"10/11: PL {'com' if pl.id in prev else 'sem'} previsão; 22/12: PL final "
                  f"{fmt(pl_depois.previsao) if pl_depois else None}, início "
                  f"{pl_depois.inicio_historico if pl_depois else None}, peso "
                  f"{fmt(pl_depois.peso_historico) if pl_depois else None}, proxy "
                  f"{pl_depois.origem_proxy if pl_depois else None}")

        prev = prever_em(date(2027, 1, 5))
        registrar("Z12 fora da temporada: PZ e PY sem previsao", sorted(nomes[p] for p in prev) == ["PA", "PL"],
                  f"produtos com previsão: {sorted(nomes[p] for p in prev)}")
        prev = prever_em(date(2026, 10, 20))
        registrar("Z13 antes da temporada: PZ sem previsao", pz.id not in prev and py.id not in prev,
                  f"produtos com previsão: {sorted(nomes[p] for p in prev)}")
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
    print("\n=== Resultado do teste do ramo sazonal ===")
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
