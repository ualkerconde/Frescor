"""
Testa o `producao_service` (Fase 4 / N6), com banco: gerar, regerar,
editar, aprovar e apagar a ordem de produção, o trânsito das ordens
aprovadas (D43, D52) e as travas da ordem aprovada.

Negócio de teste isolado (apagado no fim). "Hoje" = segunda 02/11/2026 (D).
Central A (prazo 0): lojas L1 e L2. Central B: sem lojas no início (recebe
a L2 no caso L1). Central C2 (prazo 1): loja L4. Negócio X: outro cliente.

Produtos: P1 diário, validade 1, UN; P2 seg/qui, validade 5, KG, margem
15%; P3 distribuído, diário, validade 30, UN; P4 sem calendário; P5 diário,
validade 5, UN (só na L4).

Casos:
  G1 gerar A/segunda: rascunho, entrega na segunda, 4 itens, 8 linhas,
     2 sem quantidade (P4); sugerida = final; números à mão:
     P1 L1 44 (sobra de validade 1 não conta), P1 L2 44, P2 L1 30,0
     (34,5 − 4,5), P2 L2 34,5, P3 6 e 6
  G2 total do item = soma das linhas (D54): P1 88, P2 64,5, P3 12, P4 0
  G3 componentes gravados: versão do método, referência da previsão, conta
     (mínimo 30 do P2/L1), pouco histórico e indicador de perda
  E1 editar a final do P1/L1 para 50 com motivo: sugerida fica 44
  E2 edições inválidas: UN fracionada, negativa, KG com 4 casas
  E3 editar linha de outra central ou de outro negócio -> não encontrada
  G4 regerar o rascunho: substitui (ordem nova, ajustes perdidos, uma só
     ordem programada no dia)
  A1 aprovar com linha sem quantidade (P4) -> recusado, continua rascunho
  A2 informar o P4 e aprovar -> aprovada, com quem e quando
  A3 ordem aprovada: editar, regerar e apagar -> recusados; a ordem e as
     linhas ficam intactas (é trânsito)
  T3 ordem A/terça: a entrega de segunda (aprovada, sem confirmação) está
     na contagem -> aviso "recebimento não confirmado", sem trânsito
  L1 D57: aprovar com uma loja que saiu da central -> recusado
  A4 apagar um rascunho -> ordem, itens e linhas somem
  T1 D52 (prazo 1): a ordem C2/segunda aprovada (12 do P5 na L4, entrega
     terça) entra como trânsito na ordem C2/terça: 15 contados + 12 − 20
     vendidos na terça = 7 na chegada; alvo 22 -> 15 (sem o trânsito: 22).
     Falha se o trânsito vier vazio havendo ordem aprovada para a loja
  T2 o provedor ignora rascunho, linha já recebida, entrega antes de D e
     outro negócio
  P1 D41: previsão da C2 com referência 31/10 -> atualizada antes de
     calcular (chamada com referência 01/11); a da A, em dia, não
  V1 data que já passou e data além do horizonte -> recusadas
  X1 central de outro negócio -> CentralNaoEncontrada

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_producao_service.py
"""

import sys
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.core.security import hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.calendario_producao import CalendarioProducao, DiaSemana  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.estoque_atual import EstoqueAtual  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.ordem_producao import OrdemProducao, StatusOrdemProducao  # noqa: E402
from app.models.ordem_producao_item import OrdemProducaoItem  # noqa: E402
from app.models.ordem_producao_linha import OrdemProducaoLinha  # noqa: E402
from app.models.previsao_diaria import EstatisticaBase, MetodoPrevisao, PrevisaoDiaria  # noqa: E402
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402
from app.services.necessidade_calculo import VERSAO_METODO_NECESSIDADE, LoteTransito  # noqa: E402
from app.services.necessidade_service import CentralNaoEncontrada  # noqa: E402
from app.services.producao_service import (  # noqa: E402
    AVISO_RECEBIMENTO_NAO_CONFIRMADO,
    OrdemAprovada,
    OrdemInvalida,
    OrdemNaoEncontrada,
    apagar_ordem,
    aprovar_ordem,
    editar_linha,
    gerar_ordem,
    provedor_transito_ordens,
    totais_por_produto,
)

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 18
PREFIXO_NEGOCIO_TESTE = "_Teste Producao"
D = date(2026, 11, 2)  # segunda; também é "hoje"
TER = D + timedelta(days=1)
REF = date(2026, 11, 1)
DEC = Decimal
TODOS = list(DiaSemana)

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    lojas = [i for (i,) in db.query(Loja.id).filter(Loja.negocio_id.in_(negocio_ids))]
    db.query(OrdemProducao).filter(OrdemProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (OrdemProducaoLinha, OrdemProducaoItem, PrevisaoDiaria, EstoqueAtual, CalendarioProducao):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    if lojas:
        db.query(ProdutoLoja).filter(ProdutoLoja.loja_id.in_(lojas)).delete(synchronize_session=False)
    db.query(Usuario).filter(Usuario.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
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
    def __init__(self, db):
        self.db = db
        run = uuid.uuid4().hex[:8]
        self.neg = self._add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} A", ativo=True))
        self.neg_x = self._add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} X", ativo=True))
        self.a = self._add(CentralProducao(negocio_id=self.neg.id, nome="_A", ativa=True))
        self.b = self._add(CentralProducao(negocio_id=self.neg.id, nome="_B", ativa=True))
        self.c2 = self._add(CentralProducao(negocio_id=self.neg.id, nome="_C2", ativa=True, prazo_entrega_dias=1))
        self.l1 = self._loja("L1", self.a)
        self.l2 = self._loja("L2", self.a)
        self.l4 = self._loja("L4", self.c2)
        self.gestor = self._add(Usuario(
            negocio_id=self.neg.id, nome="_Gestor", email=f"tps_{run}@teste.com", senha_hash=hash_senha("x"),
            tem_acesso_app=False, tem_acesso_web=True, tipo_usuario=TipoUsuario.GESTOR_CENTRAL,
            central_producao_id=self.a.id))
        self.p = {}
        self._produto("P1", TODOS, 1)
        self._produto("P2", [DiaSemana.SEGUNDA, DiaSemana.QUINTA], 5, UnidadeMedida.KG, DEC(15))
        self._produto("P3", TODOS, 30, tipo=TipoAbastecimento.DISTRIBUIDO)
        self._produto("P4", [], 2)
        self._produto("P5", TODOS, 5)
        for loja in (self.l1, self.l2):
            for codigo in ("P1", "P2", "P3", "P4"):
                db.add(ProdutoLoja(produto_id=self.p[codigo].id, loja_id=loja.id))
            self._prev(loja, self.a, "P1", [40, 40])
            self._prev(loja, self.a, "P2", [10, 12, 8, 10])
            self._prev(loja, self.a, "P3", [5, 5])
        db.add(ProdutoLoja(produto_id=self.p["P5"].id, loja_id=self.l4.id))
        self._prev(self.l4, self.c2, "P5", [20, 20, 20, 20], ref=date(2026, 10, 31))
        # 00:00 UTC de 02/11 = 21:00 local de domingo 01/11.
        self._estoque(self.l1, "P1", 12, datetime(2026, 11, 2, 0, 0))
        self._estoque(self.l1, "P2", DEC("4.5"), datetime(2026, 11, 2, 0, 0))
        self._estoque(self.l4, "P5", 30, datetime(2026, 11, 2, 0, 0))
        db.commit()

    def _add(self, obj):
        self.db.add(obj)
        self.db.flush()
        return obj

    def _loja(self, codigo, central):
        return self._add(Loja(negocio_id=self.neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}",
                              codigo=codigo, horario_zeragem=time(6, 0), ativo=True))

    def _produto(self, codigo, dias, validade, unidade=UnidadeMedida.UN, margem=None,
                 tipo=TipoAbastecimento.PRODUZIDO):
        produto = self._add(Produto(
            negocio_id=self.neg.id, nome=f"_Produto {codigo}", codigo=codigo, unidade_medida=unidade, ativo=True,
            peso_medio_kg=DEC("0.5") if unidade == UnidadeMedida.KG else None, dias_validade=validade,
            margem_maxima_percentual=margem, tipo_abastecimento=tipo))
        for d in dias:
            self.db.add(CalendarioProducao(negocio_id=self.neg.id, produto_id=produto.id, dia_semana=d))
        self.p[codigo] = produto

    def _prev(self, loja, central, codigo, valores, ref=REF):
        for k, valor in enumerate(valores):
            self.db.add(PrevisaoDiaria(
                negocio_id=self.neg.id, central_producao_id=central.id, loja_id=loja.id,
                produto_id=self.p[codigo].id, data=D + timedelta(days=k), data_referencia=ref, previsao=DEC(valor),
                metodo=MetodoPrevisao.SEMANAL, estatistica=EstatisticaBase.MEDIANA, semanas_na_base=6,
                tendencia=DEC(1), dias_na_tendencia=7, peso_historico=DEC(1), versao_metodo="teste"))

    def _estoque(self, loja, codigo, qtd, quando):
        self.db.add(EstoqueAtual(negocio_id=self.neg.id, loja_id=loja.id, produto_id=self.p[codigo].id,
                                 quantidade_inventariada=int(qtd), estoque_atual_calculado=DEC(qtd),
                                 atualizado_em=quando))


def linhas_da_ordem(db, ordem_id):
    """{(loja_id, codigo do produto): linha}"""
    return {
        (linha.loja_id, codigo): linha
        for linha, codigo in db.query(OrdemProducaoLinha, Produto.codigo)
        .join(OrdemProducaoItem, OrdemProducaoItem.id == OrdemProducaoLinha.item_id)
        .join(Produto, Produto.id == OrdemProducaoItem.produto_id)
        .filter(OrdemProducaoItem.ordem_id == ordem_id)
    }


def espera_erro(nome, chamada, tipo, depois=None):
    try:
        chamada()
        registrar(nome, False, "aceito, mas deveria ter sido recusado")
        return False
    except tipo as e:
        return str(e)
    except Exception as e:
        registrar(nome, False, f"erro de outro tipo: {type(e).__name__}: {e}")
        return False


def main():
    _limpar_residuos()
    db = SessionLocal()
    negocio_ids = []
    chamadas_previsao = []

    def atualizar(db_, negocio_id, central_id, referencia, usuario_id=None):
        chamadas_previsao.append((central_id, referencia))

    try:
        c = Cenario(db)
        negocio_ids = [c.neg.id, c.neg_x.id]
        neg, a, g = c.neg.id, c.a.id, c.gestor.id
        p = {k: v.id for k, v in c.p.items()}

        # ---- G1: gerar ----
        r = gerar_ordem(db, neg, a, D, g, D, atualizar_previsao=atualizar)
        ordem = db.get(OrdemProducao, r.ordem_id)
        linhas = linhas_da_ordem(db, r.ordem_id)
        esperado = {(c.l1.id, "P1"): "44", (c.l2.id, "P1"): "44", (c.l1.id, "P2"): "30.0",
                    (c.l2.id, "P2"): "34.5", (c.l1.id, "P3"): "6", (c.l2.id, "P3"): "6",
                    (c.l1.id, "P4"): None, (c.l2.id, "P4"): None}
        obtido = {k: (None if v.quantidade_sugerida is None else v.quantidade_sugerida) for k, v in linhas.items()}
        erros = [f"{k}: {obtido.get(k)} != {v}" for k, v in esperado.items()
                 if obtido.get(k) != (None if v is None else DEC(v))]
        erros += [f"final != sugerida em {k}" for k, v in linhas.items() if v.quantidade_final != v.quantidade_sugerida]
        # gerado_em em UTC, como aprovado_em/editado_em (o now() do banco é hora local).
        if abs(ordem.gerado_em - datetime.utcnow()) > timedelta(minutes=5):
            erros.append(f"gerado_em {ordem.gerado_em} não está em UTC (agora UTC {datetime.utcnow():%H:%M})")
        ok = (ordem.status == StatusOrdemProducao.RASCUNHO and ordem.data_entrega == D and r.itens == 4
              and r.linhas == 8 and r.sem_quantidade == 2 and not r.substituiu_rascunho and not erros)
        registrar("G1 gerar a ordem", ok, f"status={ordem.status.value} itens={r.itens} linhas={r.linhas} "
                  f"sem_quantidade={r.sem_quantidade}" + (f" | {erros}" if erros else ""))

        totais = totais_por_produto(db, neg, r.ordem_id)
        esperado_t = {p["P1"]: DEC(88), p["P2"]: DEC("64.5"), p["P3"]: DEC(12), p["P4"]: DEC(0)}
        registrar("G2 total do item = soma das linhas", totais == esperado_t,
                  f"{ {k: str(v) for k, v in totais.items()} }")

        comp = linhas[(c.l1.id, "P2")].componentes
        ok = (ordem.versao_metodo == VERSAO_METODO_NECESSIDADE and ordem.referencia_previsao == REF
              and DEC(comp.get("minimo", "0")) == DEC(30) and comp.get("pouco_historico") is False
              and "taxa_perda" in comp and comp.get("dias_cobertura") == ["2026-11-02", "2026-11-03", "2026-11-04"]
              and linhas[(c.l2.id, "P4")].avisos == ["sem_calendario"])
        registrar("G3 componentes gravados", ok, f"versao={ordem.versao_metodo} ref={ordem.referencia_previsao} "
                  f"minimo={comp.get('minimo')} cobertura={comp.get('dias_cobertura')}")

        # ---- E1-E3: editar ----
        linha_p1 = linhas[(c.l1.id, "P1")]
        editar_linha(db, neg, a, linha_p1.id, DEC(50), g, motivo="festa no bairro")
        db.refresh(linha_p1)
        ok = (linha_p1.quantidade_final == DEC(50) and linha_p1.quantidade_sugerida == DEC(44)
              and linha_p1.editado_por_usuario_id == g and linha_p1.editado_em is not None
              and linha_p1.motivo_edicao == "festa no bairro")
        registrar("E1 editar a final", ok, f"final={linha_p1.quantidade_final} sugerida={linha_p1.quantidade_sugerida}")

        msgs = [espera_erro("E2", lambda: editar_linha(db, neg, a, linha_p1.id, DEC("50.5"), g), OrdemInvalida),
                espera_erro("E2", lambda: editar_linha(db, neg, a, linha_p1.id, DEC(-1), g), OrdemInvalida),
                espera_erro("E2", lambda: editar_linha(db, neg, a, linhas[(c.l1.id, "P2")].id, DEC("30.1234"), g),
                            OrdemInvalida)]
        if all(msgs):
            registrar("E2 edicoes invalidas", True, " | ".join(msgs))

        m1 = espera_erro("E3", lambda: editar_linha(db, neg, c.b.id, linha_p1.id, DEC(1), g), OrdemNaoEncontrada)
        m2 = espera_erro("E3", lambda: editar_linha(db, c.neg_x.id, a, linha_p1.id, DEC(1), g), OrdemNaoEncontrada)
        if m1 and m2:
            db.refresh(linha_p1)
            registrar("E3 linha de outra central ou negocio", linha_p1.quantidade_final == DEC(50),
                      f"{m1} (final continua {linha_p1.quantidade_final})")

        # ---- G4: regerar o rascunho ----
        r2 = gerar_ordem(db, neg, a, D, g, D, atualizar_previsao=atualizar)
        quantas = db.query(OrdemProducao).filter(OrdemProducao.central_producao_id == a,
                                                 OrdemProducao.data_producao == D).count()
        linhas = linhas_da_ordem(db, r2.ordem_id)
        ok = (r2.substituiu_rascunho and r2.ordem_id != r.ordem_id and quantas == 1
              and db.get(OrdemProducao, r.ordem_id) is None and linhas[(c.l1.id, "P1")].quantidade_final == DEC(44))
        registrar("G4 regerar o rascunho", ok, f"ordem {r.ordem_id} -> {r2.ordem_id}; ordens no dia={quantas}; "
                  f"final do P1/L1 volta a {linhas[(c.l1.id, 'P1')].quantidade_final}")
        ordem_id = r2.ordem_id

        # ---- A1-A3: aprovar ----
        msg = espera_erro("A1", lambda: aprovar_ordem(db, neg, a, ordem_id, g), OrdemInvalida)
        if msg:
            db.expire_all()
            registrar("A1 aprovar com linha sem quantidade", db.get(OrdemProducao, ordem_id).status
                      == StatusOrdemProducao.RASCUNHO, msg)
        editar_linha(db, neg, a, linhas[(c.l1.id, "P4")].id, DEC(0), g)
        editar_linha(db, neg, a, linhas[(c.l2.id, "P4")].id, DEC(3), g)
        aprovada = aprovar_ordem(db, neg, a, ordem_id, g, agora=datetime(2026, 11, 1, 22, 0))
        registrar("A2 aprovar", aprovada.status == StatusOrdemProducao.APROVADA and aprovada.aprovado_por_usuario_id == g
                  and aprovada.aprovado_em == datetime(2026, 11, 1, 22, 0), f"status={aprovada.status.value}")

        antes = {k: v.quantidade_final for k, v in linhas_da_ordem(db, ordem_id).items()}
        m_editar = espera_erro("A3", lambda: editar_linha(db, neg, a, linhas[(c.l1.id, "P1")].id, DEC(1), g),
                               OrdemAprovada)
        m_regerar = espera_erro("A3", lambda: gerar_ordem(db, neg, a, D, g, D, atualizar_previsao=atualizar),
                                OrdemAprovada)
        m_apagar = espera_erro("A3", lambda: apagar_ordem(db, neg, a, ordem_id), OrdemAprovada)
        if m_editar and m_regerar and m_apagar:
            db.expire_all()
            depois = {k: v.quantidade_final for k, v in linhas_da_ordem(db, ordem_id).items()}
            ainda = db.get(OrdemProducao, ordem_id)
            registrar("A3 ordem aprovada travada", ainda is not None and ainda.status == StatusOrdemProducao.APROVADA
                      and depois == antes, f"{m_regerar} | {m_apagar}")

        # ---- T3: ordem de terça vê a entrega de segunda como já recebida ----
        r_ter = gerar_ordem(db, neg, a, TER, g, D, atualizar_previsao=atualizar)
        linhas_ter = linhas_da_ordem(db, r_ter.ordem_id)
        l1p1 = linhas_ter.get((c.l1.id, "P1"))
        ok = (l1p1 is not None and AVISO_RECEBIMENTO_NAO_CONFIRMADO in l1p1.avisos
              and l1p1.componentes.get("transito_considerado") == "0" and (c.l1.id, "P2") not in linhas_ter)
        registrar("T3 aviso de recebimento nao confirmado", ok,
                  f"avisos={l1p1.avisos if l1p1 else None} transito={l1p1.componentes.get('transito_considerado') if l1p1 else None}")

        # ---- L1 (D57): loja que saiu da central ----
        for (_, codigo), linha in linhas_ter.items():
            if linha.quantidade_final is None:
                editar_linha(db, neg, a, linha.id, DEC(1), g)
        db.execute(text("UPDATE lojas SET central_producao_id = :b WHERE id = :l"), {"b": c.b.id, "l": c.l2.id})
        db.commit()
        msg = espera_erro("L1", lambda: aprovar_ordem(db, neg, a, r_ter.ordem_id, g), OrdemInvalida)
        db.execute(text("UPDATE lojas SET central_producao_id = :a WHERE id = :l"), {"a": a, "l": c.l2.id})
        db.commit()
        if msg:
            db.expire_all()
            registrar("L1 loja fora da central", db.get(OrdemProducao, r_ter.ordem_id).status
                      == StatusOrdemProducao.RASCUNHO, msg)

        # ---- A4: apagar rascunho ----
        itens_ter = [i for (i,) in db.query(OrdemProducaoItem.id).filter(OrdemProducaoItem.ordem_id == r_ter.ordem_id)]
        apagar_ordem(db, neg, a, r_ter.ordem_id)
        restantes = db.query(OrdemProducaoLinha).filter(OrdemProducaoLinha.item_id.in_(itens_ter)).count()
        registrar("A4 apagar rascunho", db.get(OrdemProducao, r_ter.ordem_id) is None and restantes == 0,
                  f"ordem apagada; linhas restantes={restantes}")

        # ---- T1 (D52): trânsito da ordem aprovada, prazo 1 ----
        r_c2 = gerar_ordem(db, neg, c.c2.id, D, g, D, atualizar_previsao=atualizar)
        l4 = linhas_da_ordem(db, r_c2.ordem_id)[(c.l4.id, "P5")]
        # Segunda: 30 contados − 20 vendidos = 10 na terça; alvo 22 -> 12.
        sugerida_seg = l4.quantidade_sugerida
        aprovar_ordem(db, neg, c.c2.id, r_c2.ordem_id, g)
        # Nova contagem no fechamento de segunda (21:00 local = 00:00 UTC de terça).
        db.execute(text("UPDATE estoque_atual SET estoque_atual_calculado = 15, quantidade_inventariada = 15,"
                        " atualizado_em = :t WHERE loja_id = :l AND produto_id = :p"),
                   {"t": datetime(2026, 11, 3, 0, 0), "l": c.l4.id, "p": p["P5"]})
        db.commit()
        transito = provedor_transito_ordens(db, neg, [c.l4.id], TER)
        r_c2_ter = gerar_ordem(db, neg, c.c2.id, TER, g, D, atualizar_previsao=atualizar)
        l4_ter = linhas_da_ordem(db, r_c2_ter.ordem_id)[(c.l4.id, "P5")]
        ok = (sugerida_seg == DEC(12)
              and transito == {(c.l4.id, p["P5"]): [LoteTransito(TER, DEC(12))]}
              and l4_ter.componentes.get("transito_considerado") == "12.000"
              and l4_ter.quantidade_sugerida == DEC(15))
        registrar("T1 D52 transito da ordem aprovada", ok,
                  f"segunda={sugerida_seg}; provedor={transito}; terça: transito="
                  f"{l4_ter.componentes.get('transito_considerado')} sugerida={l4_ter.quantidade_sugerida} (sem transito: 22)")

        # ---- T2: o que o provedor ignora ----
        quarta = TER + timedelta(days=1)
        rascunho_ignorado = provedor_transito_ordens(db, neg, [c.l4.id], quarta) == {}  # C2/terça é rascunho
        antes_de_d = provedor_transito_ordens(db, neg, [c.l4.id], quarta) == {}  # entrega terça < quarta
        outro_negocio = provedor_transito_ordens(db, c.neg_x.id, [c.l4.id], TER) == {}
        db.execute(text("UPDATE ordens_producao_linhas SET recebido_em = :t WHERE id = :i"),
                   {"t": datetime(2026, 11, 3, 12, 0), "i": l4.id})
        db.commit()
        recebida_ignorada = provedor_transito_ordens(db, neg, [c.l4.id], TER) == {}
        db.execute(text("UPDATE ordens_producao_linhas SET recebido_em = NULL WHERE id = :i"), {"i": l4.id})
        db.commit()
        registrar("T2 provedor ignora o que nao e transito",
                  rascunho_ignorado and antes_de_d and outro_negocio and recebida_ignorada,
                  f"rascunho={rascunho_ignorado} entrega_antes={antes_de_d} outro_negocio={outro_negocio} "
                  f"recebida={recebida_ignorada}")

        # ---- P1 (D41) ----
        so_c2 = chamadas_previsao and all(cid == c.c2.id for cid, _ in chamadas_previsao)
        registrar("P1 previsao desatualizada atualizada antes", bool(so_c2) and chamadas_previsao[0] == (c.c2.id, REF)
                  and r_c2.previsao_atualizada and not r.previsao_atualizada,
                  f"chamadas={chamadas_previsao}; A atualizou={r.previsao_atualizada}; C2 atualizou={r_c2.previsao_atualizada}")

        # ---- V1, X1 ----
        m_passado = espera_erro("V1", lambda: gerar_ordem(db, neg, a, D - timedelta(days=1), g, D,
                                                          atualizar_previsao=atualizar), OrdemInvalida)
        m_longe = espera_erro("V1", lambda: gerar_ordem(db, neg, a, D + timedelta(days=7), g, D,
                                                        atualizar_previsao=atualizar), OrdemInvalida)
        if m_passado and m_longe:
            registrar("V1 datas fora do permitido", True, f"{m_passado} | {m_longe}")
        m = espera_erro("X1", lambda: gerar_ordem(db, c.neg_x.id, a, TER, g, D, atualizar_previsao=atualizar),
                        CentralNaoEncontrada)
        if m:
            registrar("X1 central de outro negocio", True, m)
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste do producao_service (N6) ===")
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
