"""
Testa o `necessidade_service` (Fase 4 / N4), com banco: quais lojas e
produtos entram na necessidade de uma central, de onde vem cada entrada
(previsão gravada, calendário, contagem, horário de fechamento da loja,
trânsito) e o isolamento.

Dados num negócio de teste isolado (apagado no fim). Data de produção
D = segunda 02/11/2026; "hoje" = 01/11 (previsões com referência 31/10
estão em dia). Fuso America/Sao_Paulo (UTC−3).

Central A (prazo 0): lojas L1 (fecha 21:00), L2 (fecha 18:00), L3 inativa.
Central B do mesmo negócio: loja LB. Central A2 (prazo 1): loja L4.
Negócio X: outro cliente.

Produtos (negócio A):
  P1 produzido, diário, validade 1, UN
  P2 produzido, seg/qui, validade 5, KG, margem 15%
  P3 distribuído, seg/sex, validade 30, UN
  P4 produzido, sem calendário
  P5 inativo no catálogo (com previsão gravada)
  P6 diário, desabilitado na L2
  P7 diário, vigência terminou em 31/10
  P8 ter/qui (D não é dia de produção)
  P9 seg/qui, validade 5, vigência termina 03/11 (no meio da cobertura)
  P10 seg/qui, validade 5, sem a previsão gravada de 04/11
  P11 diário, validade 1, previsão de pouco histórico (peso 0,5)

Casos:
  E1 linhas: L1 com P1 P2 P3 P4 P6 P9 P10 P11; L2 sem o P6 (desabilitado);
     fora: L3 (inativa), LB (outra central), P5 (inativo), P7 (fora da
     vigência), P8 (não produz na segunda)
  E2 P1/L1: 40 × 1,10 = 44; a sobra contada (validade 1) não conta
  E3 P2/L1 (KG): 10 + 12 + 8 = 30 × 1,15 = 34,5 − 4,5 contados = 30,0
  E4 P2/L2: contagem às 16:30 local de 01/11 vale porque a L2 fecha às
     18:00 (limite 16:00); com 21:00 não valeria -> 30,0 (e não 34,5)
  E5 P3 distribuído: 4 dias (seg a qui) × 5 = 20 × 1,10 = 22; tipo distribuido
  E6 P4 sem calendário -> aviso, sem necessidade
  E7 P9: quarta fora da vigência conta 0 (não "sem previsão"): 10 + 10 = 20
     × 1,10 = 22
  E8 P10: falta a previsão de um dia vigente da cobertura -> aviso sem previsão
  E9 P11: pouco histórico -> margem 20%: 40 × 1,2 = 48
  E10 indicador de perda P1/L1: venda efetiva 120 (api, D16) + 80 = 200;
      perda 10 + 12 = 22 -> 0,11; fora da janela ignorado
  E11 central A2, prazo 1, com trânsito pelo provedor: P2/L4 seg 10 vendidos
      de 5 contados + 8 em trânsito -> sobram 3; ter+qua+qui = 30 × 1,15 =
      34,5 − 3 = 31,5; o provedor recebe negócio, lojas [L4] e D
  E12 previsão desatualizada: central A em dia (referência 31/10); A2 com
      referência 30/10 -> desatualizada
  E13 isolamento: negócio X pedindo a central A -> CentralNaoEncontrada

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_necessidade_service.py
"""

import sys
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.calendario_producao import CalendarioProducao, DiaSemana  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.estoque_atual import EstoqueAtual  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.perda_diaria import OrigemPerda, PerdaDiaria  # noqa: E402
from app.models.previsao_diaria import EstatisticaBase, MetodoPrevisao, PrevisaoDiaria  # noqa: E402
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402
from app.services.necessidade_calculo import (  # noqa: E402
    AVISO_SEM_CALENDARIO,
    AVISO_SEM_CONTAGEM,
    AVISO_SEM_PREVISAO,
    LoteTransito,
)
from app.services.necessidade_service import CentralNaoEncontrada, calcular_necessidades  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 13
PREFIXO_NEGOCIO_TESTE = "_Teste Necessidade"
D = date(2026, 11, 2)  # segunda
HOJE = date(2026, 11, 1)
REF = date(2026, 10, 31)
DEC = Decimal
SEG, TER, QUA, QUI, SEX = DiaSemana.SEGUNDA, DiaSemana.TERCA, DiaSemana.QUARTA, DiaSemana.QUINTA, DiaSemana.SEXTA
TODOS = list(DiaSemana)

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def dia(k):
    return D + timedelta(days=k)


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    lojas = [i for (i,) in db.query(Loja.id).filter(Loja.negocio_id.in_(negocio_ids))]
    for modelo in (PrevisaoDiaria, EstoqueAtual, VendaDiaria, PerdaDiaria, CalendarioProducao):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    if lojas:
        db.query(ProdutoLoja).filter(ProdutoLoja.loja_id.in_(lojas)).delete(synchronize_session=False)
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
        print(f"[limpeza inicial] Apagando {len(negocios)} negócio(s) de execuções anteriores.")
        _limpar(db, [n.id for n in negocios])
    finally:
        db.close()


class Cenario:
    """Monta os dados do teste e guarda os ids."""

    def __init__(self, db):
        self.db = db
        run = uuid.uuid4().hex[:8]
        self.neg = self._add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} A", ativo=True))
        self.neg_x = self._add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} X", ativo=True))
        self.central = self._add(CentralProducao(negocio_id=self.neg.id, nome="_A", ativa=True))
        self.central_b = self._add(CentralProducao(negocio_id=self.neg.id, nome="_B", ativa=True))
        self.central_2 = self._add(CentralProducao(negocio_id=self.neg.id, nome="_A2", ativa=True,
                                                   prazo_entrega_dias=1))
        self.l1 = self._loja("L1", self.central)
        self.l2 = self._loja("L2", self.central, fechamento=time(18, 0))
        self.l3 = self._loja("L3", self.central, ativo=False)
        self.lb = self._loja("LB", self.central_b)
        self.l4 = self._loja("L4", self.central_2)
        self.p = {}
        self._produto("P1", TODOS, validade=1)
        self._produto("P2", [SEG, QUI], validade=5, unidade=UnidadeMedida.KG, margem=DEC(15))
        self._produto("P3", [SEG, SEX], validade=30, tipo=TipoAbastecimento.DISTRIBUIDO)
        self._produto("P4", [], validade=2)
        self._produto("P5", TODOS, validade=1, ativo=False)
        self._produto("P6", TODOS, validade=1)
        self._produto("P7", TODOS, validade=1, fim=date(2026, 10, 31))
        self._produto("P8", [TER, QUI], validade=2)
        self._produto("P9", [SEG, QUI], validade=5, fim=dia(1))
        self._produto("P10", [SEG, QUI], validade=5)
        self._produto("P11", TODOS, validade=1)
        for loja in (self.l1, self.l2, self.l3, self.lb, self.l4):
            for codigo, produto in self.p.items():
                ativo = not (loja is self.l2 and codigo == "P6")
                db.add(ProdutoLoja(produto_id=produto.id, loja_id=loja.id, ativo=ativo))
        db.flush()

        # Previsões (referência 31/10) da central A.
        for loja in (self.l1, self.l2, self.l3):
            self._prev(loja, "P1", {0: 40 if loja is not self.l2 else 30})
            self._prev(loja, "P2", {0: 10, 1: 12, 2: 8} if loja is self.l1 else {0: 10, 1: 10, 2: 10})
            self._prev(loja, "P3", {0: 5, 1: 5, 2: 5, 3: 5})
            self._prev(loja, "P5", {0: 9})
            self._prev(loja, "P6", {0: 9})
            self._prev(loja, "P9", {0: 10, 1: 10})
            self._prev(loja, "P10", {0: 10, 1: 10})  # falta 04/11
            self._prev(loja, "P11", {0: 40}, peso=DEC("0.5"))
        self._prev(self.lb, "P1", {0: 99}, central=self.central_b)
        # Central A2 (prazo 1): previsão com referência 30/10 (desatualizada).
        self._prev(self.l4, "P2", {0: 10, 1: 12, 2: 8, 3: 10}, central=self.central_2, ref=date(2026, 10, 30))

        # Contagens (UTC sem fuso). 00:00 UTC de 02/11 = 21:00 local de 01/11.
        self._estoque(self.l1, "P1", 12, datetime(2026, 11, 2, 0, 0))
        self._estoque(self.l1, "P2", DEC("4.5"), datetime(2026, 11, 2, 0, 0))
        # 19:30 UTC = 16:30 local: vale só com o fechamento de 18:00 da L2.
        self._estoque(self.l2, "P2", DEC("4.5"), datetime(2026, 11, 1, 19, 30))
        self._estoque(self.l4, "P2", 5, datetime(2026, 11, 2, 0, 0))

        # Indicador de perda de P1/L1 (janela 05/10 a 01/11).
        self._venda_perda(VendaDiaria, OrigemVenda, dia(-2), {"manual": 100, "api": 120})
        self._venda_perda(VendaDiaria, OrigemVenda, dia(-1), {"manual": 80})
        self._venda_perda(VendaDiaria, OrigemVenda, dia(-29), {"manual": 1000})  # fora da janela
        self._venda_perda(VendaDiaria, OrigemVenda, D, {"manual": 1000})  # o próprio D: fora
        self._venda_perda(PerdaDiaria, OrigemPerda, dia(-2), {"manual": 10})
        self._venda_perda(PerdaDiaria, OrigemPerda, dia(-1), {"manual": 12})
        db.commit()

    def _add(self, obj):
        self.db.add(obj)
        self.db.flush()
        return obj

    def _loja(self, codigo, central, fechamento=time(21, 0), ativo=True):
        return self._add(Loja(negocio_id=self.neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}",
                              codigo=codigo, horario_zeragem=time(6, 0), horario_fechamento=fechamento,
                              ativo=ativo))

    def _produto(self, codigo, dias, validade, unidade=UnidadeMedida.UN, margem=None,
                 tipo=TipoAbastecimento.PRODUZIDO, ativo=True, fim=None):
        produto = self._add(Produto(
            negocio_id=self.neg.id, nome=f"_Produto {codigo}", codigo=codigo, unidade_medida=unidade,
            peso_medio_kg=DEC("0.5") if unidade == UnidadeMedida.KG else None, ativo=ativo,
            dias_validade=validade, margem_maxima_percentual=margem, tipo_abastecimento=tipo,
            data_fim_vigencia=fim,
        ))
        for d in dias:
            self.db.add(CalendarioProducao(negocio_id=self.neg.id, produto_id=produto.id, dia_semana=d))
        self.p[codigo] = produto

    def _prev(self, loja, codigo, valores, peso=DEC(1), central=None, ref=REF):
        for k, valor in valores.items():
            self.db.add(PrevisaoDiaria(
                negocio_id=self.neg.id, central_producao_id=(central or self.central).id, loja_id=loja.id,
                produto_id=self.p[codigo].id, data=dia(k), data_referencia=ref, previsao=DEC(valor),
                metodo=MetodoPrevisao.SEMANAL, estatistica=EstatisticaBase.MEDIANA, semanas_na_base=6,
                tendencia=DEC(1), dias_na_tendencia=7, peso_historico=peso, versao_metodo="teste",
            ))

    def _estoque(self, loja, codigo, qtd, quando):
        self.db.add(EstoqueAtual(negocio_id=self.neg.id, loja_id=loja.id, produto_id=self.p[codigo].id,
                                 quantidade_inventariada=int(qtd), estoque_atual_calculado=DEC(qtd),
                                 atualizado_em=quando))

    def _venda_perda(self, modelo, origens, data, por_origem):
        for origem, qtd in por_origem.items():
            self.db.add(modelo(negocio_id=self.neg.id, loja_id=self.l1.id, produto_id=self.p["P1"].id,
                               data=data, quantidade=DEC(qtd), origem=origens(origem)))


def main():
    _limpar_residuos()
    db = SessionLocal()
    negocio_ids = []
    try:
        c = Cenario(db)
        negocio_ids = [c.neg.id, c.neg_x.id]
        r = calcular_necessidades(db, c.neg.id, c.central.id, D, HOJE)
        por_par = {(i.loja_id, i.produto_codigo): i for i in r.itens}

        esperado = {(c.l1.id, p) for p in ("P1", "P2", "P3", "P4", "P6", "P9", "P10", "P11")}
        esperado |= {(c.l2.id, p) for p in ("P1", "P2", "P3", "P4", "P9", "P10", "P11")}
        obtido = set(por_par)
        nomes = {c.l1.id: "L1", c.l2.id: "L2", c.l3.id: "L3", c.lb.id: "LB"}
        registrar("E1 linhas da central", obtido == esperado,
                  f"{len(obtido)} linhas" + (f"; a mais: {sorted((nomes.get(l), p) for l, p in obtido - esperado)}"
                                            f"; faltando: {sorted((nomes.get(l), p) for l, p in esperado - obtido)}"
                                            if obtido != esperado else ", como esperado"))

        def conferir(nome, par, necessidade, avisos=None, **campos):
            item = por_par.get(par)
            if item is None:
                registrar(nome, False, "linha ausente")
                return None
            res = item.resultado
            erros = []
            if res.necessidade != (None if necessidade is None else DEC(necessidade)):
                erros.append(f"necessidade {res.necessidade} != {necessidade}")
            if avisos is not None and sorted(res.avisos) != sorted(avisos):
                erros.append(f"avisos {list(res.avisos)} != {list(avisos)}")
            for campo, valor in campos.items():
                obtido = getattr(item, campo, None) if hasattr(item, campo) else getattr(res, campo)
                if obtido != valor:
                    erros.append(f"{campo} {obtido} != {valor}")
            registrar(nome, not erros, f"necessidade={res.necessidade} avisos={list(res.avisos)}"
                      + (f" | {'; '.join(erros)}" if erros else ""))
            return item

        conferir("E2 P1/L1 validade 1", (c.l1.id, "P1"), 44, (), estoque_na_chegada=DEC(0))
        conferir("E3 P2/L1 KG com margem 15%", (c.l1.id, "P2"), "30.0", (), minimo=DEC(30))
        conferir("E4 P2/L2 fechamento da loja (18:00)", (c.l2.id, "P2"), "30.0", (), contagem_valida=True)
        conferir("E5 P3 distribuido", (c.l1.id, "P3"), 22, (AVISO_SEM_CONTAGEM,),
                 tipo_abastecimento="distribuido", dias_cobertura=(D, dia(1), dia(2), dia(3)))
        conferir("E6 P4 sem calendario", (c.l1.id, "P4"), None, (AVISO_SEM_CALENDARIO,))
        conferir("E7 P9 dia fora da vigencia conta 0", (c.l1.id, "P9"), 22, (AVISO_SEM_CONTAGEM,), minimo=DEC(20))
        conferir("E8 P10 sem previsao de um dia", (c.l1.id, "P10"), None, (AVISO_SEM_CONTAGEM, AVISO_SEM_PREVISAO))
        conferir("E9 P11 pouco historico", (c.l1.id, "P11"), 48, (AVISO_SEM_CONTAGEM,), pouco_historico=True,
                 margem=DEC(20))
        conferir("E10 indicador de perda", (c.l1.id, "P1"), 44, taxa_perda=DEC("0.11"))

        chamadas = []

        def provedor(db_, negocio_id, lojas, data_producao):
            chamadas.append((negocio_id, list(lojas), data_producao))
            return {(c.l4.id, c.p["P2"].id): [LoteTransito(D, DEC(8))]}

        r2 = calcular_necessidades(db, c.neg.id, c.central_2.id, D, HOJE, provedor_transito=provedor)
        item = next((i for i in r2.itens if i.loja_id == c.l4.id and i.produto_codigo == "P2"), None)
        ok = (item is not None and item.resultado.necessidade == DEC("31.5")
              and item.resultado.estoque_na_chegada == DEC(3) and chamadas == [(c.neg.id, [c.l4.id], D)])
        registrar("E11 prazo 1 com transito do provedor", ok,
                  f"necessidade={item.resultado.necessidade if item else None} "
                  f"estoque_na_chegada={item.resultado.estoque_na_chegada if item else None} chamadas={chamadas}")

        ok = (not r.previsao_desatualizada and r.referencia_previsao == REF
              and r2.previsao_desatualizada and r2.referencia_previsao == date(2026, 10, 30))
        registrar("E12 previsao desatualizada", ok,
                  f"A: {r.referencia_previsao} desatualizada={r.previsao_desatualizada}; "
                  f"A2: {r2.referencia_previsao} desatualizada={r2.previsao_desatualizada}")

        try:
            calcular_necessidades(db, c.neg_x.id, c.central.id, D, HOJE)
            registrar("E13 isolamento entre negocios", False, "negócio X recebeu a central A")
        except CentralNaoEncontrada as e:
            registrar("E13 isolamento entre negocios", True, f"CentralNaoEncontrada: {e}")
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste do necessidade_service (N4) ===")
            for linha in resultados:
                print(linha)
            falhas = [x for x in resultados if x.startswith(FAIL)]
            if len(resultados) < TOTAL_CASOS:
                print(f"\nTESTE INCOMPLETO: só {len(resultados)} de {TOTAL_CASOS} casos rodaram")
            else:
                print(f"\n{'TODOS OS CASOS PASSARAM' if not falhas else f'{len(falhas)} CASO(S) FALHARAM'}")
        finally:
            try:
                db.rollback()
                _limpar(db, negocio_ids)
            except Exception as e:
                print(f"[aviso] Erro na limpeza: {e}")
            db.close()

    if len(resultados) < TOTAL_CASOS or any(x.startswith(FAIL) for x in resultados):
        sys.exit(1)


if __name__ == "__main__":
    main()
