"""
Testa o recebimento na loja e o trânsito pelo romaneio (Fase 5 / E5):
`recebimento_service` (D77, D78, D85), o provedor de trânsito novo
(`producao_service.provedor_transito_ordens`, D79, D89), as marcas da linha
da necessidade e a situação na consulta do gestor.

Regra da chegada (D89, opção A): entrega sem confirmação, ou confirmada com
atraso, conta como chegada no dia de entrega, antes da contagem do
fechamento. Confirmação no prazo depois da contagem entra pela recebida.

Negócio de teste isolado (apagado no fim). Hora local = UTC − 3.
Central C (prazo 1): lojas 001, 002, 003, 005, operadores O1, O2, O3, O5.
Produto P (UN, validade 5, todo dia, margem padrão 10%), previsão 10 em
todos os dias -> cobertura de 1 dia, alvo 11; com prazo 1 a loja vende 10
no dia D antes da chegada (D45).
Central C2 (prazo 1): loja 004, só para a ordem sem romaneio (T5).

Ordem O1 (produção 02/11, entrega 03/11, aprovada), finais 12 / 8 / 6 / 4
(planejado 30). Produção 20 -> rateio (D70) 20 x 12/30 = 8; 5,33; 4;
2,67 -> 8/5/4/2 + 1 para o maior resto (005) -> romaneio 8 / 5 / 4 / 3.
Saída de 001, 002, 003 às 06:00 de 03/11; a 005 sai depois do R4.

Conta à mão (estoque na chegada = contagem + trânsito + recebido depois da
contagem − 10; necessidade = 11 − isso, no mínimo 0):
  D1 = 03/11, contagem 10 (21:00 de 02/11): trânsito pela final do
     ROMANEIO: 001 10+8-10=8 -> 3 (pela ordem, 12: daria 0); 002 5 -> 6;
     003 4 -> 7; 005 3 -> 8.
  D2 = 04/11, contagem 10 (21:00 de 03/11):
     001 confirmou às 10:00 de 03/11 (antes da contagem) -> já está nela:
         10-10=0 -> 11 (em dobro: 10+8-10 -> 3).
     002 antes da confirmação: presumida na contagem -> 11. Confirma às
         22:30 de 03/11 (no prazo, DEPOIS da contagem) com 3 (falta) ->
         10+3-10=3 -> 8. A ordem de 04/11 aprovada às 21:35 fica com 11.
     003 e 005 sem confirmação, ainda no dia de entrega -> 11, sem marca.
     Na ordem D2, a 003 é ajustada para 2 antes de aprovar.
  D3 = 05/11, contagem 10 (21:00 de 04/11): trânsito = ordem D2 (entrega
     05/11, sem romaneio, pela final da ordem): 001 11 -> 10+11-10=11 -> 0;
     003 2 -> 2 -> 9. A entrega de 03/11 da 003 e da 005 terminou sem
     confirmação -> "sem confirmação", presumida pela final do romaneio
     (4 e 3; pela ordem seria 6 e 4), fora do trânsito.
     003 confirma COM ATRASO às 22:00 de 04/11 (dia seguinte, no prazo da
     D85; em UTC já é 05/11) com 2 (avaria): a necessidade continua 9 e a
     marca vira "confirmada com atraso" (D89). A 005 tenta às 00:30 de
     05/11 -> prazo encerrado.

Casos:
  R4 confirmar entrega sem saída -> recusado
  L1 o que cada operador vê: só as entregas da própria loja, com saída
  T1 D1: trânsito pela final do romaneio (rateada), não pela da ordem
  R2 diferença sem motivo -> recusada, nada gravado
  R6 inválidos (UN fracionada, negativa, "outro" sem texto, item de outra
     entrega) -> recusados, nada gravado
  R3 entrega de outra loja e de outro negócio -> não encontrada
  R1 "recebi tudo certo" -> recebida = final; estoque_atual intacto (D79)
  R5 confirmar de novo -> recusado
  T3 D2: recebida antes da contagem não conta em dobro
  T4b D2, ainda no dia de entrega: sem marca e fora do trânsito
  T2 confirmação no prazo depois da contagem: situação "recebida" com
     diferença, recebida gravada com motivo
  T8 D2: a necessidade muda (presumida -> recebida), e a ordem aprovada
     entre as duas fica intacta (D73)
  T5 D3: sem romaneio, trânsito pela final da ordem (D52)
  T4 D3: "sem confirmação" na linha da necessidade (aviso + presumida pela
     final do romaneio) e na consulta do gestor; fora do trânsito
  T6 confirmação no dia seguinte (22:00 local, 01:00 UTC) -> aceita,
     "confirmada com atraso", recebida substitui a presumida
  T9 D3 antes e depois da confirmação atrasada: o número não muda, só a
     marca
  T7 confirmar depois do fim do dia seguinte -> recusado; continua "sem
     confirmação" e sai da lista do operador
  V1 a ordem nova grava a versão 2026.10-n2

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_recebimento_transito.py
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
from app.models.romaneio import Romaneio  # noqa: E402
from app.models.romaneio_entrega import RomaneioEntrega, SituacaoEntrega  # noqa: E402
from app.models.romaneio_item import RomaneioItem  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402
from app.services.distribuicao_consulta_service import obter_romaneio  # noqa: E402
from app.services.distribuicao_service import (  # noqa: E402
    aprovar_romaneio,
    gerar_romaneio,
    registrar_producao,
    registrar_saida,
)
from app.services.necessidade_calculo import VERSAO_METODO_NECESSIDADE  # noqa: E402
from app.services.necessidade_service import calcular_necessidades  # noqa: E402
from app.services.producao_service import (  # noqa: E402
    AVISO_CONFIRMADA_COM_ATRASO,
    AVISO_RECEBIMENTO_NAO_CONFIRMADO,
    AVISO_SEM_CONFIRMACAO,
    aprovar_ordem,
    editar_linha,
    gerar_ordem,
    provedor_transito_ordens,
)
from app.services.recebimento_service import (  # noqa: E402
    DiferencaItem,
    EntregaNaoEncontrada,
    RecebimentoInvalido,
    RecebimentoNaoPermitido,
    confirmar,
    detalhar,
    listar_pendentes,
)

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 18
PREFIXO_NEGOCIO_TESTE = "_Teste Recebimento"
DEC = Decimal
TODOS = list(DiaSemana)

D0 = date(2026, 11, 2)  # produção da ordem O1
E = date(2026, 11, 3)  # entrega da O1
D1, D2, D3 = E, E + timedelta(days=1), E + timedelta(days=2)
# Horas em UTC sem fuso (como o app e o serviço gravam); local = UTC - 3.
APROVACAO = datetime(2026, 11, 2, 15, 0)
SAIDA = datetime(2026, 11, 3, 9, 0)  # 06:00 local de 03/11
CONTAGEM_D1 = datetime(2026, 11, 3, 0, 0)  # 21:00 local de 02/11
CONTAGEM_D2 = datetime(2026, 11, 4, 0, 0)  # 21:00 local de 03/11
CONTAGEM_D3 = datetime(2026, 11, 5, 0, 0)  # 21:00 local de 04/11
CONFIRMA_001 = datetime(2026, 11, 3, 13, 0)  # 10:00 local de 03/11 (antes da contagem D2)
AGORA_D2 = datetime(2026, 11, 4, 0, 30)  # 21:30 local de 03/11
CONFIRMA_002 = datetime(2026, 11, 4, 1, 30)  # 22:30 local de 03/11 (no prazo, depois da contagem)
AGORA_D3 = datetime(2026, 11, 5, 0, 30)  # 21:30 local de 04/11
CONFIRMA_003 = datetime(2026, 11, 5, 1, 0)  # 22:00 local de 04/11 (dia seguinte; em UTC, 05/11)
TENTA_005 = datetime(2026, 11, 5, 3, 30)  # 00:30 local de 05/11 (prazo encerrado)

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def espera_erro(nome, acao, tipo, contem=None, depois=None):
    """Roda `acao`; passa se levantar `tipo` (com `contem` na mensagem) e `depois()` devolver (True, texto)."""
    try:
        acao()
        registrar(nome, False, "foi aceito, mas deveria ter sido recusado")
        return
    except tipo as e:
        msg = str(e)
    except Exception as e:
        registrar(nome, False, f"erro inesperado -> {type(e).__name__}: {e}")
        return
    ok = contem is None or contem in msg
    detalhe = f"recusado ({tipo.__name__}): {msg}"
    if depois is not None:
        ok_depois, txt = depois()
        ok = ok and ok_depois
        detalhe += f"; {txt}"
    registrar(nome, ok, detalhe)


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    lojas = [i for (i,) in db.query(Loja.id).filter(Loja.negocio_id.in_(negocio_ids))]
    db.query(Romaneio).filter(Romaneio.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (RomaneioItem, RomaneioEntrega):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(OrdemProducao).filter(OrdemProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (OrdemProducaoLinha, OrdemProducaoItem, PrevisaoDiaria, EstoqueAtual, CalendarioProducao):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    if lojas:
        db.query(ProdutoLoja).filter(ProdutoLoja.loja_id.in_(lojas)).delete(synchronize_session=False)
    for modelo in (Usuario, Produto, Loja, CentralProducao):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
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
        self.run = run
        self.neg = self._add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} A", ativo=True))
        self.neg_x = self._add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} X", ativo=True))
        self.c = self._add(CentralProducao(negocio_id=self.neg.id, nome="_C", ativa=True, prazo_entrega_dias=1))
        self.c2 = self._add(CentralProducao(negocio_id=self.neg.id, nome="_C2", ativa=True, prazo_entrega_dias=1))
        self.cx = self._add(CentralProducao(negocio_id=self.neg_x.id, nome="_X", ativa=True))
        self.lojas = {cod: self._loja(self.neg, self.c, cod) for cod in ("001", "002", "003", "005")}
        self.l4 = self._loja(self.neg, self.c2, "004")
        self.lx = self._loja(self.neg_x, self.cx, "X01")
        self.gestor = self._usuario(self.neg, f"trt_g_{run}", central=self.c)
        self.op = {cod: self._usuario(self.neg, f"trt_{cod}_{run}", loja=loja) for cod, loja in self.lojas.items()}
        self.op_x = self._usuario(self.neg_x, f"trt_x_{run}", loja=self.lx)
        self.p = self._add(Produto(negocio_id=self.neg.id, nome="_Produto P", codigo="P", ativo=True,
                                   unidade_medida=UnidadeMedida.UN, dias_validade=5,
                                   tipo_abastecimento=TipoAbastecimento.PRODUZIDO))
        for d in TODOS:
            db.add(CalendarioProducao(negocio_id=self.neg.id, produto_id=self.p.id, dia_semana=d))
        for loja, central in [(lj, self.c) for lj in self.lojas.values()] + [(self.l4, self.c2)]:
            db.add(ProdutoLoja(produto_id=self.p.id, loja_id=loja.id))
            for k in range(8):
                db.add(PrevisaoDiaria(
                    negocio_id=self.neg.id, central_producao_id=central.id, loja_id=loja.id, produto_id=self.p.id,
                    data=D0 + timedelta(days=k), data_referencia=D0 - timedelta(days=1), previsao=DEC(10),
                    metodo=MetodoPrevisao.SEMANAL, estatistica=EstatisticaBase.MEDIANA, semanas_na_base=6,
                    tendencia=DEC(1), dias_na_tendencia=7, peso_historico=DEC(1), versao_metodo="teste"))
            db.add(EstoqueAtual(negocio_id=self.neg.id, loja_id=loja.id, produto_id=self.p.id,
                                quantidade_inventariada=10, estoque_atual_calculado=DEC(10),
                                atualizado_em=CONTAGEM_D1))
        finais = {"001": 12, "002": 8, "003": 6, "005": 4}
        self.o1 = self._ordem(self.c, D0, E, [(self.lojas[k], v) for k, v in finais.items()])
        self.o4 = self._ordem(self.c2, D0, E, [(self.l4, 7)])
        db.commit()

    def _add(self, obj):
        self.db.add(obj)
        self.db.flush()
        return obj

    def _loja(self, neg, central, codigo):
        return self._add(Loja(negocio_id=neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}",
                              codigo=codigo, horario_zeragem=time(6, 0), ativo=True))

    def _usuario(self, neg, nome, loja=None, central=None):
        return self._add(Usuario(
            negocio_id=neg.id, nome=f"_U {nome}", email=f"{nome}@teste.com", senha_hash=hash_senha("x"),
            loja_id=loja.id if loja else None, central_producao_id=central.id if central else None,
            tem_acesso_app=loja is not None, tem_acesso_web=central is not None,
            tipo_usuario=TipoUsuario.OPERADOR_LOJA if loja else TipoUsuario.GESTOR_CENTRAL))

    def _ordem(self, central, producao, entrega, linhas):
        ordem = self._add(OrdemProducao(
            negocio_id=self.neg.id, central_producao_id=central.id, data_producao=producao, data_entrega=entrega,
            versao_metodo="teste", gerado_em=APROVACAO, status=StatusOrdemProducao.APROVADA,
            aprovado_em=APROVACAO, aprovado_por_usuario_id=self.gestor.id))
        item = self._add(OrdemProducaoItem(negocio_id=self.neg.id, ordem_id=ordem.id, produto_id=self.p.id,
                                           tipo_abastecimento=TipoAbastecimento.PRODUZIDO,
                                           unidade=UnidadeMedida.UN))
        ordem.item_id = item.id
        for loja, final in linhas:
            self._add(OrdemProducaoLinha(negocio_id=self.neg.id, item_id=item.id, loja_id=loja.id,
                                         quantidade_sugerida=DEC(final), quantidade_final=DEC(final)))
        return ordem


def main():
    _limpar_residuos()
    db = SessionLocal()
    negocio_ids = []
    try:
        c = Cenario(db)
        negocio_ids = [c.neg.id, c.neg_x.id]
        neg, C, g, P = c.neg.id, c.c.id, c.gestor.id, c.p.id
        L = {k: v.id for k, v in c.lojas.items()}
        O = {k: v.id for k, v in c.op.items()}

        def contar(quando):
            db.execute(text("UPDATE estoque_atual SET atualizado_em = :t WHERE negocio_id = :n"),
                       {"t": quando, "n": neg})
            db.commit()

        def necessidade(dia, hoje):
            """{codigo da loja: resultado} da central C para o dia."""
            db.expire_all()
            r = calcular_necessidades(db, neg, C, dia, hoje, provedor_transito=provedor_transito_ordens)
            return {i.loja_codigo: i.resultado for i in r.itens}

        def resumo(res):
            return {k: (str(v.necessidade), str(v.transito_considerado), str(v.recebido_apos_contagem))
                    for k, v in sorted(res.items())}

        def linhas_ordem(ordem_id):
            db.expire_all()
            return {codigo: linha for linha, codigo in db.query(OrdemProducaoLinha, Loja.codigo)
                    .join(Loja, Loja.id == OrdemProducaoLinha.loja_id)
                    .join(OrdemProducaoItem, OrdemProducaoItem.id == OrdemProducaoLinha.item_id)
                    .filter(OrdemProducaoItem.ordem_id == ordem_id)}

        def itens_entrega(entrega_id):
            db.expire_all()
            return db.query(RomaneioItem).filter(RomaneioItem.entrega_id == entrega_id).all()

        # ---- romaneio da O1 (serviços do E4): produção 20 -> 8/5/4/3 ----
        registrar_producao(db, neg, C, c.o1.id, {c.o1.item_id: DEC(20)}, g, agora=APROVACAO)
        rom_id = gerar_romaneio(db, neg, C, c.o1.id, g, agora=APROVACAO).romaneio_id
        aprovar_romaneio(db, neg, C, rom_id, g, agora=APROVACAO)
        ent = {e.loja_codigo: e for e in obter_romaneio(db, neg, C, rom_id, agora=SAIDA).entregas}
        ENT = {k: v.entrega_id for k, v in ent.items()}
        ITEM = {k: v.itens[0].item_id for k, v in ent.items()}
        finais_rom = {k: str(v.itens[0].quantidade_final) for k, v in ent.items()}
        if finais_rom != {"001": "8.000", "002": "5.000", "003": "4.000", "005": "3.000"}:
            raise RuntimeError(f"cenário errado: finais do romaneio {finais_rom}")

        # ---- R4: sem saída ----
        espera_erro("R4 confirmar sem saida",
                    lambda: confirmar(db, neg, L["005"], ENT["005"], O["005"], agora=SAIDA),
                    RecebimentoNaoPermitido, "ainda não registrou a saída")
        registrar_saida(db, neg, C, rom_id, g, [ENT["001"], ENT["002"], ENT["003"]], agora=SAIDA)

        # ---- L1: o que cada operador vê ----
        vistos = {k: [(x.entrega_id, x.situacao.situacao, str(x.itens[0].quantidade_expedida))
                      for x in listar_pendentes(db, neg, L[k], agora=SAIDA)] for k in L}
        esperado = {"001": [(ENT["001"], "a_caminho", "8.000")], "002": [(ENT["002"], "a_caminho", "5.000")],
                    "003": [(ENT["003"], "a_caminho", "4.000")], "005": []}
        registrar("L1 cada loja ve so a propria entrega com saida", vistos == esperado,
                  f"{ {k: [(s, q) for _, s, q in v] for k, v in vistos.items()} }")
        registrar_saida(db, neg, C, rom_id, g, [ENT["005"]], agora=SAIDA)

        # ---- T1: D1, trânsito pela final do romaneio ----
        r1 = necessidade(D1, D0)
        esperado = {"001": ("3", "8.000", "0"), "002": ("6", "5.000", "0"), "003": ("7", "4.000", "0"),
                    "005": ("8", "3.000", "0")}
        registrar("T1 transito pela final do romaneio (nao pela da ordem)", resumo(r1) == esperado,
                  f"(necessidade, transito, recebido) {resumo(r1)}; pela ordem a 001 daria 0")

        # ---- R2, R6, R3: recusas sem gravar nada ----
        def nada_gravado(codigo):
            def conferir():
                db.expire_all()
                e = db.get(RomaneioEntrega, ENT[codigo])
                itens = itens_entrega(ENT[codigo])
                ok = e.situacao == SituacaoEntrega.EXPEDIDA and all(i.quantidade_recebida is None for i in itens)
                return ok, f"entrega {codigo} {e.situacao.value}, recebida {[i.quantidade_recebida for i in itens]}"
            return conferir

        espera_erro("R2 diferenca sem motivo",
                    lambda: confirmar(db, neg, L["002"], ENT["002"], O["002"], {ITEM["002"]: DiferencaItem(DEC(3))},
                                      agora=CONFIRMA_001),
                    RecebimentoInvalido, "informe o motivo", nada_gravado("002"))
        recusas = []
        for rotulo, dif in {
            "fracionada": {ITEM["002"]: DiferencaItem(DEC("2.5"), "falta")},
            "negativa": {ITEM["002"]: DiferencaItem(DEC(-1), "falta")},
            "outro sem texto": {ITEM["002"]: DiferencaItem(DEC(4), "outro", "  ")},
            "motivo invalido": {ITEM["002"]: DiferencaItem(DEC(4), "roubo")},
            "item de outra entrega": {ITEM["001"]: DiferencaItem(DEC(4), "falta")},
        }.items():
            try:
                confirmar(db, neg, L["002"], ENT["002"], O["002"], dif, agora=CONFIRMA_001)
                recusas.append(f"{rotulo}: ACEITO")
            except (RecebimentoInvalido, EntregaNaoEncontrada) as e:
                recusas.append(f"{rotulo}: {type(e).__name__}")
        ok_nada, txt = nada_gravado("002")()
        registrar("R6 confirmacoes invalidas", ok_nada and not any("ACEITO" in r for r in recusas),
                  f"{recusas}; {txt}")
        vazou = []
        for rotulo, acao in {
            "operador da 002 na entrega da 001": lambda: confirmar(db, neg, L["002"], ENT["001"], O["002"],
                                                                   agora=CONFIRMA_001),
            "detalhe da 001 pela 002": lambda: detalhar(db, neg, L["002"], ENT["001"], agora=CONFIRMA_001),
            "negocio X na entrega da 001": lambda: confirmar(db, c.neg_x.id, c.lx.id, ENT["001"], c.op_x.id,
                                                             agora=CONFIRMA_001),
            "negocio X com a loja da 001": lambda: confirmar(db, c.neg_x.id, L["001"], ENT["001"], c.op_x.id,
                                                             agora=CONFIRMA_001),
        }.items():
            try:
                acao()
                vazou.append(rotulo)
            except EntregaNaoEncontrada:
                pass
        ok_nada, txt = nada_gravado("001")()
        registrar("R3 entrega de outra loja ou negocio", not vazou and ok_nada,
                  f"4 nao encontradas; {txt}" if not vazou else f"aceitos: {vazou}")

        # ---- R1, R5: tudo certo na 001, antes da contagem do fechamento ----
        estoque_antes = db.execute(text(
            "SELECT loja_id, estoque_atual_calculado, quantidade_inventariada, atualizado_em FROM estoque_atual"
            " WHERE negocio_id = :n ORDER BY loja_id"), {"n": neg}).all()
        r = confirmar(db, neg, L["001"], ENT["001"], O["001"], agora=CONFIRMA_001)
        db.expire_all()
        e1 = db.get(RomaneioEntrega, ENT["001"])
        estoque_depois = db.execute(text(
            "SELECT loja_id, estoque_atual_calculado, quantidade_inventariada, atualizado_em FROM estoque_atual"
            " WHERE negocio_id = :n ORDER BY loja_id"), {"n": neg}).all()
        i1 = itens_entrega(ENT["001"])[0]
        registrar("R1 recebi tudo certo",
                  r.situacao.situacao == "recebida" and not r.situacao.com_diferenca
                  and i1.quantidade_recebida == DEC(8) and i1.motivo_divergencia is None
                  and e1.recebido_em == CONFIRMA_001 and e1.recebido_por_usuario_id == O["001"]
                  and estoque_antes == estoque_depois,
                  f"situacao {r.situacao.situacao}, recebida {i1.quantidade_recebida}, por {e1.recebido_por_usuario_id};"
                  f" estoque_atual {'intacto' if estoque_antes == estoque_depois else 'MUDOU'}")
        espera_erro("R5 confirmar de novo",
                    lambda: confirmar(db, neg, L["001"], ENT["001"], O["001"], agora=CONFIRMA_001),
                    RecebimentoNaoPermitido, "já foi confirmada")

        # ---- D2: contagem do fechamento de 03/11 ----
        contar(CONTAGEM_D2)
        r2 = necessidade(D2, D1)
        registrar("T3 recebida antes da contagem nao conta em dobro",
                  resumo(r2)["001"] == ("11", "0", "0"),
                  f"001 (necessidade, transito, recebido) {resumo(r2)['001']}; em dobro daria 3")

        g2 = gerar_ordem(db, neg, C, D2, g, D1, atualizar_previsao=None, agora=AGORA_D2)
        lin2 = linhas_ordem(g2.ordem_id)
        marcas = {k: [a for a in v.avisos if a in (AVISO_SEM_CONFIRMACAO, AVISO_CONFIRMADA_COM_ATRASO,
                                                   AVISO_RECEBIMENTO_NAO_CONFIRMADO)] for k, v in lin2.items()}
        numeros = {k: (str(v.quantidade_sugerida), v.componentes.get("transito_considerado")) for k, v in lin2.items()}
        registrar("T4b ainda no dia de entrega: sem marca e fora do transito",
                  all(m == [] for m in marcas.values())
                  and numeros == {k: ("11.000", "0") for k in ("001", "002", "003", "005")},
                  f"marcas {marcas}; (sugerida, transito) {numeros}")
        editar_linha(db, neg, C, lin2["003"].id, DEC(2), g, motivo="teste", agora=AGORA_D2)
        aprovar_ordem(db, neg, C, g2.ordem_id, g, agora=AGORA_D2 + timedelta(minutes=5))
        foto_d2 = {k: (v.quantidade_final, v.quantidade_sugerida, dict(v.componentes), list(v.avisos))
                   for k, v in linhas_ordem(g2.ordem_id).items()}

        # ---- T2, T8: 002 confirma no prazo, depois da contagem, com diferença ----
        antes = necessidade(D2, D1)["002"]
        r = confirmar(db, neg, L["002"], ENT["002"], O["002"],
                      {ITEM["002"]: DiferencaItem(DEC(3), "falta", "faltaram 2")}, agora=CONFIRMA_002)
        i2 = itens_entrega(ENT["002"])[0]
        motivo2 = i2.motivo_divergencia.value if i2.motivo_divergencia else None
        registrar("T2 confirmacao no prazo com diferenca",
                  r.situacao.situacao == "recebida" and r.situacao.com_diferenca
                  and i2.quantidade_recebida == DEC(3) and motivo2 == "falta"
                  and i2.observacao_divergencia == "faltaram 2",
                  f"situacao {r.situacao.situacao} com_diferenca={r.situacao.com_diferenca}, recebida "
                  f"{i2.quantidade_recebida} ({motivo2}: {i2.observacao_divergencia})")
        depois = necessidade(D2, D1)["002"]
        foto_d2_depois = {k: (v.quantidade_final, v.quantidade_sugerida, dict(v.componentes), list(v.avisos))
                          for k, v in linhas_ordem(g2.ordem_id).items()}
        status_d2 = db.get(OrdemProducao, g2.ordem_id).status
        registrar("T8 o numero muda e a ordem aprovada fica intacta",
                  (str(antes.necessidade), str(antes.recebido_apos_contagem)) == ("11", "0")
                  and (str(depois.necessidade), str(depois.recebido_apos_contagem)) == ("8", "3.000")
                  and foto_d2 == foto_d2_depois and status_d2 == StatusOrdemProducao.APROVADA,
                  f"002 antes {antes.necessidade} (recebido {antes.recebido_apos_contagem}) -> depois "
                  f"{depois.necessidade} (recebido {depois.recebido_apos_contagem}); ordem D2 "
                  f"{'intacta' if foto_d2 == foto_d2_depois else 'ALTERADA'}, {status_d2.value}, 002 final "
                  f"{foto_d2_depois['002'][0]}")

        # ---- D3: contagem do fechamento de 04/11 ----
        contar(CONTAGEM_D3)
        r3 = necessidade(D3, D2)
        registrar("T5 sem romaneio: transito pela final da ordem",
                  resumo(r3)["001"] == ("0", "11.000", "0") and resumo(r3)["003"] == ("9", "2.000", "0"),
                  f"001 {resumo(r3)['001']}, 003 {resumo(r3)['003']} (ordem D2: 11 e 2)")

        g3 = gerar_ordem(db, neg, C, D3, g, D2, atualizar_previsao=None, agora=AGORA_D3)
        lin3 = linhas_ordem(g3.ordem_id)
        detalhe_g = {e.loja_codigo: e.situacao for e in obter_romaneio(db, neg, C, rom_id, agora=AGORA_D3).entregas}
        lista_003 = [(x.situacao.situacao, x.situacao.pode_confirmar) for x in
                     listar_pendentes(db, neg, L["003"], agora=AGORA_D3)]

        def marca(linhas, k):
            return [a for a in linhas[k].avisos if a in (AVISO_SEM_CONFIRMACAO, AVISO_CONFIRMADA_COM_ATRASO,
                                                         AVISO_RECEBIMENTO_NAO_CONFIRMADO)]

        ok = (marca(lin3, "003") == [AVISO_SEM_CONFIRMACAO] and marca(lin3, "005") == [AVISO_SEM_CONFIRMACAO]
              and marca(lin3, "001") == [] and marca(lin3, "002") == []
              and lin3["003"].componentes.get("recebimento_presumido") == "4.000"
              and lin3["005"].componentes.get("recebimento_presumido") == "3.000"
              and lin3["003"].componentes.get("transito_considerado") == "2.000"
              and lin3["003"].quantidade_sugerida == DEC(9)
              and (detalhe_g["003"].situacao, detalhe_g["003"].pode_confirmar) == ("sem_confirmacao", True)
              and (detalhe_g["001"].situacao, detalhe_g["002"].situacao, detalhe_g["002"].com_diferenca)
              == ("recebida", "recebida", True)
              and lista_003 == [("sem_confirmacao", True)])
        registrar("T4 sem confirmacao na necessidade e na consulta do gestor", ok,
                  f"marcas 003 {marca(lin3, '003')} 005 {marca(lin3, '005')} 001 {marca(lin3, '001')}; presumida "
                  f"003 {lin3['003'].componentes.get('recebimento_presumido')} 005 "
                  f"{lin3['005'].componentes.get('recebimento_presumido')} (pela ordem: 6 e 4); 003 transito "
                  f"{lin3['003'].componentes.get('transito_considerado')} sugerida {lin3['003'].quantidade_sugerida};"
                  f" gestor 003 {detalhe_g['003'].situacao} (pode confirmar {detalhe_g['003'].pode_confirmar}), "
                  f"002 {detalhe_g['002'].situacao} com diferenca {detalhe_g['002'].com_diferenca}; app 003 {lista_003}")

        # ---- T6, T9: 003 confirma com atraso (22:00 local de 04/11 = 01:00 UTC de 05/11) ----
        marca_antes = marca(lin3, "003")
        antes = necessidade(D3, D2)["003"]
        # A necessidade de 04/11 também, com a contagem dela (21:00 de 03/11): a confirmação
        # atrasada (01:00 UTC de 05/11) é depois dessa contagem, mas a chegada é presumida em 03/11.
        contar(CONTAGEM_D2)
        antes_d2 = necessidade(D2, D1)["003"]
        contar(CONTAGEM_D3)
        r = confirmar(db, neg, L["003"], ENT["003"], O["003"],
                      {ITEM["003"]: DiferencaItem(DEC(2), "avaria")}, agora=CONFIRMA_003)
        i3 = itens_entrega(ENT["003"])[0]
        gestor_003 = {e.loja_codigo: e.situacao for e in
                      obter_romaneio(db, neg, C, rom_id, agora=CONFIRMA_003).entregas}["003"]
        motivo3 = i3.motivo_divergencia.value if i3.motivo_divergencia else None
        registrar("T6 confirmacao no dia seguinte aceita, com atraso",
                  r.situacao.situacao == "confirmada_com_atraso" and gestor_003.situacao == "confirmada_com_atraso"
                  and i3.quantidade_recebida == DEC(2) and motivo3 == "avaria",
                  f"app {r.situacao.situacao}, gestor {gestor_003.situacao}, recebida {i3.quantidade_recebida} "
                  f"({motivo3}) no lugar da presumida 4")
        depois = necessidade(D3, D2)["003"]
        contar(CONTAGEM_D2)
        depois_d2 = necessidade(D2, D1)["003"]
        contar(CONTAGEM_D3)
        g3b = gerar_ordem(db, neg, C, D3, g, D2, atualizar_previsao=None, agora=CONFIRMA_003)
        lin3b = linhas_ordem(g3b.ordem_id)
        registrar("T9 contagem depois da chegada: o numero nao muda, so a marca",
                  (str(antes.necessidade), str(antes.recebido_apos_contagem)) == ("9", "0")
                  and (str(depois.necessidade), str(depois.recebido_apos_contagem)) == ("9", "0")
                  and (str(antes_d2.necessidade), str(depois_d2.necessidade),
                       str(depois_d2.recebido_apos_contagem)) == ("11", "11", "0")
                  and lin3b["003"].quantidade_sugerida == DEC(9)
                  and marca(lin3b, "003") == [AVISO_CONFIRMADA_COM_ATRASO]
                  and marca(lin3b, "005") == [AVISO_SEM_CONFIRMACAO],
                  f"003 em 05/11 antes {antes.necessidade} depois {depois.necessidade}; em 04/11 antes "
                  f"{antes_d2.necessidade} depois {depois_d2.necessidade} (recebido {depois_d2.recebido_apos_contagem});"
                  f" marca 003 {marca_antes} -> {marca(lin3b, '003')}")

        # ---- T7: 005 tenta depois do fim do dia seguinte ----
        espera_erro("T7 confirmar depois do prazo",
                    lambda: confirmar(db, neg, L["005"], ENT["005"], O["005"], agora=TENTA_005),
                    RecebimentoNaoPermitido, "prazo para confirmar",
                    lambda: (lambda s, lst: (
                        (s.situacao, s.pode_confirmar) == ("sem_confirmacao", False) and lst == []
                        and nada_gravado("005")()[0],
                        f"005 {s.situacao} (pode confirmar {s.pode_confirmar}), lista do app {lst}"))(
                        {e.loja_codigo: e.situacao for e in
                         obter_romaneio(db, neg, C, rom_id, agora=TENTA_005).entregas}["005"],
                        listar_pendentes(db, neg, L["005"], agora=TENTA_005)))

        versao = db.get(OrdemProducao, g3b.ordem_id).versao_metodo
        registrar("V1 versao do metodo", versao == VERSAO_METODO_NECESSIDADE == "2026.10-n2", f"{versao}")
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste do recebimento e do trânsito (E5) ===")
            for r in resultados:
                print(r)
            falhas = [r for r in resultados if r.startswith(FAIL)]
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

    if len(resultados) < TOTAL_CASOS or any(r.startswith(FAIL) for r in resultados):
        sys.exit(1)


if __name__ == "__main__":
    main()
