"""
Testa as regras de banco de vendas_diarias, perdas_diarias e lojas.codigo
(migration 0015, Fase 2 / P2).

Casos:
  V1  venda válida -> inserida
  V2  venda repetida (mesma loja, produto, data e origem) -> barrada pela chave única
  V3  mesma loja/produto/data com outra origem (api) -> inserida (origens coexistem)
  V4  INSERT ... ON CONFLICT DO UPDATE (mecanismo do D5) -> substitui a quantidade, 1 linha só
  V5  loja inexistente -> barrada pela FK
  V6  produto inexistente -> barrada pela FK
  V7  negócio inexistente -> barrada pela FK
  V8  quantidade negativa -> barrada pela check constraint
  V9  origem "inferida" em venda -> recusada pelo enum (só perda tem inferida)
  V10 precisão: 1,234 gravado exato; 1,2345 é arredondado pelo banco para 1,235
  P1  perda inferida -> inserida
  P2  perda repetida -> barrada pela chave única
  P3  perda negativa -> barrada pela check constraint
  L1  dois códigos de loja iguais no mesmo negócio -> barrado
  L2  mesmo código de loja em outro negócio -> aceito
  L3  duas lojas sem código no mesmo negócio -> aceito
  L4  dois produtos com o mesmo código no mesmo negócio -> barrado (migration 0016)
  L5  mesmo código de produto em outro negócio -> aceito
  L6  dois produtos sem código no mesmo negócio -> aceito
  X1  venda com loja de outro negócio -> barrada pela FK composta (negocio_id, loja_id)
  X2  venda com produto de outro negócio -> barrada pela FK composta (negocio_id, produto_id)
  X3  perda com loja de outro negócio -> barrada pela FK composta
  X4  perda com produto de outro negócio -> barrada pela FK composta

Cada caso de erro confere o NOME da constraint que barrou, para garantir
que foi a regra certa. Em V5-V7 (loja, produto ou negócio inexistente)
aceita-se a FK simples ou a composta: as duas expressam a regra, e qual
dispara primeiro depende da ordem interna do PostgreSQL. Saída ASCII ([OK]/[FALHA]), limpeza no início e no
fim, exit 1 se algo falhar.

Uso: python scripts/test_vendas_perdas_modelo.py
"""

import sys
import uuid
from datetime import date, time
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.exc import DataError, IntegrityError, ProgrammingError  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.perda_diaria import OrigemPerda, PerdaDiaria  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 23
PREFIXO_NEGOCIO_TESTE = "_Teste Vendas Modelo"
DIA = date(2026, 10, 1)
INEXISTENTE = 2_000_000_000

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
        aceitas = (constraint_esperada,) if isinstance(constraint_esperada, str) else constraint_esperada
        if aceitas and nome_c not in aceitas:
            registrar(nome, False, f"barrado pela constraint errada: {nome_c} (esperada {' ou '.join(aceitas)})")
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
    db.query(VendaDiaria).filter(VendaDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(PerdaDiaria).filter(PerdaDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
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
        central_a = CentralProducao(negocio_id=neg_a.id, nome="_Central A", ativa=True)
        central_b = CentralProducao(negocio_id=neg_b.id, nome="_Central B", ativa=True)
        db.add_all([central_a, central_b])
        db.flush()
        loja = Loja(negocio_id=neg_a.id, central_producao_id=central_a.id, nome="_Loja A",
                    codigo="T01", horario_zeragem=time(6, 0), ativo=True)
        db.add(loja)
        db.flush()
        prod_un = Produto(negocio_id=neg_a.id, nome="_Produto UN", unidade_medida=UnidadeMedida.UN, ativo=True)
        prod_kg = Produto(negocio_id=neg_a.id, nome="_Produto KG", unidade_medida=UnidadeMedida.KG, ativo=True)
        # Loja e produto do negócio B, para os casos X (outro negócio).
        loja_b = Loja(negocio_id=neg_b.id, central_producao_id=central_b.id, nome="_Loja B",
                      horario_zeragem=time(6, 0), ativo=True)
        prod_b = Produto(negocio_id=neg_b.id, nome="_Produto B", unidade_medida=UnidadeMedida.UN, ativo=True)
        # Produto com código, alvo do caso L4 (código repetido).
        prod_c1 = Produto(negocio_id=neg_a.id, nome="_Produto C-1", codigo="C-1",
                          unidade_medida=UnidadeMedida.UN, ativo=True)
        db.add_all([prod_un, prod_kg, loja_b, prod_b, prod_c1])
        db.commit()
        ids = dict(neg=neg_a.id, neg_b=neg_b.id, loja=loja.id, un=prod_un.id, kg=prod_kg.id,
                   central_a=central_a.id, central_b=central_b.id, loja_b=loja_b.id, prod_b=prod_b.id)

        def venda(qtd, origem=OrigemVenda.MANUAL, loja_id=None, produto_id=None, negocio_id=None, produto=None):
            return VendaDiaria(
                negocio_id=negocio_id or ids["neg"], loja_id=loja_id or ids["loja"],
                produto_id=produto_id or produto or ids["un"], data=DIA, quantidade=Decimal(qtd), origem=origem,
            )

        def perda(qtd, origem=OrigemPerda.INFERIDA, loja_id=None, produto_id=None):
            return PerdaDiaria(negocio_id=ids["neg"], loja_id=loja_id or ids["loja"],
                               produto_id=produto_id or ids["un"], data=DIA, quantidade=Decimal(qtd), origem=origem)

        # ---- vendas ----
        deve_inserir("V1 venda valida", lambda s: s.add(venda("10")))
        deve_barrar("V2 venda repetida (mesma chave)", lambda s: s.add(venda("11")),
                    "uq_venda_loja_produto_data_origem")
        deve_inserir("V3 mesma chave com origem api", lambda s: s.add(venda("12", origem=OrigemVenda.API)))

        # V4: o mecanismo que o serviço de importação vai usar (D5).
        s = SessionLocal()
        try:
            stmt = pg_insert(VendaDiaria).values(
                negocio_id=ids["neg"], loja_id=ids["loja"], produto_id=ids["un"],
                data=DIA, quantidade=Decimal("15"), origem=OrigemVenda.MANUAL,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_venda_loja_produto_data_origem",
                set_={"quantidade": stmt.excluded.quantidade, "atualizado_em": func.now()},
            )
            s.execute(stmt)
            s.commit()
            linhas = s.query(VendaDiaria).filter_by(loja_id=ids["loja"], produto_id=ids["un"], data=DIA,
                                                    origem=OrigemVenda.MANUAL).all()
            ok = len(linhas) == 1 and linhas[0].quantidade == Decimal("15")
            registrar("V4 reimportacao substitui (ON CONFLICT DO UPDATE)", ok,
                      f"{len(linhas)} linha(s) manual, quantidade={[str(x.quantidade) for x in linhas]} (era 10)")
        except Exception as e:
            s.rollback()
            registrar("V4 reimportacao substitui (ON CONFLICT DO UPDATE)", False, f"{type(e).__name__}: {e}")
        finally:
            s.close()

        deve_barrar("V5 loja inexistente", lambda s: s.add(venda("1", loja_id=INEXISTENTE)),
                    ("vendas_diarias_loja_id_fkey", "fk_venda_negocio_loja"))
        deve_barrar("V6 produto inexistente", lambda s: s.add(venda("1", produto_id=INEXISTENTE)),
                    ("vendas_diarias_produto_id_fkey", "fk_venda_negocio_produto"))
        deve_barrar("V7 negocio inexistente", lambda s: s.add(venda("1", negocio_id=INEXISTENTE, produto=ids["kg"])),
                    ("vendas_diarias_negocio_id_fkey", "fk_venda_negocio_loja", "fk_venda_negocio_produto"))
        deve_barrar("V8 quantidade negativa", lambda s: s.add(venda("-1", produto=ids["kg"])),
                    "ck_venda_quantidade_nao_negativa")
        deve_barrar(
            "V9 origem inferida em venda",
            lambda s: s.execute(text(
                "INSERT INTO vendas_diarias (negocio_id, loja_id, produto_id, data, quantidade, origem) "
                "VALUES (:n, :l, :p, :d, 1, 'inferida')"
            ), {"n": ids["neg"], "l": ids["loja"], "p": ids["kg"], "d": DIA}),
            excecoes=(DataError, ProgrammingError, IntegrityError),
        )

        # V10: precisão de 3 casas (D6, gramas em produto KG).
        s = SessionLocal()
        try:
            s.add(VendaDiaria(negocio_id=ids["neg"], loja_id=ids["loja"], produto_id=ids["kg"], data=DIA,
                              quantidade=Decimal("1.234"), origem=OrigemVenda.MANUAL))
            s.add(VendaDiaria(negocio_id=ids["neg"], loja_id=ids["loja"], produto_id=ids["kg"], data=DIA,
                              quantidade=Decimal("1.2345"), origem=OrigemVenda.API))
            s.commit()
            q = {v.origem: v.quantidade for v in s.query(VendaDiaria).filter_by(produto_id=ids["kg"], data=DIA)}
            ok = q.get(OrigemVenda.MANUAL) == Decimal("1.234") and q.get(OrigemVenda.API) == Decimal("1.235")
            registrar("V10 precisao de 3 casas", ok,
                      f"1.234 -> {q.get(OrigemVenda.MANUAL)}; 1.2345 -> {q.get(OrigemVenda.API)} (arredondado pelo banco)")
        except Exception as e:
            s.rollback()
            registrar("V10 precisao de 3 casas", False, f"{type(e).__name__}: {e}")
        finally:
            s.close()

        # ---- perdas ----
        deve_inserir("P1 perda inferida", lambda s: s.add(perda("2")))
        deve_barrar("P2 perda repetida (mesma chave)", lambda s: s.add(perda("3")),
                    "uq_perda_loja_produto_data_origem")
        deve_barrar("P3 perda negativa", lambda s: s.add(perda("-1", origem=OrigemPerda.MANUAL)),
                    "ck_perda_quantidade_nao_negativa")

        # ---- lojas.codigo ----
        def loja_nova(negocio_id, central_id, codigo):
            return Loja(negocio_id=negocio_id, central_producao_id=central_id, nome=f"_Loja {codigo}",
                        codigo=codigo, horario_zeragem=time(6, 0), ativo=True)

        deve_barrar("L1 codigo de loja repetido no mesmo negocio",
                    lambda s: s.add(loja_nova(ids["neg"], ids["central_a"], "T01")), "uq_loja_negocio_codigo")
        deve_inserir("L2 mesmo codigo em outro negocio",
                     lambda s: s.add(loja_nova(ids["neg_b"], ids["central_b"], "T01")))
        deve_inserir("L3 duas lojas sem codigo no mesmo negocio",
                     lambda s: s.add_all([loja_nova(ids["neg"], ids["central_a"], None),
                                          loja_nova(ids["neg"], ids["central_a"], None)]))

        # ---- produtos.codigo (migration 0016) ----
        def produto_novo(negocio_id, codigo):
            return Produto(negocio_id=negocio_id, nome=f"_Produto {codigo}", codigo=codigo,
                           unidade_medida=UnidadeMedida.UN, ativo=True)

        deve_barrar("L4 codigo de produto repetido no mesmo negocio",
                    lambda s: s.add(produto_novo(ids["neg"], "C-1")), "uq_produto_negocio_codigo")
        deve_inserir("L5 mesmo codigo de produto em outro negocio", lambda s: s.add(produto_novo(ids["neg_b"], "C-1")))
        deve_inserir("L6 dois produtos sem codigo no mesmo negocio",
                     lambda s: s.add_all([produto_novo(ids["neg"], None), produto_novo(ids["neg"], None)]))

        # ---- outro negócio (FKs compostas) ----
        deve_barrar("X1 venda com loja de outro negocio",
                    lambda s: s.add(venda("1", loja_id=ids["loja_b"], produto=ids["kg"])), "fk_venda_negocio_loja")
        deve_barrar("X2 venda com produto de outro negocio",
                    lambda s: s.add(venda("1", produto_id=ids["prod_b"])), "fk_venda_negocio_produto")
        deve_barrar("X3 perda com loja de outro negocio",
                    lambda s: s.add(perda("1", origem=OrigemPerda.MANUAL, loja_id=ids["loja_b"])), "fk_perda_negocio_loja")
        deve_barrar("X4 perda com produto de outro negocio",
                    lambda s: s.add(perda("1", origem=OrigemPerda.MANUAL, produto_id=ids["prod_b"])),
                    "fk_perda_negocio_produto")

    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste de vendas_diarias / perdas_diarias / lojas.codigo ===")
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
