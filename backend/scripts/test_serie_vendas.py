"""
Testa a série diária de vendas do motor de previsão (Fase 3 / F1):
D16 (api vale sobre manual), D17 (zero ou faltante) e "produto não
habilitado na loja não recebe previsão".

Cenário (janela de 02/09 a 08/09/2026; dias 01 e 09 têm vendas fora dela):
  negócio A, central A1, lojas L1 e L2
    P1 (UN) habilitado em L1 e L2 · P2 (KG) habilitado em L1
    P3 habilitado em L1 com ativo = False · P4 sem habilitação em L1
    P5 inativo no catálogo, habilitado em L1, com venda no dia 02
  negócio B, loja LB, produto PB

  Loja L1, dia a dia:
    02  P1 manual 10 · P2 manual 2,5
    03  P1 manual 8 + api 12 (vale a api) · P2 sem linha
    04  nenhuma linha em L1 (mas L2 e o negócio B venderam)
    05  só P4 (não habilitado) vendeu
    06  P1 só api 7
    07  P1 manual 0 (zero explícito)
    08  nenhuma linha em L1
    01 e 09 (fora da janela): P1 manual 99

Casos:
  F1-01 a série tem exatamente os 7 dias da janela, em ordem
  F1-02 só manual -> vale a manual
  F1-03 api + manual no mesmo dia -> vale a api (D16)
  F1-04 KG mantém as casas decimais
  F1-05 dia sem linha do produto, loja com vendas -> zero (D17)
  F1-06 dia sem nenhuma venda na loja -> faltante, mesmo com venda em outra
        loja do negócio e em outro negócio (D17)
  F1-07 loja só com venda de produto não habilitado -> zero para os habilitados
  F1-08 só api -> vale a api
  F1-09 zero explícito -> zero
  F1-10 vendas fora da janela não entram (01 e 09)
  F1-11 série completa de P1 em L1
  F1-12 série completa de P2 em L1
  F1-13 só produtos habilitados e ativos recebem série (P1, P2)
  F1-14 produto com habilitação inativa -> sem série
  F1-15 produto sem habilitação, mesmo com vendas -> sem série
  F1-16 série de P1 em L2 só enxerga as vendas de L2
  F1-17 negócio errado para a loja -> nenhuma série (isolamento)
  F1-18 produto_ids restringe o resultado
  F1-19 data inicial depois da final -> ValueError
  F1-20 seed: loja 001, 11 produtos, 56 dias (18/08 a 12/10), nenhum
        faltante e soma igual à da tabela
  F1-21 produto inativo no catálogo, habilitado e com vendas -> sem série

Uso: python scripts/test_serie_vendas.py
"""

import sys
import uuid
from datetime import date, time
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402
from app.services.serie_vendas_service import serie_diaria, series_da_loja  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 21
PREFIXO_NEGOCIO_TESTE = "_Teste Serie"
SET = lambda d: date(2026, 9, d)  # noqa: E731
INICIO, FIM = SET(2), SET(8)
D = Decimal

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def mostrar(serie):
    if serie is None:
        return "None"
    return "{" + ", ".join(f"{d.day:02d}: {'faltante' if v is None else v}" for d, v in serie.items()) + "}"


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    db.query(VendaDiaria).filter(VendaDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    produto_ids = [p.id for p in db.query(Produto).filter(Produto.negocio_id.in_(negocio_ids))]
    if produto_ids:
        db.query(ProdutoLoja).filter(ProdutoLoja.produto_id.in_(produto_ids)).delete(synchronize_session=False)
    db.query(Produto).filter(Produto.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Usuario).filter(Usuario.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
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
        c_a = CentralProducao(negocio_id=neg_a.id, nome="_Central A1", ativa=True)
        c_b = CentralProducao(negocio_id=neg_b.id, nome="_Central B", ativa=True)
        db.add_all([c_a, c_b])
        db.flush()

        def loja(neg, central, codigo):
            lj = Loja(negocio_id=neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}", codigo=codigo,
                      horario_zeragem=time(6, 0), ativo=True)
            db.add(lj)
            db.flush()
            return lj

        def produto(neg, codigo, unidade=UnidadeMedida.UN, ativo=True):
            p = Produto(negocio_id=neg.id, nome=f"_Produto {codigo}", codigo=codigo, unidade_medida=unidade,
                        ativo=ativo)
            db.add(p)
            db.flush()
            return p

        l1, l2, lb = loja(neg_a, c_a, "L1"), loja(neg_a, c_a, "L2"), loja(neg_b, c_b, "LB")
        p1, p2 = produto(neg_a, "P1"), produto(neg_a, "P2", UnidadeMedida.KG)
        p3, p4, pb = produto(neg_a, "P3"), produto(neg_a, "P4"), produto(neg_b, "PB")
        p5 = produto(neg_a, "P5", ativo=False)
        db.add_all([
            ProdutoLoja(produto_id=p1.id, loja_id=l1.id), ProdutoLoja(produto_id=p2.id, loja_id=l1.id),
            ProdutoLoja(produto_id=p5.id, loja_id=l1.id),
            ProdutoLoja(produto_id=p3.id, loja_id=l1.id, ativo=False), ProdutoLoja(produto_id=p1.id, loja_id=l2.id),
            ProdutoLoja(produto_id=pb.id, loja_id=lb.id),
        ])

        def venda(neg, lj, p, dia, qtd, origem=OrigemVenda.MANUAL):
            db.add(VendaDiaria(negocio_id=neg.id, loja_id=lj.id, produto_id=p.id, data=SET(dia),
                               quantidade=D(qtd), origem=origem))

        venda(neg_a, l1, p1, 1, "99")
        venda(neg_a, l1, p1, 2, "10")
        venda(neg_a, l1, p2, 2, "2.5")
        venda(neg_a, l1, p5, 2, "6")
        venda(neg_a, l1, p1, 3, "8")
        venda(neg_a, l1, p1, 3, "12", OrigemVenda.API)
        venda(neg_a, l2, p1, 4, "5")
        venda(neg_b, lb, pb, 4, "50")
        venda(neg_a, l1, p4, 5, "3")
        venda(neg_a, l1, p4, 6, "4")
        venda(neg_a, l1, p1, 6, "7", OrigemVenda.API)
        venda(neg_a, l1, p1, 7, "0")
        venda(neg_a, l1, p1, 9, "99")
        db.commit()

        series = series_da_loja(db, neg_a.id, l1.id, INICIO, FIM)
        s1, s2 = series.get(p1.id), series.get(p2.id)
        print(f"P1 em L1: {mostrar(s1)}")
        print(f"P2 em L1: {mostrar(s2)}")

        dias = [SET(d) for d in range(2, 9)]
        registrar("F1-01 dias da janela, em ordem", s1 is not None and list(s1) == dias,
                  f"{[d.day for d in s1] if s1 else None}")
        registrar("F1-02 so manual -> manual", s1[SET(2)] == D("10"), f"02 = {s1[SET(2)]}")
        registrar("F1-03 api + manual -> api (D16)", s1[SET(3)] == D("12"), f"03 = {s1[SET(3)]} (manual 8, api 12)")
        registrar("F1-04 KG com decimais", s2[SET(2)] == D("2.5"), f"P2 02 = {s2[SET(2)]}")
        registrar("F1-05 sem linha, loja com vendas -> zero (D17)", s2[SET(3)] == D("0"), f"P2 03 = {s2[SET(3)]}")
        registrar("F1-06 loja sem vendas no dia -> faltante (D17)", s1[SET(4)] is None and s2[SET(4)] is None,
                  f"04 = {s1[SET(4)]} / {s2[SET(4)]} (L2 e negocio B venderam no dia)")
        registrar("F1-07 so produto nao habilitado vendeu -> zero", s1[SET(5)] == D("0") and s2[SET(5)] == D("0"),
                  f"05 = {s1[SET(5)]} / {s2[SET(5)]}")
        registrar("F1-08 so api -> api", s1[SET(6)] == D("7"), f"06 = {s1[SET(6)]}")
        registrar("F1-09 zero explicito -> zero", s1[SET(7)] == D("0"), f"07 = {s1[SET(7)]}")
        registrar("F1-10 fora da janela nao entra", SET(1) not in s1 and SET(9) not in s1 and D("99") not in s1.values(),
                  "01 e 09 (99 un) ausentes")
        esperado_p1 = [D("10"), D("12"), None, D("0"), D("7"), D("0"), None]
        registrar("F1-11 serie completa de P1", list(s1.values()) == esperado_p1, mostrar(s1))
        esperado_p2 = [D("2.5"), D("0"), None, D("0"), D("0"), D("0"), None]
        registrar("F1-12 serie completa de P2", list(s2.values()) == esperado_p2, mostrar(s2))
        registrar("F1-13 so habilitados e ativos", sorted(series) == sorted([p1.id, p2.id]),
                  f"produtos com serie = {sorted(series)}, esperado P1={p1.id}, P2={p2.id}")
        s3 = serie_diaria(db, neg_a.id, l1.id, p3.id, INICIO, FIM)
        registrar("F1-14 habilitacao inativa -> sem serie", s3 is None, f"P3 -> {mostrar(s3)}")
        s4 = serie_diaria(db, neg_a.id, l1.id, p4.id, INICIO, FIM)
        registrar("F1-15 sem habilitacao, com vendas -> sem serie", s4 is None, f"P4 -> {mostrar(s4)}")
        s_l2 = serie_diaria(db, neg_a.id, l2.id, p1.id, INICIO, FIM)
        esperado_l2 = [None, None, D("5"), None, None, None, None]
        registrar("F1-16 P1 em L2 so ve L2", s_l2 is not None and list(s_l2.values()) == esperado_l2, mostrar(s_l2))
        errado = series_da_loja(db, neg_b.id, l1.id, INICIO, FIM)
        registrar("F1-17 negocio errado -> nenhuma serie", errado == {}, f"negocio B + loja L1 -> {errado}")
        s5 = serie_diaria(db, neg_a.id, l1.id, p5.id, INICIO, FIM)
        registrar("F1-21 produto inativo no catalogo -> sem serie", s5 is None and p5.id not in series,
                  f"P5 -> {mostrar(s5)}")
        so_p2 = series_da_loja(db, neg_a.id, l1.id, INICIO, FIM, [p2.id, p4.id])
        registrar("F1-18 produto_ids restringe", list(so_p2) == [p2.id], f"pedido P2 e P4 -> {list(so_p2)}")
        try:
            series_da_loja(db, neg_a.id, l1.id, FIM, INICIO)
            registrar("F1-19 inicio depois do fim", False, "nao levantou erro")
        except ValueError as e:
            registrar("F1-19 inicio depois do fim", True, f"ValueError: {e}")

        # F1-20: seed (só leitura).
        loja_seed = db.query(Loja).filter(Loja.codigo == "001", Loja.nome == "Loja Centro").first()
        if loja_seed is None:
            registrar("F1-20 seed", False, "loja 001 do seed não existe -> rode scripts/seed_dev.py e seed_vendas.py")
        else:
            ini, fim = date(2026, 8, 18), date(2026, 10, 12)
            s_seed = series_da_loja(db, loja_seed.negocio_id, loja_seed.id, ini, fim)
            faltantes = sum(1 for s in s_seed.values() for v in s.values() if v is None)
            soma_serie = sum(v for s in s_seed.values() for v in s.values() if v is not None)
            soma_tabela = db.query(func.sum(VendaDiaria.quantidade)).filter(
                VendaDiaria.negocio_id == loja_seed.negocio_id, VendaDiaria.loja_id == loja_seed.id,
                VendaDiaria.data >= ini, VendaDiaria.data <= fim).scalar()
            dias_por_produto = {len(s) for s in s_seed.values()}
            registrar("F1-20 seed loja 001",
                      len(s_seed) == 11 and dias_por_produto == {56} and faltantes == 0 and soma_serie == soma_tabela,
                      f"{len(s_seed)} produtos, dias por produto {dias_por_produto}, {faltantes} faltante(s), "
                      f"soma serie {soma_serie} / tabela {soma_tabela}")

    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste da série diária de vendas ===")
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
