"""
Testa o `distribuicao_service` (Fase 5 / E4), com banco: produção real
(D69), romaneio (gerar, ajustar, aprovar, apagar; D68, D70, D71) e saída
(D76), com as travas e o escopo do gestor.

Negócio de teste isolado (apagado no fim). As ordens aprovadas são montadas
direto no banco (a geração da ordem é testada na Fase 4).
Central A (prazo 1): lojas L1 (código 001), L2 (002), L3 (003). Central B:
loja LB. Negócio X: outro cliente.

Ordem OA (A, produção 02/11, entrega 03/11, aprovada):
  PA (UN, produzido)   finais 6 / 4 / 2      (sugeridas 2 / 4 / 6: o gestor mudou a ordem; pela
                       sugerida o rateio daria 2/3/5, e não 5/3/2)
  PB (KG, produzido)   finais 10,5 / 6,0 / 3,5
  PC (UN, distribuído) finais 4 / 0 / 3
Produção registrada: PA 10, PB 15,0, PC 9.
Conta à mão (D70, a mesma do E3): PA 10 x 6/12 = 5; x 4/12 = 3,33; x 2/12 =
1,67 -> 5/3/1 + 1 para o maior resto -> 5/3/2. PB 15 x 10,5/20 = 7,875 ->
7,8 (+0,1) = 7,9; 4,5; 2,625 -> 2,6. PC: 9 >= 7, sem rateio: 4 / (fora) / 3,
sobra 2. Entregas: L1 (PA 5, PB 7,9, PC 4), L2 (PA 3, PB 4,5), L3 (PA 2,
PB 2,6, PC 3) = 3 entregas, 8 itens.
Ordem OR (A, 04/11, rascunho). Ordem O2 (A, 05/11, aprovada; PA 3/3 nas
L1/L2). Ordem OB (B, aprovada; PA 5 na LB). Ordem OX (negócio X).

Casos:
  G0 gerar sem a produção registrada -> recusado, citando os 3 produtos
  P1 registrar a produção da OA -> gravada com quem e quando
  P2 produção inválida (UN fracionada, negativa, KG com 4 casas, item de
     outra ordem) -> recusada, nada muda
  P3 produção de ordem em rascunho -> não permitido
  P4 produção de ordem de outra central / de outro negócio -> não encontrada
  G1 gerar o romaneio da OA: rascunho, central e entrega da ordem, 3
     entregas, 8 itens com os números acima, sugerida = final, escassez em
     PA e PB, sobra em PC, L2 sem PC (final 0 fica fora)
  G2 gerar de ordem em rascunho -> não permitido; de outra central -> não
     encontrada
  E1 ajustar a L1/PA para 6 com motivo: final 6, sugerida continua 5
  E2 ajustes inválidos (UN fracionada, negativa, 4 casas, motivo > 255) ->
     recusados, a final continua 6
  E3 ajustar item do romaneio de outra central, e item da OA pelo romaneio
     da O2 -> não encontrado, nada gravado
  P5 corrigir a produção com o romaneio em rascunho -> aceita, avisa que o
     rascunho ficou desatualizado, e o rascunho NÃO é refeito sozinho
  G3 gerar de novo: substitui o rascunho (id novo, um romaneio só, o ajuste
     da L1/PA se perde: volta a 5)
  A1 aprovar com Σ final do PA (11) acima do produzido (10) -> recusado,
     citando o produto; continua rascunho
  A2 voltar a L1/PA para 5 e aprovar -> aprovado, com quem e quando
  A3 romaneio aprovado: ajustar, gerar de novo, apagar e mudar a produção ->
     não permitido; itens e produção intactos
  L1 aprovar o romaneio da O2 com a L2 fora da central -> recusado, citando a
     loja; continua rascunho
  S1 saída de romaneio em rascunho -> não permitido
  S2 saída da L1 -> expedida, com quem e quando; L2 e L3 aguardando
  S3 saída da L1 de novo -> não permitido; a hora da 1ª saída fica
  S4 saída da L2 junto com uma entrega de outro romaneio -> não encontrada,
     e a L2 continua aguardando (tudo ou nada)
  S5 saída de "todas as que faltam" -> L2 e L3 expedidas; L1 mantém a hora
  S6 "todas as que faltam" sem nenhuma faltando -> não permitido
  D1 apagar o rascunho da O2 -> some com entregas e itens; a ordem fica
  X1 gestor da A no romaneio da B e gestor do negócio X no da A (aprovar,
     apagar, saída) -> não encontrado, nada muda

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_distribuicao_service.py
"""

import sys
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.security import hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.ordem_producao import OrdemProducao, StatusOrdemProducao  # noqa: E402
from app.models.ordem_producao_item import OrdemProducaoItem  # noqa: E402
from app.models.ordem_producao_linha import OrdemProducaoLinha  # noqa: E402
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida  # noqa: E402
from app.models.romaneio import Romaneio, StatusRomaneio  # noqa: E402
from app.models.romaneio_entrega import RomaneioEntrega, SituacaoEntrega  # noqa: E402
from app.models.romaneio_item import RomaneioItem  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402
from app.services.distribuicao_service import (  # noqa: E402
    DistribuicaoInvalida,
    NaoEncontrado,
    OperacaoNaoPermitida,
    apagar_romaneio,
    aprovar_romaneio,
    editar_item,
    gerar_romaneio,
    registrar_producao,
    registrar_saida,
)

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 24
PREFIXO_NEGOCIO_TESTE = "_Teste Distribuicao"
D = date(2026, 11, 2)
T0 = datetime(2026, 11, 2, 20, 0)
T1 = datetime(2026, 11, 3, 5, 0)
T2 = datetime(2026, 11, 3, 6, 0)
DEC = Decimal

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def espera_erro(nome, acao, tipo, contem=None, depois=None):
    """Roda `acao`; passa se levantar `tipo` (com `contem` na mensagem) e `depois()` devolver True."""
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
    db.query(Romaneio).filter(Romaneio.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (RomaneioItem, RomaneioEntrega):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(OrdemProducao).filter(OrdemProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (OrdemProducaoLinha, OrdemProducaoItem):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
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
        self.a = self._add(CentralProducao(negocio_id=self.neg.id, nome="_A", ativa=True, prazo_entrega_dias=1))
        self.b = self._add(CentralProducao(negocio_id=self.neg.id, nome="_B", ativa=True))
        self.cx = self._add(CentralProducao(negocio_id=self.neg_x.id, nome="_X", ativa=True))
        self.l1 = self._loja(self.neg, self.a, "001")
        self.l2 = self._loja(self.neg, self.a, "002")
        self.l3 = self._loja(self.neg, self.a, "003")
        self.lb = self._loja(self.neg, self.b, "B01")
        self.lx = self._loja(self.neg_x, self.cx, "X01")
        self.ga = self._gestor(self.neg, self.a, f"tds_a_{run}")
        self.gb = self._gestor(self.neg, self.b, f"tds_b_{run}")
        self.gx = self._gestor(self.neg_x, self.cx, f"tds_x_{run}")
        self.pa = self._produto(self.neg, "PA", UnidadeMedida.UN)
        self.pb = self._produto(self.neg, "PB", UnidadeMedida.KG)
        self.pc = self._produto(self.neg, "PC", UnidadeMedida.UN, TipoAbastecimento.DISTRIBUIDO)
        self.px = self._produto(self.neg_x, "PX", UnidadeMedida.UN)
        self.oa = self._ordem(self.neg, self.a, D, date(2026, 11, 3), self.ga, {
            self.pa: [(self.l1, 2, 6), (self.l2, 4, 4), (self.l3, 6, 2)],
            self.pb: [(self.l1, "10.5", "10.5"), (self.l2, "6.0", "6.0"), (self.l3, "3.5", "3.5")],
            self.pc: [(self.l1, 4, 4), (self.l2, 1, 0), (self.l3, 3, 3)],
        })
        self.o_r = self._ordem(self.neg, self.a, date(2026, 11, 4), date(2026, 11, 5), None,
                               {self.pa: [(self.l1, 5, 5)]})
        self.o2 = self._ordem(self.neg, self.a, date(2026, 11, 5), date(2026, 11, 6), self.ga,
                              {self.pa: [(self.l1, 3, 3), (self.l2, 3, 3)]})
        self.ob = self._ordem(self.neg, self.b, D, D, self.gb, {self.pa: [(self.lb, 5, 5)]})
        self.ox = self._ordem(self.neg_x, self.cx, D, D, self.gx, {self.px: [(self.lx, 5, 5)]})
        db.commit()

    def _add(self, obj):
        self.db.add(obj)
        self.db.flush()
        return obj

    def _loja(self, neg, central, codigo):
        return self._add(Loja(negocio_id=neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}",
                              codigo=codigo, horario_zeragem=time(6, 0), ativo=True))

    def _gestor(self, neg, central, nome):
        return self._add(Usuario(
            negocio_id=neg.id, nome=f"_Gestor {nome}", email=f"{nome}@teste.com", senha_hash=hash_senha("x"),
            tem_acesso_app=False, tem_acesso_web=True, tipo_usuario=TipoUsuario.GESTOR_CENTRAL,
            central_producao_id=central.id))

    def _produto(self, neg, codigo, unidade, tipo=TipoAbastecimento.PRODUZIDO):
        return self._add(Produto(negocio_id=neg.id, nome=f"_Produto {codigo}", codigo=codigo, unidade_medida=unidade,
                                 ativo=True, tipo_abastecimento=tipo))

    def _ordem(self, neg, central, producao, entrega, aprovador, itens):
        ordem = self._add(OrdemProducao(
            negocio_id=neg.id, central_producao_id=central.id, data_producao=producao, data_entrega=entrega,
            versao_metodo="teste", gerado_em=T0,
            status=StatusOrdemProducao.APROVADA if aprovador else StatusOrdemProducao.RASCUNHO,
            aprovado_em=T0 if aprovador else None, aprovado_por_usuario_id=aprovador.id if aprovador else None))
        ordem.itens = {}
        for produto, linhas in itens.items():
            item = self._add(OrdemProducaoItem(negocio_id=neg.id, ordem_id=ordem.id, produto_id=produto.id,
                                               tipo_abastecimento=produto.tipo_abastecimento,
                                               unidade=produto.unidade_medida))
            ordem.itens[produto.codigo] = item
            for loja, sugerida, final in linhas:
                self._add(OrdemProducaoLinha(negocio_id=neg.id, item_id=item.id, loja_id=loja.id,
                                             quantidade_sugerida=DEC(str(sugerida)), quantidade_final=DEC(str(final))))
        return ordem


def main():
    _limpar_residuos()
    db = SessionLocal()
    negocio_ids = []
    try:
        c = Cenario(db)
        negocio_ids = [c.neg.id, c.neg_x.id]
        neg, A = c.neg.id, c.a.id
        oa_itens = {k: v.id for k, v in c.oa.itens.items()}

        def producao_oa():
            db.expire_all()
            return {k: db.get(OrdemProducaoItem, i).quantidade_produzida for k, i in oa_itens.items()}

        def romaneio_de(ordem):
            db.expire_all()
            return db.query(Romaneio).filter(Romaneio.ordem_id == ordem.id).one_or_none()

        def itens_de(romaneio_id):
            """{(codigo da loja, codigo do produto): (sugerida, final, item)}"""
            db.expire_all()
            linhas = (
                db.query(RomaneioItem, Loja.codigo, Produto.codigo)
                .join(RomaneioEntrega, RomaneioEntrega.id == RomaneioItem.entrega_id)
                .join(Loja, Loja.id == RomaneioEntrega.loja_id)
                .join(Produto, Produto.id == RomaneioItem.produto_id)
                .filter(RomaneioEntrega.romaneio_id == romaneio_id)
            )
            return {(lc, pc): (str(i.quantidade_sugerida), str(i.quantidade_final), i) for i, lc, pc in linhas}

        def entregas_de(romaneio_id):
            db.expire_all()
            return {lc: e for e, lc in db.query(RomaneioEntrega, Loja.codigo)
                    .join(Loja, Loja.id == RomaneioEntrega.loja_id)
                    .filter(RomaneioEntrega.romaneio_id == romaneio_id)}

        # ---- produção real ----
        espera_erro("G0 gerar sem producao registrada",
                    lambda: gerar_romaneio(db, neg, A, c.oa.id, c.ga.id), DistribuicaoInvalida, "3 produto(s)",
                    lambda: (romaneio_de(c.oa) is None, "nenhum romaneio gravado"))
        r = registrar_producao(db, neg, A, c.oa.id, {oa_itens["PA"]: DEC(10), oa_itens["PB"]: DEC("15.0"),
                                                     oa_itens["PC"]: DEC(9)}, c.ga.id, agora=T0)
        db.expire_all()
        pa = db.get(OrdemProducaoItem, oa_itens["PA"])
        prod = producao_oa()
        registrar("P1 producao registrada",
                  prod == {"PA": DEC("10.000"), "PB": DEC("15.000"), "PC": DEC("9.000")}
                  and pa.producao_registrada_em == T0 and pa.producao_registrada_por_usuario_id == c.ga.id
                  and r.itens_registrados == 3 and not r.romaneio_desatualizado,
                  f"{ {k: str(v) for k, v in prod.items()} }, por {pa.producao_registrada_por_usuario_id}")

        invalidas = {
            "UN fracionada": {oa_itens["PA"]: DEC("10.5")},
            "negativa": {oa_itens["PB"]: DEC("-1")},
            "KG com 4 casas": {oa_itens["PB"]: DEC("15.0001")},
        }
        aceitas = []
        for rotulo, q in invalidas.items():
            try:
                registrar_producao(db, neg, A, c.oa.id, q, c.ga.id)
                aceitas.append(rotulo)
            except DistribuicaoInvalida:
                pass
        try:
            registrar_producao(db, neg, A, c.oa.id, {c.o_r.itens["PA"].id: DEC(1)}, c.ga.id)
            aceitas.append("item de outra ordem")
        except NaoEncontrado:
            pass
        intacta = producao_oa() == prod
        registrar("P2 producao invalida recusada", not aceitas and intacta,
                  f"4 recusadas, producao intacta = {intacta}" if not aceitas else f"aceitas: {aceitas}")
        espera_erro("P3 producao de ordem em rascunho",
                    lambda: registrar_producao(db, neg, A, c.o_r.id, {c.o_r.itens["PA"].id: DEC(5)}, c.ga.id),
                    OperacaoNaoPermitida, "não foi aprovada")
        fora = []
        for rotulo, args in {"outra central": (neg, A, c.ob.id, {c.ob.itens["PA"].id: DEC(5)}),
                             "outro negocio": (neg, A, c.ox.id, {c.ox.itens["PX"].id: DEC(5)})}.items():
            try:
                registrar_producao(db, *args, c.ga.id)
                fora.append(rotulo)
            except NaoEncontrado:
                pass
        registrar("P4 producao fora do escopo", not fora, "2 nao encontradas" if not fora else f"aceitas: {fora}")

        # ---- romaneio ----
        g = gerar_romaneio(db, neg, A, c.oa.id, c.ga.id, agora=T0)
        rom = romaneio_de(c.oa)
        itens = itens_de(rom.id)
        valores = {k: v[1] for k, v in itens.items()}
        esperado = {("001", "PA"): "5.000", ("002", "PA"): "3.000", ("003", "PA"): "2.000",
                    ("001", "PB"): "7.900", ("002", "PB"): "4.500", ("003", "PB"): "2.600",
                    ("001", "PC"): "4.000", ("003", "PC"): "3.000"}
        ok = (rom.status == StatusRomaneio.RASCUNHO and rom.central_producao_id == A
              and rom.data_entrega == date(2026, 11, 3) and g.entregas == 3 and g.itens == 8
              and valores == esperado and all(v[0] == v[1] for v in itens.values())
              and set(g.produtos_com_escassez) == {c.pa.id, c.pb.id} and g.produtos_com_sobra == (c.pc.id,)
              and not g.substituiu_rascunho)
        registrar("G1 romaneio gerado com o rateio", ok,
                  f"{g.entregas} entregas, {g.itens} itens; L1 PA {valores.get(('001', 'PA'))}, "
                  f"L3 PA {valores.get(('003', 'PA'))}, L1 PB {valores.get(('001', 'PB'))}; "
                  f"L2 PC {'ausente' if ('002', 'PC') not in valores else 'PRESENTE'}"
                  + ("" if ok else f" (obtido {valores})"))

        problemas = []
        try:
            gerar_romaneio(db, neg, A, c.o_r.id, c.ga.id)
            problemas.append("ordem em rascunho aceita")
        except OperacaoNaoPermitida:
            pass
        try:
            gerar_romaneio(db, neg, A, c.ob.id, c.ga.id)
            problemas.append("ordem de outra central aceita")
        except NaoEncontrado:
            pass
        registrar("G2 gerar de ordem em rascunho ou de outra central", not problemas,
                  "recusados" if not problemas else str(problemas))

        item_l1_pa = itens[("001", "PA")][2].id
        editar_item(db, neg, A, rom.id, item_l1_pa, DEC(6), c.ga.id, motivo="cliente grande", agora=T0)
        sug, fin, it = itens_de(rom.id)[("001", "PA")]
        registrar("E1 ajuste da final", (sug, fin, it.motivo_edicao, it.editado_por_usuario_id)
                  == ("5.000", "6.000", "cliente grande", c.ga.id), f"sugerida {sug}, final {fin}, {it.motivo_edicao}")

        item_l1_pb = itens[("001", "PB")][2].id
        aceitas = []
        for rotulo, item_id, q, motivo in [("UN fracionada", item_l1_pa, DEC("6.5"), None),
                                           ("negativa", item_l1_pa, DEC(-1), None),
                                           ("4 casas", item_l1_pb, DEC("7.9001"), None),
                                           ("motivo longo", item_l1_pa, DEC(6), "x" * 256)]:
            try:
                editar_item(db, neg, A, rom.id, item_id, q, c.ga.id, motivo=motivo)
                aceitas.append(rotulo)
            except DistribuicaoInvalida:
                pass
        final_l1 = itens_de(rom.id)[("001", "PA")][1]
        registrar("E2 ajustes invalidos recusados", not aceitas and final_l1 == "6.000",
                  f"4 recusados, final {final_l1}" if not aceitas else f"aceitos: {aceitas}")

        # Romaneios da O2 e da OB, para escopo e outras travas.
        registrar_producao(db, neg, A, c.o2.id, {c.o2.itens["PA"].id: DEC(6)}, c.ga.id)
        g2 = gerar_romaneio(db, neg, A, c.o2.id, c.ga.id)
        registrar_producao(db, neg, c.b.id, c.ob.id, {c.ob.itens["PA"].id: DEC(5)}, c.gb.id)
        gb = gerar_romaneio(db, neg, c.b.id, c.ob.id, c.gb.id)
        item_b = next(iter(itens_de(gb.romaneio_id).values()))[2].id
        vazou = []
        for rotulo, args in {"item de outra central": (gb.romaneio_id, item_b),
                             "item da OA pelo romaneio da O2": (g2.romaneio_id, item_l1_pa)}.items():
            try:
                editar_item(db, neg, A, *args, DEC(1), c.ga.id)
                vazou.append(rotulo)
            except NaoEncontrado:
                pass
        intactos = (itens_de(gb.romaneio_id)[("B01", "PA")][1] == "5.000"
                    and itens_de(rom.id)[("001", "PA")][1] == "6.000")
        registrar("E3 ajuste fora do escopo", not vazou and intactos,
                  f"2 nao encontrados, nada gravado = {intactos}" if not vazou else f"aceitos: {vazou}")

        r5 = registrar_producao(db, neg, A, c.oa.id, {oa_itens["PA"]: DEC(10)}, c.ga.id)
        mesmo = romaneio_de(c.oa)
        registrar("P5 producao com rascunho avisa e nao refaz",
                  r5.romaneio_desatualizado and mesmo.id == rom.id and itens_de(rom.id)[("001", "PA")][1] == "6.000",
                  f"desatualizado={r5.romaneio_desatualizado}; mesmo rascunho={mesmo.id == rom.id}")

        g3 = gerar_romaneio(db, neg, A, c.oa.id, c.ga.id)
        novo = romaneio_de(c.oa)
        quantos = db.query(Romaneio).filter(Romaneio.ordem_id == c.oa.id).count()
        final_novo = itens_de(novo.id)[("001", "PA")][1]
        registrar("G3 gerar de novo substitui o rascunho",
                  g3.substituiu_rascunho and novo.id != rom.id and quantos == 1 and final_novo == "5.000",
                  f"id {rom.id} -> {novo.id}, romaneios da ordem {quantos}, L1 PA volta a {final_novo}")
        rom = novo
        itens = itens_de(rom.id)
        item_l1_pa = itens[("001", "PA")][2].id

        # ---- aprovação ----
        editar_item(db, neg, A, rom.id, item_l1_pa, DEC(6), c.ga.id)
        espera_erro("A1 aprovar acima do produzido",
                    lambda: aprovar_romaneio(db, neg, A, rom.id, c.ga.id), DistribuicaoInvalida, "_Produto PA",
                    lambda: (romaneio_de(c.oa).status == StatusRomaneio.RASCUNHO, "continua rascunho"))
        editar_item(db, neg, A, rom.id, item_l1_pa, DEC(5), c.ga.id)
        aprovar_romaneio(db, neg, A, rom.id, c.ga.id, agora=T1)
        aprovado = romaneio_de(c.oa)
        registrar("A2 aprovar", aprovado.status == StatusRomaneio.APROVADO and aprovado.aprovado_em == T1
                  and aprovado.aprovado_por_usuario_id == c.ga.id, f"{aprovado.status.value} em {aprovado.aprovado_em}")

        antes_itens = {k: v[:2] for k, v in itens_de(rom.id).items()}
        antes_prod = producao_oa()
        aceitas = []
        for rotulo, acao in {
            "ajustar": lambda: editar_item(db, neg, A, rom.id, item_l1_pa, DEC(1), c.ga.id),
            "gerar de novo": lambda: gerar_romaneio(db, neg, A, c.oa.id, c.ga.id),
            "apagar": lambda: apagar_romaneio(db, neg, A, rom.id),
            "mudar a producao": lambda: registrar_producao(db, neg, A, c.oa.id, {oa_itens["PA"]: DEC(3)}, c.ga.id),
        }.items():
            try:
                acao()
                aceitas.append(rotulo)
            except OperacaoNaoPermitida:
                pass
            except Exception as e:  # ex.: o romaneio sumiu numa ação anterior
                aceitas.append(f"{rotulo} ({type(e).__name__})")
        atual = romaneio_de(c.oa)
        intacto = (atual is not None and atual.id == rom.id and atual.status == StatusRomaneio.APROVADO
                   and {k: v[:2] for k, v in itens_de(rom.id).items()} == antes_itens and producao_oa() == antes_prod)
        registrar("A3 romaneio aprovado travado", not aceitas and intacto,
                  f"4 acoes recusadas, romaneio e producao intactos = {intacto}" if not aceitas
                  else f"aceitas: {aceitas}; intacto = {intacto}")

        c.l2.central_producao_id = c.b.id
        db.commit()
        espera_erro("L1 aprovar com loja fora da central",
                    lambda: aprovar_romaneio(db, neg, A, g2.romaneio_id, c.ga.id), DistribuicaoInvalida, "_Loja 002",
                    lambda: (db.get(Romaneio, g2.romaneio_id).status == StatusRomaneio.RASCUNHO, "continua rascunho"))
        db.expire_all()
        c.l2.central_producao_id = A
        db.commit()

        # ---- saída ----
        espera_erro("S1 saida de romaneio em rascunho",
                    lambda: registrar_saida(db, neg, A, g2.romaneio_id, c.ga.id), OperacaoNaoPermitida, "Aprove")
        ent = entregas_de(rom.id)
        registrar_saida(db, neg, A, rom.id, c.ga.id, [ent["001"].id], agora=T1)
        ent = entregas_de(rom.id)
        registrar("S2 saida de uma loja",
                  ent["001"].situacao == SituacaoEntrega.EXPEDIDA and ent["001"].expedido_em == T1
                  and ent["001"].expedido_por_usuario_id == c.ga.id
                  and {ent["002"].situacao, ent["003"].situacao} == {SituacaoEntrega.AGUARDANDO_SAIDA},
                  f"001 {ent['001'].situacao.value}; 002 {ent['002'].situacao.value}; 003 {ent['003'].situacao.value}")
        espera_erro("S3 saida repetida", lambda: registrar_saida(db, neg, A, rom.id, c.ga.id, [ent["001"].id], agora=T2),
                    OperacaoNaoPermitida, "_Loja 001",
                    lambda: (entregas_de(rom.id)["001"].expedido_em == T1, "hora da 1a saida mantida"))
        entrega_b = next(iter(entregas_de(gb.romaneio_id).values()))
        espera_erro("S4 saida com entrega de outro romaneio (tudo ou nada)",
                    lambda: registrar_saida(db, neg, A, rom.id, c.ga.id, [ent["002"].id, entrega_b.id]),
                    NaoEncontrado, None,
                    lambda: (entregas_de(rom.id)["002"].situacao == SituacaoEntrega.AGUARDANDO_SAIDA,
                             "L2 continua aguardando"))
        saiu = registrar_saida(db, neg, A, rom.id, c.ga.id, agora=T2)
        ent = entregas_de(rom.id)
        registrar("S5 saida de todas as que faltam",
                  len(saiu) == 2 and all(e.situacao == SituacaoEntrega.EXPEDIDA for e in ent.values())
                  and ent["001"].expedido_em == T1 and ent["002"].expedido_em == T2,
                  f"{len(saiu)} saidas; 001 em {ent['001'].expedido_em:%H:%M}, 002 em {ent['002'].expedido_em:%H:%M}")
        espera_erro("S6 todas as que faltam sem nenhuma faltando",
                    lambda: registrar_saida(db, neg, A, rom.id, c.ga.id), OperacaoNaoPermitida, "já saíram")

        # ---- apagar e escopo ----
        apagar_romaneio(db, neg, A, g2.romaneio_id)
        db.expire_all()
        sobras = db.query(RomaneioEntrega).filter(RomaneioEntrega.romaneio_id == g2.romaneio_id).count()
        registrar("D1 apagar rascunho", romaneio_de(c.o2) is None and sobras == 0
                  and db.get(OrdemProducao, c.o2.id) is not None, f"romaneio apagado, entregas {sobras}, ordem existe")

        vazou = []
        for rotulo, acao in {
            "aprovar B pela A": lambda: aprovar_romaneio(db, neg, A, gb.romaneio_id, c.ga.id),
            "apagar B pela A": lambda: apagar_romaneio(db, neg, A, gb.romaneio_id),
            "saida B pela A": lambda: registrar_saida(db, neg, A, gb.romaneio_id, c.ga.id),
            "aprovar A pelo X": lambda: aprovar_romaneio(db, c.neg_x.id, c.cx.id, rom.id, c.gx.id),
            "saida A pelo X": lambda: registrar_saida(db, c.neg_x.id, c.cx.id, rom.id, c.gx.id),
        }.items():
            try:
                acao()
                vazou.append(rotulo)
            except NaoEncontrado:
                pass
        rb = db.get(Romaneio, gb.romaneio_id)
        db.refresh(rb)
        registrar("X1 fora do escopo", not vazou and rb.status == StatusRomaneio.RASCUNHO,
                  f"5 nao encontrados, romaneio da B intacto" if not vazou else f"aceitos: {vazou}")
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste do distribuicao_service (E4) ===")
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
