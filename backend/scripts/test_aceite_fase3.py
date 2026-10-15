"""
Critério de aceite da Fase 3 (doc §8): "dado um produto/loja/data, o
serviço retorna uma previsão numérica coerente" nos 5 cenários:
histórico completo, produto novo, sazonal na 1ª temporada, sazonal com
histórico do ano anterior e produto com evento cadastrado.

Chama o serviço real (`prever_central`) contra o banco, num negócio de teste
isolado (apagado no fim), e confere cada número com a conta feita à mão.
Os cenários também são cobertos, em mais detalhe, por test_previsao_cold_start,
test_previsao_sazonal e test_previsao_eventos; este script junta os 5 num lugar.

Dia previsto: terça, 22/12/2026, com vendas conhecidas até segunda, 21/12.
Uma loja, todos os produtos em UN:
  H  histórico completo (Pães): 60 nas terças e 40 nos outros dias desde
     01/09/2026; nos últimos 7 dias (15 a 21/12), 10% a mais.
     -> base = mediana das 6 últimas terças = 60; tendência 1,1; previsão 66.
     O padrão por dia da semana aparece (terça 60, não a média da semana).
  N  produto novo (Pães): vende 30/dia desde 08/12 (2 semanas completas).
     -> própria 30; peso 2/6; proxy = categoria Pães (só H tem histórico
     completo) = 66; previsão = 2/6 × 30 + 4/6 × 66 = 54.
  S1 sazonal (dezembro, recorrente) na 1ª temporada (Pães): 50/dia desde
     01/12/2026, nada em 2025.
     -> sem ano anterior: base semanal com cold start; peso 3/6;
     previsão = 0,5 × 50 + 0,5 × 66 = 58.
  S2 sazonal (dezembro, recorrente) com o ano anterior (Natal): em
     dezembro de 2025, 80/dia, com as terças de 16 e 23/12 em 100 (semana
     do Natal); em dezembro de 2026, 96/dia.
     -> base = mediana do mesmo dia da semana no mesmo período do ano
     anterior (09, 16, 23 e 30/12/2025: 80, 100, 100, 80) = 90; tendência =
     mediana de 96/100 e seis vezes 96/80 = 1,2; previsão 108; sem cold
     start. A base semanal (este ano) daria 96: o número distingue os ramos.
  E  produto com evento (Outros): 20/dia desde 01/09/2026; em 08/12 (terça)
     vendeu 200 num evento "Promoção" (×2); evento "Feriado" ×1,5 em 22/12.
     -> o dia do evento passado fica fora da base (5 terças, não 6) e a
     base continua 20; previsão sem evento 20; com o evento, 30.

Coerência conferida em todos: número presente, positivo e igual à conta.

Uso: python scripts/test_aceite_fase3.py
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
from app.models.nivel_classificacao import NivelClassificacao  # noqa: E402
from app.models.produto import CicloPrevisao, Produto, UnidadeMedida  # noqa: E402
from app.models.produto_classificacao import ProdutoClassificacao  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402
from app.services.previsao_service import prever_central  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 6
PREFIXO_NEGOCIO_TESTE = "_Teste Aceite F3"
D = Decimal
TOL = D("0.000000001")
REFERENCIA = date(2026, 12, 21)  # segunda
ALVO = date(2026, 12, 22)  # terça

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def perto(a, b):
    return a is not None and b is not None and abs(a - b) <= TOL


def fmt(x):
    return "None" if x is None else f"{x:.4f}"


def dias(inicio, fim):
    return [inicio + timedelta(days=k) for k in range((fim - inicio).days + 1)]


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


def cenarios():
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

        dezembro = dict(sazonal=True, inicio=date(2025, 12, 1), fim=date(2025, 12, 31), recorrente=True)

        def produto(codigo, categoria, sazonal=False, inicio=None, fim=None, recorrente=False):
            p = Produto(negocio_id=neg.id, nome=f"_{codigo}", codigo=codigo, unidade_medida=UnidadeMedida.UN,
                        ativo=True, ciclo_previsao=CicloPrevisao.SAZONAL if sazonal else CicloPrevisao.SEMANAL,
                        data_inicio_vigencia=inicio, data_fim_vigencia=fim, vigencia_recorrente=recorrente)
            db.add(p)
            db.flush()
            db.add(ProdutoClassificacao(produto_id=p.id, nivel_id=nivel.id, valor=categoria))
            db.add(ProdutoLoja(produto_id=p.id, loja_id=lj.id))
            return p

        h = produto("H", "Pães")
        n = produto("N", "Pães")
        s1 = produto("S1", "Pães", **dezembro)
        s2 = produto("S2", "Natal", **dezembro)
        e = produto("E", "Outros")

        def vender(p, inicio, fim, quantidade):
            for d in dias(inicio, fim):
                db.add(VendaDiaria(negocio_id=neg.id, loja_id=lj.id, produto_id=p.id, data=d,
                                   quantidade=D(quantidade(d)), origem=OrigemVenda.MANUAL))

        ultimos_7 = REFERENCIA - timedelta(days=6)

        def padrao_h(d):
            normal = D(60) if d.weekday() == 1 else D(40)  # terça = 1
            return normal * D("1.1") if d >= ultimos_7 else normal

        vender(h, date(2026, 9, 1), REFERENCIA, padrao_h)
        vender(n, date(2026, 12, 8), REFERENCIA, lambda d: "30")
        vender(s1, date(2026, 12, 1), REFERENCIA, lambda d: "50")
        semana_natal_2025 = {date(2025, 12, 16), date(2025, 12, 23)}
        vender(s2, date(2025, 12, 1), date(2025, 12, 31), lambda d: "100" if d in semana_natal_2025 else "80")
        vender(s2, date(2026, 12, 1), REFERENCIA, lambda d: "96")
        dia_promocao = date(2026, 12, 8)
        vender(e, date(2026, 9, 1), REFERENCIA, lambda d: "200" if d == dia_promocao else "20")

        def evento(nome, dia, fator):
            ev = Evento(negocio_id=neg.id, central_producao_id=central.id, nome=nome, data_inicio=dia,
                        data_fim=dia, escopo_loja=EscopoLoja.ESPECIFICAS, escopo_produto=EscopoProduto.ESPECIFICOS,
                        tipo_ajuste=TipoAjuste.MULTIPLICADOR, valor_ajuste=D(fator))
            db.add(ev)
            db.flush()
            db.add(EventoLoja(evento_id=ev.id, loja_id=lj.id, negocio_id=neg.id))
            db.add(EventoProduto(evento_id=ev.id, produto_id=e.id, negocio_id=neg.id))

        evento("Promoção", dia_promocao, "2")
        evento("Feriado", ALVO, "1.5")
        db.commit()

        # O serviço, como a API chama: central inteira, referência e dia previsto.
        prev = {x.produto_id: x for x in prever_central(db, neg.id, central.id, REFERENCIA, ALVO)}
        nomes = {h.id: "H", n.id: "N", s1.id: "S1", s2.id: "S2", e.id: "E"}
        print(f"Previsões de {ALVO:%d/%m/%Y} (vendas até {REFERENCIA:%d/%m/%Y}):")
        for pid, x in sorted(prev.items(), key=lambda kv: nomes[kv[0]]):
            c = x.componentes
            print(f"  {nomes[pid]:>2}: método {c.metodo}, base {fmt(c.base)} ({c.semanas_na_base} sem), "
                  f"tendência {fmt(c.tendencia)}, própria {fmt(c.previsao)}, peso {fmt(x.peso_historico)}, "
                  f"proxy {fmt(x.proxy)} ({x.origem_proxy}), sem evento {fmt(x.previsao_sem_evento)}, "
                  f"final {fmt(x.previsao)}")

        def coerente(x, esperado):
            return x is not None and x.previsao is not None and x.previsao > 0 and perto(x.previsao, esperado)

        x = prev.get(h.id)
        registrar("A1 histórico completo: mediana do dia da semana × tendência",
                  coerente(x, D(66)) and x.componentes.metodo == "semanal" and x.componentes.base == D(60)
                  and x.componentes.semanas_na_base == 6 and perto(x.componentes.tendencia, D("1.1"))
                  and x.peso_historico == 1 and x.proxy is None,
                  f"base {fmt(x.componentes.base) if x else None} (terças; a média da semana seria ~45,7), "
                  f"tendência {fmt(x.componentes.tendencia) if x else None}, final {fmt(x.previsao) if x else None} "
                  "(esperado 66)")

        x = prev.get(n.id)
        esperado_n = D(2) / 6 * 30 + D(4) / 6 * 66
        registrar("A2 produto novo: cold start com proxy da categoria",
                  coerente(x, esperado_n) and x.peso_historico == D(2) / 6 and x.componentes.previsao == D(30)
                  and x.origem_proxy == "categoria" and perto(x.proxy, D(66)),
                  f"própria {fmt(x.componentes.previsao) if x else None}, peso {fmt(x.peso_historico) if x else None}, "
                  f"proxy {fmt(x.proxy) if x else None} ({x.origem_proxy if x else None}), "
                  f"final {fmt(x.previsao) if x else None} (esperado {fmt(esperado_n)})")

        x = prev.get(s1.id)
        esperado_s1 = D("0.5") * 50 + D("0.5") * 66
        registrar("A3 sazonal na 1ª temporada: base semanal com cold start",
                  coerente(x, esperado_s1) and x.componentes.metodo == "semanal" and x.peso_historico == D("0.5")
                  and x.inicio_historico == date(2026, 12, 1) and x.origem_proxy == "categoria",
                  f"método {x.componentes.metodo if x else None}, início {x.inicio_historico if x else None}, "
                  f"peso {fmt(x.peso_historico) if x else None}, final {fmt(x.previsao) if x else None} "
                  f"(esperado {fmt(esperado_s1)})")

        x = prev.get(s2.id)
        registrar("A4 sazonal com o ano anterior: base do mesmo período × tendência",
                  coerente(x, D(108)) and x.componentes.metodo == "sazonal" and x.componentes.base == D(90)
                  and x.componentes.tendencia == D("1.2") and x.peso_historico == 1 and x.proxy is None,
                  f"método {x.componentes.metodo if x else None}, base {fmt(x.componentes.base) if x else None}, "
                  f"tendência {fmt(x.componentes.tendencia) if x else None}, final {fmt(x.previsao) if x else None} "
                  "(esperado 108; a base semanal daria 96)")

        x = prev.get(e.id)
        registrar("A5 produto com evento: multiplicador no dia e evento passado fora da base",
                  coerente(x, D(30)) and x.previsao_sem_evento == D(20) and x.componentes.base == D(20)
                  and x.componentes.semanas_na_base == 5 and [ev.nome for ev in x.eventos] == ["Feriado"],
                  f"base {fmt(x.componentes.base) if x else None} ({x.componentes.semanas_na_base if x else 0} terças; "
                  f"a de 08/12 com 200 ficou fora), sem evento {fmt(x.previsao_sem_evento) if x else None}, "
                  f"final {fmt(x.previsao) if x else None} (esperado 30)")

        registrar("A6 todos os 5 cenários com número positivo",
                  all(nomes[p] in nomes.values() for p in prev) and len(prev) == 5
                  and all(x.previsao is not None and x.previsao > 0 for x in prev.values()),
                  f"{len(prev)} previsões: " + ", ".join(f"{nomes[p]} {fmt(x.previsao)}" for p, x in sorted(
                      prev.items(), key=lambda kv: nomes[kv[0]])))
    finally:
        try:
            db.rollback()
            _limpar(db, negocio_ids)
        except Exception as ex:
            print(f"[aviso] Erro na limpeza: {ex}")
        db.close()


def main():
    try:
        cenarios()
    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    print("\n=== Critério de aceite da Fase 3 ===")
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
