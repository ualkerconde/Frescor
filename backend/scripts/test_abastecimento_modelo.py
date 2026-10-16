"""
Testa as regras de banco da migration 0020 (Fase 4 / N1): seção e prazo de
entrega na central, tipo de abastecimento no produto e negócio no
calendário de produção (D14, D32, D40).

Casos:
  E1  os enums secaocentral e tipoabastecimento existem com os valores certos
  E2  a coluna produtos.tem_producao_propria não existe mais
  C1  central inserida sem seção e sem prazo -> padaria e 0 (padrão do BANCO, por SQL)
  C2  prazo de entrega negativo -> barrado por ck_central_prazo_entrega_nao_negativo
  C3  prazo 1 e seção açougue -> aceitos
  C4  seção fora do enum ('confeitaria') -> recusada pelo enum
  T1  produto inserido sem tipo (por SQL) -> produzido (padrão do banco)
  T2  tipo fora do enum ('comprado') -> recusado pelo enum
  T3  produto pelo ORM com DISTRIBUIDO -> grava 'distribuido' (values_callable)
  K1  calendário com o negócio do produto -> aceito
  K2  calendário com produto de outro negócio -> barrado por fk_calendario_negocio_produto
  K3  calendário sem negocio_id -> barrado (NOT NULL)
  K4  mesmo produto e dia da semana duas vezes -> barrado por uq_calendario_produto_dia
  S1  seed principal: tipo preenchido a partir de tem_producao_propria
      (INT-001..INT-010 produzidos, INT-011 distribuído)

Cada erro confere o NOME da constraint (quando há uma). Saída ASCII
([OK]/[FALHA]), limpeza no início e no fim, exit 1 se algo falhar.

Uso: python scripts/test_abastecimento_modelo.py
"""

import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import DataError, IntegrityError  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.calendario_producao import CalendarioProducao, DiaSemana  # noqa: E402
from app.models.central_producao import CentralProducao, SecaoCentral  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 14
PREFIXO_NEGOCIO_TESTE = "_Teste Abastecimento"
CODIGOS_SEED_PRODUZIDOS = [f"INT-{n:03d}" for n in range(1, 11)]
CODIGO_SEED_DISTRIBUIDO = "INT-011"

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def _constraint(e):
    diag = getattr(getattr(e, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", None)


def deve_inserir(nome, criar):
    """Roda `criar(db)` numa sessão própria e espera sucesso."""
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
    """Roda `criar(db)` numa sessão própria e espera erro (da constraint indicada)."""
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
        registrar(nome, False, f"erro inesperado -> {type(e).__name__}: {e}")
    finally:
        db.close()


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    db.query(CalendarioProducao).filter(CalendarioProducao.negocio_id.in_(negocio_ids)).delete(
        synchronize_session=False)
    db.query(Produto).filter(Produto.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
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


def _valores_enum(db, nome):
    return [r[0] for r in db.execute(text(
        "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
        "WHERE t.typname = :n ORDER BY e.enumsortorder"), {"n": nome})]


def _central_sql(negocio_id, extra_cols="", extra_vals="", params=None):
    """Insere uma central por SQL, sem passar pelos padrões do ORM."""
    def criar(s):
        s.execute(text(
            f"INSERT INTO centrais_producao (negocio_id, nome, ativa, criado_em{extra_cols}) "
            f"VALUES (:neg, '_Central SQL', true, now(){extra_vals})"),
            {"neg": negocio_id, **(params or {})})
    return criar


def _produto_sql(negocio_id, nome, extra_cols="", extra_vals="", params=None):
    """Insere um produto por SQL, sem passar pelos padrões do ORM."""
    def criar(s):
        s.execute(text(
            "INSERT INTO produtos (negocio_id, nome, unidade_medida, ativo, vigencia_recorrente, "
            f"ciclo_previsao, criado_em, atualizado_em{extra_cols}) "
            f"VALUES (:neg, :nome, 'UN', true, false, 'semanal', now(), now(){extra_vals})"),
            {"neg": negocio_id, "nome": nome, **(params or {})})
    return criar


def main():
    _limpar_residuos()
    db = SessionLocal()
    negocio_ids = []
    try:
        run_id = uuid.uuid4().hex[:8]
        neg_a = Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run_id} A", ativo=True)
        neg_b = Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run_id} B", ativo=True)
        db.add_all([neg_a, neg_b])
        db.flush()
        negocio_ids = [neg_a.id, neg_b.id]
        prod_a = Produto(negocio_id=neg_a.id, nome="_Produto A", unidade_medida=UnidadeMedida.UN, ativo=True)
        prod_b = Produto(negocio_id=neg_b.id, nome="_Produto B", unidade_medida=UnidadeMedida.UN, ativo=True)
        db.add_all([prod_a, prod_b])
        db.commit()
        ids = dict(neg=neg_a.id, neg_b=neg_b.id, prod_a=prod_a.id, prod_b=prod_b.id)

        # ---- enums e coluna removida ----
        secoes = _valores_enum(db, "secaocentral")
        tipos = _valores_enum(db, "tipoabastecimento")
        ok = secoes == ["padaria", "acougue", "hortifruti"] and tipos == ["produzido", "distribuido"]
        registrar("E1 enums da 0020", ok, f"secaocentral={secoes} tipoabastecimento={tipos}")
        existe = db.execute(text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'produtos' AND column_name = 'tem_producao_propria'")).scalar()
        registrar("E2 tem_producao_propria removida", existe == 0, f"colunas encontradas: {existe}")

        # ---- central ----
        _central_sql(ids["neg"])(db)
        db.commit()
        linha = db.execute(text(
            "SELECT secao::text, prazo_entrega_dias FROM centrais_producao "
            "WHERE negocio_id = :neg ORDER BY id DESC LIMIT 1"), {"neg": ids["neg"]}).one()
        registrar("C1 padrao do banco na central", tuple(linha) == ("padaria", 0), f"secao, prazo = {tuple(linha)}")
        deve_barrar("C2 prazo negativo",
                    _central_sql(ids["neg"], ", prazo_entrega_dias", ", -1"),
                    "ck_central_prazo_entrega_nao_negativo")
        deve_inserir("C3 prazo 1 e secao acougue",
                     lambda s: s.add(CentralProducao(negocio_id=ids["neg"], nome="_Central Acougue", ativa=True,
                                                     secao=SecaoCentral.ACOUGUE, prazo_entrega_dias=1)))
        deve_barrar("C4 secao fora do enum",
                    _central_sql(ids["neg"], ", secao", ", 'confeitaria'"),
                    excecoes=(DataError,))

        # ---- produto ----
        _produto_sql(ids["neg"], "_Produto SQL sem tipo")(db)
        db.commit()
        tipo = db.execute(text(
            "SELECT tipo_abastecimento::text FROM produtos WHERE negocio_id = :neg AND nome = :nome"),
            {"neg": ids["neg"], "nome": "_Produto SQL sem tipo"}).scalar()
        registrar("T1 padrao do banco no produto", tipo == "produzido", f"tipo_abastecimento = {tipo!r}")
        deve_barrar("T2 tipo fora do enum",
                    _produto_sql(ids["neg"], "_Produto tipo invalido", ", tipo_abastecimento", ", 'comprado'"),
                    excecoes=(DataError,))
        try:
            db.add(Produto(negocio_id=ids["neg"], nome="_Produto distribuido ORM", unidade_medida=UnidadeMedida.UN,
                           ativo=True, tipo_abastecimento=TipoAbastecimento.DISTRIBUIDO))
            db.commit()
            gravado = db.execute(text(
                "SELECT tipo_abastecimento::text FROM produtos WHERE negocio_id = :neg AND nome = :nome"),
                {"neg": ids["neg"], "nome": "_Produto distribuido ORM"}).scalar()
            registrar("T3 ORM grava o valor do enum", gravado == "distribuido", f"gravado = {gravado!r}")
        except Exception as e:
            db.rollback()
            registrar("T3 ORM grava o valor do enum", False, f"{type(e).__name__}: {str(e).splitlines()[0]}")

        # ---- calendário ----
        deve_inserir("K1 calendario com o negocio do produto",
                     lambda s: s.add(CalendarioProducao(negocio_id=ids["neg"], produto_id=ids["prod_a"],
                                                        dia_semana=DiaSemana.SEGUNDA)))
        deve_barrar("K2 calendario com produto de outro negocio",
                    lambda s: s.add(CalendarioProducao(negocio_id=ids["neg"], produto_id=ids["prod_b"],
                                                       dia_semana=DiaSemana.SEGUNDA)),
                    "fk_calendario_negocio_produto")
        deve_barrar("K3 calendario sem negocio_id",
                    lambda s: s.execute(text(
                        "INSERT INTO calendario_producao (produto_id, dia_semana) VALUES (:p, 'terca')"),
                        {"p": ids["prod_a"]}))
        deve_barrar("K4 mesmo produto e dia duas vezes",
                    lambda s: s.add(CalendarioProducao(negocio_id=ids["neg"], produto_id=ids["prod_a"],
                                                       dia_semana=DiaSemana.SEGUNDA)),
                    "uq_calendario_produto_dia")

        # ---- seed principal (dado migrado) ----
        linhas = db.execute(text(
            "SELECT p.codigo, p.tipo_abastecimento::text FROM produtos p "
            "JOIN negocios n ON n.id = p.negocio_id "
            "WHERE n.nome = 'Rede Padaria Teste' AND p.codigo LIKE 'INT-%' ORDER BY p.codigo")).all()
        por_codigo = dict(linhas)
        ok = (all(por_codigo.get(c) == "produzido" for c in CODIGOS_SEED_PRODUZIDOS)
              and por_codigo.get(CODIGO_SEED_DISTRIBUIDO) == "distribuido")
        registrar("S1 seed: tipo migrado de tem_producao_propria", ok,
                  f"{sum(1 for v in por_codigo.values() if v == 'produzido')} produzidos, "
                  f"{CODIGO_SEED_DISTRIBUIDO}={por_codigo.get(CODIGO_SEED_DISTRIBUIDO)!r}")

    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste da migration 0020 (secao, prazo, tipo de abastecimento) ===")
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
