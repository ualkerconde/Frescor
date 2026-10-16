"""
Testa as regras de banco das ordens de produção (migration 0022, Fase 4 /
N5): `ordens_producao`, `ordens_producao_itens` e `ordens_producao_linhas`.

Casos:
  O1 ordem inserida sem tipo e sem situação (por SQL) -> programada e rascunho
  O2 segunda ordem programada na mesma central e data -> barrada
     (uq_ordem_programada_central_data)
  O3 duas emergenciais na mesma central e data da programada -> aceitas
  O4 aprovada sem aprovado_em / aprovado_por -> barrada (ck_ordem_aprovacao_coerente)
  O5 rascunho com aprovado_por -> barrada (ck_ordem_aprovacao_coerente)
  O6 aprovada com quem e quando -> aceita
  O7 entrega antes da produção -> barrada (ck_ordem_entrega_depois_da_producao)
  O8 central de outro negócio -> barrada (fk_ordem_negocio_central)
  O9 situação fora do enum -> recusada
  I1 item pelo ORM grava os valores dos enums (produzido, KG)
  I2 mesmo produto duas vezes na ordem -> barrado (uq_ordem_item_produto)
  I3 produto de outro negócio -> barrado (fk_ordem_item_negocio_produto)
  I4 item do negócio X apontando ordem do negócio A -> barrado
     (fk_ordem_item_negocio_ordem)
  I5 quantidade produzida negativa -> barrada
  L1 linha com componentes e avisos (JSON) -> gravados e lidos iguais
  L2 mesma loja duas vezes no item -> barrada (uq_ordem_linha_item_loja)
  L3 loja de outro negócio -> barrada (fk_ordem_linha_negocio_loja)
  L4 sugerida negativa -> barrada
  L5 final negativa -> barrada
  L6 recebida negativa -> barrada
  L7 sugerida e final NULL (por SQL) -> aceita, componentes {} e avisos []
  C1 apagar a ordem apaga os itens e as linhas (CASCADE), sem tocar outra ordem

Cada erro confere o NOME da constraint. Saída ASCII ([OK]/[FALHA]), limpeza
no início e no fim, exit 1 se algo falhar.

Uso: python scripts/test_ordens_modelo.py
"""

import json
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
from app.models.ordem_producao import OrdemProducao, StatusOrdemProducao, TipoOrdemProducao  # noqa: E402
from app.models.ordem_producao_item import OrdemProducaoItem  # noqa: E402
from app.models.ordem_producao_linha import OrdemProducaoLinha  # noqa: E402
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 22
PREFIXO_NEGOCIO_TESTE = "_Teste Ordens Modelo"
D = date(2026, 11, 2)
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
    # As linhas e os itens saem em cascata com as ordens.
    db.query(OrdemProducao).filter(OrdemProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (OrdemProducaoLinha, OrdemProducaoItem):  # sobras, se o CASCADE estiver quebrado
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
        central_x = CentralProducao(negocio_id=neg_x.id, nome="_Central X", ativa=True)
        db.add_all([central, central_x])
        db.flush()
        loja = Loja(negocio_id=neg.id, central_producao_id=central.id, nome="_Loja A", horario_zeragem=time(6, 0))
        loja_x = Loja(negocio_id=neg_x.id, central_producao_id=central_x.id, nome="_Loja X",
                      horario_zeragem=time(6, 0))
        prod = Produto(negocio_id=neg.id, nome="_Pao", unidade_medida=UnidadeMedida.KG, ativo=True)
        prod_2 = Produto(negocio_id=neg.id, nome="_Bolo", unidade_medida=UnidadeMedida.UN, ativo=True)
        prod_x = Produto(negocio_id=neg_x.id, nome="_Pao X", unidade_medida=UnidadeMedida.UN, ativo=True)
        gestor = Usuario(negocio_id=neg.id, nome="_Gestor", email=f"tom_{run}@teste.com",
                         senha_hash=hash_senha("x"), tem_acesso_app=False, tem_acesso_web=True,
                         tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=central.id)
        db.add_all([loja, loja_x, prod, prod_2, prod_x, gestor])
        db.commit()
        ids = dict(neg=neg.id, neg_x=neg_x.id, central=central.id, central_x=central_x.id, loja=loja.id,
                   loja_x=loja_x.id, prod=prod.id, prod_2=prod_2.id, prod_x=prod_x.id, gestor=gestor.id)

        def ordem(data=D, entrega=None, negocio=None, central_id=None, **kw):
            return OrdemProducao(negocio_id=negocio or ids["neg"], central_producao_id=central_id or ids["central"],
                                 data_producao=data, data_entrega=entrega or data, versao_metodo="teste", **kw)

        # ---- ordens ----
        db.execute(text(
            "INSERT INTO ordens_producao (negocio_id, central_producao_id, data_producao, data_entrega, versao_metodo)"
            " VALUES (:neg, :central, :d, :d, 'teste')"), {"neg": ids["neg"], "central": ids["central"], "d": D})
        db.commit()
        linha = db.execute(text(
            "SELECT id, tipo::text, status::text FROM ordens_producao WHERE negocio_id = :neg AND data_producao = :d"),
            {"neg": ids["neg"], "d": D}).one()
        ids["ordem"] = linha[0]
        registrar("O1 padroes do banco na ordem", tuple(linha[1:]) == ("programada", "rascunho"),
                  f"tipo, status = {tuple(linha[1:])}")
        deve_barrar("O2 segunda programada no mesmo dia", lambda s: s.add(ordem()),
                    "uq_ordem_programada_central_data")
        deve_inserir("O3 duas emergenciais no mesmo dia", lambda s: s.add_all(
            [ordem(tipo=TipoOrdemProducao.EMERGENCIAL), ordem(tipo=TipoOrdemProducao.EMERGENCIAL)]))
        deve_barrar("O4 aprovada sem quem e quando",
                    lambda s: s.add(ordem(data=date(2026, 11, 3), status=StatusOrdemProducao.APROVADA)),
                    "ck_ordem_aprovacao_coerente")
        deve_barrar("O5 rascunho com aprovado_por",
                    lambda s: s.add(ordem(data=date(2026, 11, 3), aprovado_por_usuario_id=ids["gestor"])),
                    "ck_ordem_aprovacao_coerente")
        deve_inserir("O6 aprovada com quem e quando", lambda s: s.add(ordem(
            data=date(2026, 11, 4), status=StatusOrdemProducao.APROVADA, aprovado_em=datetime(2026, 11, 3, 20, 0),
            aprovado_por_usuario_id=ids["gestor"])))
        deve_barrar("O7 entrega antes da producao",
                    lambda s: s.add(ordem(data=date(2026, 11, 5), entrega=date(2026, 11, 4))),
                    "ck_ordem_entrega_depois_da_producao")
        deve_barrar("O8 central de outro negocio",
                    lambda s: s.add(ordem(data=date(2026, 11, 6), central_id=ids["central_x"])),
                    "fk_ordem_negocio_central")
        deve_barrar("O9 situacao fora do enum", lambda s: s.execute(text(
            "INSERT INTO ordens_producao (negocio_id, central_producao_id, data_producao, data_entrega,"
            " versao_metodo, status) VALUES (:neg, :central, '2026-11-07', '2026-11-07', 'teste', 'em_producao')"),
            {"neg": ids["neg"], "central": ids["central"]}), excecoes=(DataError,))

        # ---- itens ----
        def item(produto=None, negocio=None, ordem_id=None, **kw):
            return OrdemProducaoItem(negocio_id=negocio or ids["neg"], ordem_id=ordem_id or ids["ordem"],
                                     produto_id=produto or ids["prod"],
                                     tipo_abastecimento=TipoAbastecimento.PRODUZIDO, unidade=UnidadeMedida.KG, **kw)

        obj = item()
        db.add(obj)
        db.commit()
        ids["item"] = obj.id
        gravado = db.execute(text(
            "SELECT tipo_abastecimento::text, unidade::text FROM ordens_producao_itens WHERE id = :i"),
            {"i": ids["item"]}).one()
        registrar("I1 item grava os valores dos enums", tuple(gravado) == ("produzido", "KG"), f"{tuple(gravado)}")
        deve_barrar("I2 mesmo produto duas vezes", lambda s: s.add(item()), "uq_ordem_item_produto")
        deve_barrar("I3 produto de outro negocio", lambda s: s.add(item(produto=ids["prod_x"])),
                    "fk_ordem_item_negocio_produto")
        deve_barrar("I4 item de outro negocio na ordem",
                    lambda s: s.add(item(produto=ids["prod_x"], negocio=ids["neg_x"])), "fk_ordem_item_negocio_ordem")
        deve_barrar("I5 produzida negativa", lambda s: s.add(item(produto=ids["prod_2"],
                                                                  quantidade_produzida=DEC("-1"))),
                    "ck_ordem_item_produzida_nao_negativa")

        # ---- linhas ----
        componentes = {"dias_cobertura": ["2026-11-02"], "minimo": "40", "alvo": "44.0",
                       "contagem_local": "2026-11-01T21:00:00-03:00"}
        avisos = ["sem_contagem"]

        def linha_(loja_id=None, **kw):
            return OrdemProducaoLinha(negocio_id=ids["neg"], item_id=ids["item"], loja_id=loja_id or ids["loja"],
                                      **kw)

        obj = linha_(quantidade_sugerida=DEC("44"), quantidade_final=DEC("40"), componentes=componentes,
                     avisos=avisos)
        db.add(obj)
        db.commit()
        lido = db.execute(text("SELECT componentes, avisos FROM ordens_producao_linhas WHERE id = :i"),
                          {"i": obj.id}).one()
        registrar("L1 componentes e avisos em JSON", lido[0] == componentes and lido[1] == avisos,
                  f"componentes={json.dumps(lido[0], ensure_ascii=True)[:60]}... avisos={lido[1]}")
        deve_barrar("L2 mesma loja duas vezes", lambda s: s.add(linha_()), "uq_ordem_linha_item_loja")
        deve_barrar("L3 loja de outro negocio", lambda s: s.add(linha_(loja_id=ids["loja_x"])),
                    "fk_ordem_linha_negocio_loja")
        # L4-L6 usam um item novo (a loja já tem linha no item principal).
        item_2 = item(produto=ids["prod_2"])
        db.add(item_2)
        db.commit()
        ids["item_2"] = item_2.id

        def linha_2(**kw):
            return OrdemProducaoLinha(negocio_id=ids["neg"], item_id=ids["item_2"], loja_id=ids["loja"], **kw)

        deve_barrar("L4 sugerida negativa", lambda s: s.add(linha_2(quantidade_sugerida=DEC("-0.1"))),
                    "ck_ordem_linha_sugerida_nao_negativa")
        deve_barrar("L5 final negativa", lambda s: s.add(linha_2(quantidade_final=DEC("-1"))),
                    "ck_ordem_linha_final_nao_negativa")
        deve_barrar("L6 recebida negativa", lambda s: s.add(linha_2(quantidade_recebida=DEC("-1"))),
                    "ck_ordem_linha_recebida_nao_negativa")
        db.execute(text("INSERT INTO ordens_producao_linhas (negocio_id, item_id, loja_id) VALUES (:n, :i, :l)"),
                   {"n": ids["neg"], "i": ids["item_2"], "l": ids["loja"]})
        db.commit()
        padrao = db.execute(text(
            "SELECT quantidade_sugerida, quantidade_final, componentes, avisos FROM ordens_producao_linhas"
            " WHERE item_id = :i"), {"i": ids["item_2"]}).one()
        registrar("L7 linha sem quantidades", tuple(padrao) == (None, None, {}, []), f"{tuple(padrao)}")

        # ---- cascata ----
        outra = db.query(OrdemProducao).filter(OrdemProducao.negocio_id == ids["neg"],
                                               OrdemProducao.id != ids["ordem"]).count()
        try:
            db.execute(text("DELETE FROM ordens_producao WHERE id = :o"), {"o": ids["ordem"]})
            db.commit()
            sobras = db.execute(text(
                "SELECT (SELECT count(*) FROM ordens_producao_itens WHERE ordem_id = :o),"
                " (SELECT count(*) FROM ordens_producao_linhas WHERE item_id IN (:i1, :i2))"),
                {"o": ids["ordem"], "i1": ids["item"], "i2": ids["item_2"]}).one()
            depois = db.query(OrdemProducao).filter(OrdemProducao.negocio_id == ids["neg"]).count()
            registrar("C1 apagar a ordem apaga itens e linhas", tuple(sobras) == (0, 0) and depois == outra,
                      f"itens e linhas restantes = {tuple(sobras)}; outras ordens {outra} -> {depois}")
        except IntegrityError as e:
            db.rollback()
            registrar("C1 apagar a ordem apaga itens e linhas", False, f"DELETE barrado: {_constraint(e)}")
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        try:
            print("\n=== Resultado do teste das ordens de produção (migration 0022) ===")
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
