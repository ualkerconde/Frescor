"""
Testa as regras de banco do romaneio (migration 0024, Fase 5 / E1):
`romaneios`, `romaneios_entregas`, `romaneios_itens` e a produção real em
`ordens_producao_itens`.

Casos:
  R1 romaneio inserido sem situação (por SQL) -> rascunho, gerado_em preenchido
  R2 segundo romaneio da mesma ordem -> barrado (uq_romaneio_ordem)
  R3 central diferente da central da ordem -> barrado (fk_romaneio_ordem_coerente)
  R4 data de entrega diferente da da ordem -> barrado (fk_romaneio_ordem_coerente)
  R5 romaneio do negócio X apontando ordem do negócio A -> barrado (fk_romaneio_ordem_coerente)
  R6 aprovado sem quem e quando -> barrado (ck_romaneio_aprovacao_coerente)
  R7 rascunho com aprovado_por -> barrado (ck_romaneio_aprovacao_coerente)
  R8 situação fora do enum -> recusada
  R9 apagar a ordem que tem romaneio -> barrado (fk_romaneio_ordem_coerente)
  E1 entrega pelo ORM grava o valor do enum (aguardando_saida)
  E2 mesma loja duas vezes no romaneio -> barrada (uq_entrega_romaneio_loja)
  E3 loja de outro negócio -> barrada (fk_entrega_negocio_loja)
  E4 entrega do negócio X apontando romaneio do negócio A -> barrada
     (fk_entrega_negocio_romaneio)
  E5 expedida sem expedido_em -> barrada (ck_entrega_situacao_coerente)
  E6 recebida sem recebido_por -> barrada (ck_entrega_situacao_coerente)
  E7 aguardando saída com recebido_em -> barrada (ck_entrega_situacao_coerente)
  E8 recebida com saída e recebimento completos -> aceita
  I1 item pelo ORM grava os valores dos enums (KG, a_mais)
  I2 mesmo produto duas vezes na entrega -> barrado (uq_romaneio_item_entrega_produto)
  I3 mesma linha da ordem em dois itens -> barrada (uq_romaneio_item_ordem_linha)
  I4 produto de outro negócio -> barrado (fk_romaneio_item_negocio_produto)
  I5 linha da ordem de outro negócio -> barrada (fk_romaneio_item_negocio_linha)
  I6 sugerida negativa -> barrada
  I7 final negativa -> barrada
  I8 recebida negativa -> barrada
  I9 recebida diferente da final sem motivo -> barrada (ck_romaneio_item_divergencia_coerente)
  I10 motivo sem recebida -> barrado (ck_romaneio_item_divergencia_coerente)
  I11 recebida igual à final sem motivo -> aceita
  P1 produção registrada sem quem/quando -> barrada (ck_ordem_item_producao_coerente)
  P2 produção com quantidade, quem e quando -> aceita
  C1 apagar o romaneio apaga entregas e itens (CASCADE), sem tocar outro
     romaneio nem a ordem

Cada erro confere o NOME da constraint. Saída ASCII ([OK]/[FALHA]), limpeza
no início e no fim, exit 1 se algo falhar.

Uso: python scripts/test_romaneios_modelo.py
"""

import sys
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import DataError, IntegrityError  # noqa: E402

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
from app.models.romaneio_item import MotivoDivergencia, RomaneioItem  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 31
PREFIXO_NEGOCIO_TESTE = "_Teste Romaneios Modelo"
D = date(2026, 11, 2)
ENTREGA = date(2026, 11, 3)
AGORA = datetime(2026, 11, 3, 9, 0)
DEC = Decimal

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def _constraint(e):
    diag = getattr(getattr(e, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", None)


def deve_inserir(nome, criar):
    db = SessionLocal()
    try:
        criar(db)
        db.commit()
        registrar(nome, True, "inserido")
    except Exception as e:
        db.rollback()
        registrar(nome, False, f"falhou inesperadamente -> {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        db.close()


def deve_barrar(nome, criar, constraint_esperada=None, excecoes=(IntegrityError,)):
    db = SessionLocal()
    try:
        criar(db)
        db.commit()
        registrar(nome, False, "foi aceito, mas deveria ter sido barrado")
    except excecoes as e:
        db.rollback()
        nome_c = _constraint(e)
        if constraint_esperada and nome_c != constraint_esperada:
            registrar(nome, False, f"barrado pela constraint errada: {nome_c} (esperada {constraint_esperada})")
        else:
            registrar(nome, True, f"barrado -> {type(e).__name__} ({nome_c or str(e.orig).splitlines()[0]})")
    except Exception as e:
        db.rollback()
        registrar(nome, False, f"erro inesperado -> {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        db.close()


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    # Entregas e itens saem em cascata com os romaneios; itens e linhas da
    # ordem, com as ordens.
    db.query(Romaneio).filter(Romaneio.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (RomaneioItem, RomaneioEntrega):  # sobras, se o CASCADE estiver quebrado
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(OrdemProducao).filter(OrdemProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
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


def main():
    _limpar_residuos()
    db = SessionLocal()
    negocio_ids = []
    try:
        run = uuid.uuid4().hex[:8]
        neg = Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} A", ativo=True)
        neg_x = Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} X", ativo=True)
        db.add_all([neg, neg_x])
        db.flush()
        negocio_ids = [neg.id, neg_x.id]
        central = CentralProducao(negocio_id=neg.id, nome="_Central A", ativa=True)
        central_2 = CentralProducao(negocio_id=neg.id, nome="_Central A2", ativa=True)
        central_x = CentralProducao(negocio_id=neg_x.id, nome="_Central X", ativa=True)
        db.add_all([central, central_2, central_x])
        db.flush()
        loja = Loja(negocio_id=neg.id, central_producao_id=central.id, nome="_Loja A1", horario_zeragem=time(6, 0))
        loja_2 = Loja(negocio_id=neg.id, central_producao_id=central.id, nome="_Loja A2", horario_zeragem=time(6, 0))
        loja_x = Loja(negocio_id=neg_x.id, central_producao_id=central_x.id, nome="_Loja X",
                      horario_zeragem=time(6, 0))
        prod = Produto(negocio_id=neg.id, nome="_Pao", unidade_medida=UnidadeMedida.KG, ativo=True)
        prod_2 = Produto(negocio_id=neg.id, nome="_Bolo", unidade_medida=UnidadeMedida.UN, ativo=True)
        prod_x = Produto(negocio_id=neg_x.id, nome="_Pao X", unidade_medida=UnidadeMedida.UN, ativo=True)
        gestor = Usuario(negocio_id=neg.id, nome="_Gestor", email=f"rom_g_{run}@teste.com",
                         senha_hash=hash_senha("x"), tem_acesso_app=False, tem_acesso_web=True,
                         tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=central.id)
        db.add_all([loja, loja_2, loja_x, prod, prod_2, prod_x, gestor])
        db.flush()
        operador = Usuario(negocio_id=neg.id, nome="_Operador", email=f"rom_o_{run}@teste.com",
                           senha_hash=hash_senha("x"), tem_acesso_app=True, tem_acesso_web=False,
                           tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=loja.id)
        db.add(operador)
        db.flush()

        # Ordem aprovada (A) com 2 itens e 2 linhas cada; ordem B (outro dia) para o C1; ordem X.
        def ordem(negocio, central_id, data):
            return OrdemProducao(negocio_id=negocio, central_producao_id=central_id, data_producao=data,
                                 data_entrega=data + (ENTREGA - D), versao_metodo="teste",
                                 status=StatusOrdemProducao.APROVADA, aprovado_em=AGORA,
                                 aprovado_por_usuario_id=gestor.id if negocio == neg.id else None)

        ordem_a = ordem(neg.id, central.id, D)
        ordem_b = ordem(neg.id, central.id, date(2026, 11, 9))
        db.add_all([ordem_a, ordem_b])
        db.flush()
        gestor_x = Usuario(negocio_id=neg_x.id, nome="_Gestor X", email=f"rom_gx_{run}@teste.com",
                           senha_hash=hash_senha("x"), tem_acesso_app=False, tem_acesso_web=True,
                           tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=central_x.id)
        db.add(gestor_x)
        db.flush()
        ordem_x = ordem(neg_x.id, central_x.id, D)
        ordem_x.aprovado_por_usuario_id = gestor_x.id
        db.add(ordem_x)
        db.flush()

        def item_ordem(negocio, ordem_id, produto_id, unidade):
            obj = OrdemProducaoItem(negocio_id=negocio, ordem_id=ordem_id, produto_id=produto_id,
                                    tipo_abastecimento=TipoAbastecimento.PRODUZIDO, unidade=unidade)
            db.add(obj)
            db.flush()
            return obj

        def linha_ordem(negocio, item_id, loja_id, final):
            obj = OrdemProducaoLinha(negocio_id=negocio, item_id=item_id, loja_id=loja_id,
                                     quantidade_sugerida=final, quantidade_final=final)
            db.add(obj)
            db.flush()
            return obj

        oi_pao = item_ordem(neg.id, ordem_a.id, prod.id, UnidadeMedida.KG)
        oi_bolo = item_ordem(neg.id, ordem_a.id, prod_2.id, UnidadeMedida.UN)
        ol_pao_1 = linha_ordem(neg.id, oi_pao.id, loja.id, DEC("10.5"))
        ol_pao_2 = linha_ordem(neg.id, oi_pao.id, loja_2.id, DEC("6.0"))
        ol_bolo_1 = linha_ordem(neg.id, oi_bolo.id, loja.id, DEC("4"))
        ol_bolo_2 = linha_ordem(neg.id, oi_bolo.id, loja_2.id, DEC("3"))
        oi_b = item_ordem(neg.id, ordem_b.id, prod.id, UnidadeMedida.KG)
        ol_b = linha_ordem(neg.id, oi_b.id, loja.id, DEC("8"))
        oi_x = item_ordem(neg_x.id, ordem_x.id, prod_x.id, UnidadeMedida.UN)
        ol_x = linha_ordem(neg_x.id, oi_x.id, loja_x.id, DEC("5"))
        db.commit()
        ids = dict(neg=neg.id, neg_x=neg_x.id, central=central.id, central_2=central_2.id, central_x=central_x.id,
                   loja=loja.id, loja_2=loja_2.id, loja_x=loja_x.id, prod=prod.id, prod_2=prod_2.id,
                   prod_x=prod_x.id, gestor=gestor.id, operador=operador.id, ordem_a=ordem_a.id,
                   ordem_b=ordem_b.id, ordem_x=ordem_x.id, oi_pao=oi_pao.id, oi_bolo=oi_bolo.id,
                   ol_pao_1=ol_pao_1.id, ol_pao_2=ol_pao_2.id, ol_bolo_1=ol_bolo_1.id, ol_bolo_2=ol_bolo_2.id,
                   ol_b=ol_b.id, ol_x=ol_x.id)

        def romaneio(ordem_id=None, negocio=None, central_id=None, entrega=ENTREGA, **kw):
            return Romaneio(negocio_id=negocio or ids["neg"], central_producao_id=central_id or ids["central"],
                            ordem_id=ordem_id or ids["ordem_a"], data_entrega=entrega, **kw)

        # ---- romaneios ----
        db.execute(text(
            "INSERT INTO romaneios (negocio_id, central_producao_id, ordem_id, data_entrega)"
            " VALUES (:neg, :central, :ordem, :e)"),
            {"neg": ids["neg"], "central": ids["central"], "ordem": ids["ordem_a"], "e": ENTREGA})
        db.commit()
        lido = db.execute(text("SELECT id, status::text, gerado_em FROM romaneios WHERE ordem_id = :o"),
                          {"o": ids["ordem_a"]}).one()
        ids["rom"] = lido[0]
        registrar("R1 padroes do banco no romaneio", lido[1] == "rascunho" and lido[2] is not None,
                  f"status = {lido[1]}, gerado_em preenchido = {lido[2] is not None}")
        deve_barrar("R2 segundo romaneio da mesma ordem", lambda s: s.add(romaneio()), "uq_romaneio_ordem")
        deve_barrar("R3 central diferente da da ordem",
                    lambda s: s.add(romaneio(ordem_id=ids["ordem_b"], central_id=ids["central_2"],
                                             entrega=date(2026, 11, 10))),
                    "fk_romaneio_ordem_coerente")
        deve_barrar("R4 entrega diferente da da ordem",
                    lambda s: s.add(romaneio(ordem_id=ids["ordem_b"], entrega=date(2026, 11, 11))),
                    "fk_romaneio_ordem_coerente")
        deve_barrar("R5 romaneio de outro negocio na ordem",
                    lambda s: s.add(romaneio(ordem_id=ids["ordem_b"], negocio=ids["neg_x"],
                                             central_id=ids["central_x"], entrega=date(2026, 11, 10))),
                    "fk_romaneio_ordem_coerente")
        deve_barrar("R6 aprovado sem quem e quando",
                    lambda s: s.add(romaneio(ordem_id=ids["ordem_b"], entrega=date(2026, 11, 10),
                                             status=StatusRomaneio.APROVADO)),
                    "ck_romaneio_aprovacao_coerente")
        deve_barrar("R7 rascunho com aprovado_por",
                    lambda s: s.add(romaneio(ordem_id=ids["ordem_b"], entrega=date(2026, 11, 10),
                                             aprovado_por_usuario_id=ids["gestor"])),
                    "ck_romaneio_aprovacao_coerente")
        deve_barrar("R8 situacao fora do enum", lambda s: s.execute(text(
            "INSERT INTO romaneios (negocio_id, central_producao_id, ordem_id, data_entrega, status)"
            " VALUES (:neg, :central, :ordem, '2026-11-10', 'expedido')"),
            {"neg": ids["neg"], "central": ids["central"], "ordem": ids["ordem_b"]}), excecoes=(DataError,))
        deve_barrar("R9 apagar ordem com romaneio", lambda s: s.execute(text(
            "DELETE FROM ordens_producao WHERE id = :o"), {"o": ids["ordem_a"]}), "fk_romaneio_ordem_coerente")

        # ---- entregas ----
        def entrega(loja_id=None, negocio=None, romaneio_id=None, **kw):
            return RomaneioEntrega(negocio_id=negocio or ids["neg"], romaneio_id=romaneio_id or ids["rom"],
                                   loja_id=loja_id or ids["loja"], **kw)

        obj = entrega()
        db.add(obj)
        db.commit()
        ids["ent"] = obj.id
        gravado = db.execute(text("SELECT situacao::text FROM romaneios_entregas WHERE id = :i"),
                             {"i": ids["ent"]}).scalar()
        registrar("E1 entrega grava o valor do enum", gravado == "aguardando_saida", f"situacao = {gravado}")
        deve_barrar("E2 mesma loja duas vezes", lambda s: s.add(entrega()), "uq_entrega_romaneio_loja")
        deve_barrar("E3 loja de outro negocio", lambda s: s.add(entrega(loja_id=ids["loja_x"])),
                    "fk_entrega_negocio_loja")
        deve_barrar("E4 entrega de outro negocio no romaneio",
                    lambda s: s.add(entrega(loja_id=ids["loja_x"], negocio=ids["neg_x"])),
                    "fk_entrega_negocio_romaneio")
        deve_barrar("E5 expedida sem expedido_em",
                    lambda s: s.add(entrega(loja_id=ids["loja_2"], situacao=SituacaoEntrega.EXPEDIDA,
                                            expedido_por_usuario_id=ids["gestor"])),
                    "ck_entrega_situacao_coerente")
        deve_barrar("E6 recebida sem recebido_por",
                    lambda s: s.add(entrega(loja_id=ids["loja_2"], situacao=SituacaoEntrega.RECEBIDA,
                                            expedido_em=AGORA, expedido_por_usuario_id=ids["gestor"],
                                            recebido_em=AGORA)),
                    "ck_entrega_situacao_coerente")
        deve_barrar("E7 aguardando saida com recebido_em",
                    lambda s: s.add(entrega(loja_id=ids["loja_2"], recebido_em=AGORA)),
                    "ck_entrega_situacao_coerente")
        obj = entrega(loja_id=ids["loja_2"], situacao=SituacaoEntrega.RECEBIDA, expedido_em=AGORA,
                      expedido_por_usuario_id=ids["gestor"], recebido_em=AGORA,
                      recebido_por_usuario_id=ids["operador"])
        deve_inserir("E8 recebida completa", lambda s: s.add(obj))
        ids["ent_2"] = db.execute(text("SELECT id FROM romaneios_entregas WHERE romaneio_id = :r AND loja_id = :l"),
                                  {"r": ids["rom"], "l": ids["loja_2"]}).scalar()

        # ---- itens ----
        def item(produto=None, linha=None, negocio=None, entrega_id=None, unidade=UnidadeMedida.KG, **kw):
            dados = dict(quantidade_sugerida=DEC("10.5"), quantidade_final=DEC("10.5"))
            dados.update(kw)
            return RomaneioItem(negocio_id=negocio or ids["neg"], entrega_id=entrega_id or ids["ent"],
                                produto_id=produto or ids["prod"], ordem_linha_id=linha or ids["ol_pao_1"],
                                unidade=unidade, **dados)

        obj = item(quantidade_final=DEC("10.0"), quantidade_recebida=DEC("11.0"),
                   motivo_divergencia=MotivoDivergencia.A_MAIS)
        db.add(obj)
        db.commit()
        gravado = db.execute(text(
            "SELECT unidade::text, motivo_divergencia::text FROM romaneios_itens WHERE id = :i"),
            {"i": obj.id}).one()
        registrar("I1 item grava os valores dos enums", tuple(gravado) == ("KG", "a_mais"), f"{tuple(gravado)}")
        deve_barrar("I2 mesmo produto duas vezes na entrega",
                    lambda s: s.add(item(linha=ids["ol_pao_2"])), "uq_romaneio_item_entrega_produto")
        deve_barrar("I3 mesma linha da ordem em dois itens",
                    lambda s: s.add(item(entrega_id=ids["ent_2"])), "uq_romaneio_item_ordem_linha")
        deve_barrar("I4 produto de outro negocio",
                    lambda s: s.add(item(produto=ids["prod_x"], linha=ids["ol_bolo_1"])),
                    "fk_romaneio_item_negocio_produto")
        deve_barrar("I5 linha da ordem de outro negocio",
                    lambda s: s.add(item(produto=ids["prod_2"], linha=ids["ol_x"])),
                    "fk_romaneio_item_negocio_linha")

        def item_bolo(**kw):
            return item(produto=ids["prod_2"], linha=ids["ol_bolo_1"], unidade=UnidadeMedida.UN, **kw)

        deve_barrar("I6 sugerida negativa", lambda s: s.add(item_bolo(quantidade_sugerida=DEC("-1"))),
                    "ck_romaneio_item_sugerida_nao_negativa")
        deve_barrar("I7 final negativa", lambda s: s.add(item_bolo(quantidade_final=DEC("-1"))),
                    "ck_romaneio_item_final_nao_negativa")
        deve_barrar("I8 recebida negativa",
                    lambda s: s.add(item_bolo(quantidade_recebida=DEC("-1"),
                                              motivo_divergencia=MotivoDivergencia.FALTA)),
                    "ck_romaneio_item_recebida_nao_negativa")
        deve_barrar("I9 recebida diferente sem motivo",
                    lambda s: s.add(item_bolo(quantidade_final=DEC("4"), quantidade_recebida=DEC("3"))),
                    "ck_romaneio_item_divergencia_coerente")
        deve_barrar("I10 motivo sem recebida",
                    lambda s: s.add(item_bolo(motivo_divergencia=MotivoDivergencia.AVARIA)),
                    "ck_romaneio_item_divergencia_coerente")
        deve_inserir("I11 recebida igual a final sem motivo", lambda s: s.add(item_bolo(
            quantidade_sugerida=DEC("4"), quantidade_final=DEC("4"), quantidade_recebida=DEC("4"))))

        # ---- produção real no item da ordem ----
        deve_barrar("P1 producao sem quem e quando", lambda s: s.execute(text(
            "UPDATE ordens_producao_itens SET quantidade_produzida = 15 WHERE id = :i"), {"i": ids["oi_pao"]}),
            "ck_ordem_item_producao_coerente")
        deve_inserir("P2 producao com quantidade, quem e quando", lambda s: s.execute(text(
            "UPDATE ordens_producao_itens SET quantidade_produzida = 15, producao_registrada_em = :t,"
            " producao_registrada_por_usuario_id = :u WHERE id = :i"),
            {"t": AGORA, "u": ids["gestor"], "i": ids["oi_pao"]}))

        # ---- cascata ----
        outro = romaneio(ordem_id=ids["ordem_b"], entrega=date(2026, 11, 10))
        db.add(outro)
        db.flush()
        ent_b = entrega(romaneio_id=outro.id)
        db.add(ent_b)
        db.flush()
        db.add(item(entrega_id=ent_b.id, linha=ids["ol_b"], quantidade_sugerida=DEC("8"),
                    quantidade_final=DEC("8")))
        db.commit()
        try:
            db.execute(text("DELETE FROM romaneios WHERE id = :r"), {"r": ids["rom"]})
            db.commit()
            sobras = db.execute(text(
                "SELECT (SELECT count(*) FROM romaneios_entregas WHERE romaneio_id = :r),"
                " (SELECT count(*) FROM romaneios_itens WHERE entrega_id IN (:e1, :e2)),"
                " (SELECT count(*) FROM romaneios_itens WHERE entrega_id = :eb),"
                " (SELECT count(*) FROM ordens_producao WHERE id = :o)"),
                {"r": ids["rom"], "e1": ids["ent"], "e2": ids["ent_2"], "eb": ent_b.id,
                 "o": ids["ordem_a"]}).one()
            registrar("C1 apagar o romaneio apaga entregas e itens", tuple(sobras) == (0, 0, 1, 1),
                      f"entregas, itens restantes = {tuple(sobras[:2])}; itens do outro romaneio = {sobras[2]};"
                      f" ordem existe = {sobras[3]}")
        except IntegrityError as e:
            db.rollback()
            registrar("C1 apagar o romaneio apaga entregas e itens", False, f"DELETE barrado: {_constraint(e)}")
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        try:
            print("\n=== Resultado do teste do romaneio (migration 0024) ===")
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
