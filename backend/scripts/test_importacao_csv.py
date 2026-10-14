"""
Testa o serviço de importação de CSV de vendas e perdas
(app/services/importacao_service.py, Fase 2 / P4), sem endpoint.

Cenário: negócio A com a central do gestor (lojas T01 ativa e T02 inativa)
e outra central (loja T03); negócio B (loja TB9, produto P-B). Produtos de
A, habilitados na loja T01: P-UN (UN), P-KG (KG), PÃO-01 (com acento, para
testar codificação) e P-INAT (produto inativo). Sem habilitação: P-NH.
Habilitado mas desabilitado na loja (ativo = false): P-OFF.

"Hoje" é fixado em 13/10/2026 (parâmetro `hoje` do serviço), para o caso de
data futura não depender do relógio.

Cada caso de erro confere: número da linha, trecho da mensagem e que NADA
foi gravado (D9, tudo ou nada). Os CSVs são gerados em memória com fim de
linha \\r\\n, como o Excel salva.

Uso: python scripts/test_importacao_csv.py
"""

import re
import sys
import uuid
from datetime import date, time
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.dependencies import GestorCentralAutenticado  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.perda_diaria import PerdaDiaria  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.venda_diaria import VendaDiaria  # noqa: E402
from app.services.importacao_service import TipoImportacao, importar_csv  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
PREFIXO_NEGOCIO_TESTE = "_Teste Importacao"
CAB = "data;codigo_loja;codigo_produto;quantidade"
HOJE = date(2026, 10, 13)

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def csv_bytes(linhas, codificacao="utf-8", bom=False, cabecalho=CAB):
    texto = "\r\n".join(([cabecalho] if cabecalho is not None else []) + linhas) + "\r\n"
    dados = texto.encode(codificacao)
    return (b"\xef\xbb\xbf" + dados) if bom else dados


def contar(db, negocio_id):
    db.expire_all()
    v = db.query(VendaDiaria).filter(VendaDiaria.negocio_id == negocio_id).count()
    p = db.query(PerdaDiaria).filter(PerdaDiaria.negocio_id == negocio_id).count()
    return v, p


def resumo_erros(res):
    return "; ".join(f"L{e.linha}: {e.mensagem}" for e in res.erros)


def caso_erro(db, g, nome, conteudo, linha, trecho, tipo=TipoImportacao.VENDA):
    """Espera falha com o erro `trecho` na `linha`, e nada gravado."""
    antes = contar(db, g.negocio_id)
    try:
        res = importar_csv(db, g, conteudo, tipo, hoje=HOJE)
    except Exception as e:
        registrar(nome, False, f"exceção inesperada -> {type(e).__name__}: {e}")
        return
    depois = contar(db, g.negocio_id)
    achou = any(e.linha == linha and trecho in e.mensagem for e in res.erros)
    ok = (not res.sucesso) and achou and antes == depois
    detalhe = resumo_erros(res) if res.erros else "nenhum erro devolvido"
    if antes != depois:
        detalhe += f" | GRAVOU ALGO: {antes} -> {depois}"
    registrar(nome, ok, detalhe)


def caso_sucesso(db, g, nome, conteudo, inseridas, substituidas, tipo=TipoImportacao.VENDA, codificacao=None,
                 avisos=()):
    """Espera sucesso com as contagens dadas e exatamente os avisos dados (trechos)."""
    try:
        res = importar_csv(db, g, conteudo, tipo, hoje=HOJE)
    except Exception as e:
        registrar(nome, False, f"exceção inesperada -> {type(e).__name__}: {e}")
        return None
    ok = res.sucesso and res.inseridas == inseridas and res.substituidas == substituidas
    if codificacao:
        ok = ok and res.codificacao == codificacao
    ok = ok and len(res.avisos) == len(avisos) and all(
        any(t in a.mensagem for a in res.avisos) for t in avisos
    )
    registrar(nome, ok, (
        f"sucesso={res.sucesso}, lidas={res.linhas_lidas}, inseridas={res.inseridas}, "
        f"substituidas={res.substituidas}, codificacao={res.codificacao}, avisos={len(res.avisos)}"
        + (f" | erros: {resumo_erros(res)}" if res.erros else "")
        + (" | avisos: " + "; ".join(f"L{a.linha}: {a.mensagem}" for a in res.avisos) if res.avisos else "")
    ))
    return res


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    db.query(VendaDiaria).filter(VendaDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(PerdaDiaria).filter(PerdaDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    produto_ids = [p.id for p in db.query(Produto).filter(Produto.negocio_id.in_(negocio_ids))]
    if produto_ids:
        db.query(ProdutoLoja).filter(ProdutoLoja.produto_id.in_(produto_ids)).delete(synchronize_session=False)
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
        c_a1 = CentralProducao(negocio_id=neg_a.id, nome="_Central A1", ativa=True)
        c_a2 = CentralProducao(negocio_id=neg_a.id, nome="_Central A2", ativa=True)
        c_b = CentralProducao(negocio_id=neg_b.id, nome="_Central B", ativa=True)
        db.add_all([c_a1, c_a2, c_b])
        db.flush()

        def loja(neg, central, codigo, ativo=True):
            lj = Loja(negocio_id=neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}", codigo=codigo,
                      horario_zeragem=time(6, 0), ativo=ativo)
            db.add(lj)
            return lj

        def produto(neg, codigo, un=UnidadeMedida.UN, ativo=True):
            p = Produto(negocio_id=neg.id, nome=f"_Produto {codigo}", codigo=codigo, unidade_medida=un, ativo=ativo)
            db.add(p)
            return p

        t01 = loja(neg_a, c_a1, "T01")
        loja(neg_a, c_a1, "T02", ativo=False)
        loja(neg_a, c_a2, "T03")
        loja(neg_b, c_b, "TB9")
        p_un = produto(neg_a, "P-UN")
        p_kg = produto(neg_a, "P-KG", UnidadeMedida.KG)
        p_pao = produto(neg_a, "PÃO-01")
        p_inat = produto(neg_a, "P-INAT", ativo=False)
        produto(neg_a, "P-NH")
        p_off = produto(neg_a, "P-OFF")
        produto(neg_b, "P-B")
        db.flush()
        for p in (p_un, p_kg, p_pao, p_inat):
            db.add(ProdutoLoja(produto_id=p.id, loja_id=t01.id))
        db.add(ProdutoLoja(produto_id=p_off.id, loja_id=t01.id, ativo=False))
        db.commit()
        g = GestorCentralAutenticado(usuario_id=0, negocio_id=neg_a.id, central_producao_id=c_a1.id)

        # ---------------- sucessos ----------------
        validas = ["01/10/2026;T01;P-UN;12", "01/10/2026;T01;P-KG;1,25", "02/10/2026;T01;P-UN;8"]
        caso_sucesso(db, g, "C1 CSV valido (UTF-8)", csv_bytes(validas), inseridas=3, substituidas=0, codificacao="utf-8")
        db.expire_all()
        kg = db.query(VendaDiaria).filter_by(produto_id=p_kg.id, data=date(2026, 10, 1)).one()
        registrar("C1b valor KG gravado (D6)", kg.quantidade == Decimal("1.250"), f"1,25 -> {kg.quantidade}")

        caso_sucesso(db, g, "C2 reimportacao do mesmo dia substitui (D5)",
                     csv_bytes(["01/10/2026;T01;P-UN;20", "02/10/2026;T01;P-UN;8"]), inseridas=0, substituidas=2)
        db.expire_all()
        un = db.query(VendaDiaria).filter_by(produto_id=p_un.id, data=date(2026, 10, 1)).all()
        registrar("C2b quantidade substituida, sem linha nova", len(un) == 1 and un[0].quantidade == Decimal("20"),
                  f"{len(un)} linha(s), quantidade={[str(x.quantidade) for x in un]} (era 12)")

        v_antes, p_antes = contar(db, neg_a.id)
        caso_sucesso(db, g, "C3 perdas vao para perdas_diarias", csv_bytes(["01/10/2026;T01;P-UN;2"]),
                     inseridas=1, substituidas=0, tipo=TipoImportacao.PERDA)
        v_dep, p_dep = contar(db, neg_a.id)
        registrar("C3b vendas intactas, 1 perda a mais", (v_dep, p_dep) == (v_antes, p_antes + 1),
                  f"vendas {v_antes}->{v_dep}, perdas {p_antes}->{p_dep}")

        caso_sucesso(db, g, "C4 Windows-1252 (Excel pt-BR) com acento no codigo",
                     csv_bytes(["03/10/2026;T01;PÃO-01;5"], codificacao="cp1252"), 1, 0, codificacao="windows-1252")
        caso_sucesso(db, g, "C5 UTF-8 com BOM (Excel 'CSV UTF-8')",
                     csv_bytes(["04/10/2026;T01;PÃO-01;6"], bom=True), 1, 0, codificacao="utf-8")
        db.expire_all()
        pao = db.query(VendaDiaria).filter_by(produto_id=p_pao.id).count()
        registrar("C5b as duas codificacoes acharam o mesmo produto", pao == 2, f"{pao} venda(s) de PÃO-01")

        caso_sucesso(db, g, "C6 linhas em branco no fim sao ignoradas",
                     csv_bytes(["05/10/2026;T01;P-UN;3", "", ";;;", ""]), 1, 0)
        caso_sucesso(db, g, "C7 cabecalho em maiusculas e com espacos",
                     csv_bytes(["06/10/2026;T01;P-UN;4"], cabecalho="DATA ; Codigo_Loja;CODIGO_PRODUTO;Quantidade"), 1, 0)
        caso_sucesso(db, g, "C8 quantidade zero e 3 casas", csv_bytes(["07/10/2026;T01;P-KG;0", "08/10/2026;T01;P-KG;0,125"]), 2, 0)

        # ---------------- erros (nada gravado) ----------------
        caso_erro(db, g, "E1 data invalida (formato)", csv_bytes(["2026-10-01;T01;P-UN;1"]), 2, "data inválida")
        caso_erro(db, g, "E2 data inexistente", csv_bytes(["31/02/2026;T01;P-UN;1"]), 2, "data inexistente")
        caso_erro(db, g, "E3 produto desconhecido", csv_bytes(["01/10/2026;T01;NAO-EXISTE;1"]), 2, "não encontrado no seu negócio")
        caso_erro(db, g, "E4 loja de outra central (D8)", csv_bytes(["01/10/2026;T03;P-UN;1"]), 2, "não encontrada entre as lojas da sua central")
        caso_erro(db, g, "E5 loja de outro negocio", csv_bytes(["01/10/2026;TB9;P-UN;1"]), 2, "não encontrada entre as lojas da sua central")
        caso_erro(db, g, "E6 produto de outro negocio", csv_bytes(["01/10/2026;T01;P-B;1"]), 2, "não encontrado no seu negócio")
        caso_erro(db, g, "E7 loja inativa (D12)", csv_bytes(["01/10/2026;T02;P-UN;1"]), 2, "está inativa")
        caso_erro(db, g, "E8 quantidade negativa", csv_bytes(["01/10/2026;T01;P-UN;-3"]), 2, "negativa")
        caso_erro(db, g, "E9 mais de 3 casas decimais", csv_bytes(["01/10/2026;T01;P-KG;1,2345"]), 2, "mais de 3 casas")
        caso_erro(db, g, "E10 quantidade com ponto", csv_bytes(["01/10/2026;T01;P-KG;1.234"]), 2, "com ponto")
        caso_erro(db, g, "E11 quantidade vazia", csv_bytes(["01/10/2026;T01;P-UN;"]), 2, "quantidade vazia")
        caso_erro(db, g, "E12 linha duplicada no arquivo",
                  csv_bytes(["09/10/2026;T01;P-UN;1", "09/10/2026;T01;P-UN;2"]), 3, "já aparecem na linha 2")
        caso_erro(db, g, "E13 fracao em produto UN (D13 a)", csv_bytes(["01/10/2026;T01;P-UN;2,5"]), 2, "tem de ser inteira")
        caso_erro(db, g, "E14 numero de colunas errado", csv_bytes(["01/10/2026;T01;P-UN"]), 2, "esperadas 4 colunas")
        caso_erro(db, g, "E15 arquivo vazio (0 bytes)", b"", 0, "arquivo vazio")
        caso_erro(db, g, "E16 arquivo so com espacos", b"  \r\n \r\n", 0, "arquivo vazio")
        caso_erro(db, g, "E17 cabecalho errado", csv_bytes(["01/10/2026;T01;P-UN;1"], cabecalho="data;loja;produto;qtd"), 1, "cabeçalho inválido")
        caso_erro(db, g, "E18 separador virgula", csv_bytes([], cabecalho="data,codigo_loja,codigo_produto,quantidade"), 1, "cabeçalho inválido")
        caso_erro(db, g, "E19 so cabecalho, sem dados", csv_bytes([]), 2, "nenhuma linha de dados")

        # E20: tudo ou nada com linhas válidas + uma inválida no meio.
        conteudo = csv_bytes(["10/10/2026;T01;P-UN;1", "10/10/2026;T01;NAO-EXISTE;1", "11/10/2026;T01;P-UN;1"])
        caso_erro(db, g, "E20 tudo ou nada (2 validas + 1 invalida)", conteudo, 3, "não encontrado")
        db.expire_all()
        n = db.query(VendaDiaria).filter(VendaDiaria.negocio_id == neg_a.id,
                                         VendaDiaria.data.in_([date(2026, 10, 10), date(2026, 10, 11)])).count()
        registrar("E20b nenhuma das linhas validas foi gravada", n == 0, f"{n} venda(s) de 10 e 11/10")

        # E21: vários erros relatados de uma vez, cada um na sua linha.
        res = importar_csv(db, g, csv_bytes(["xx;T01;P-UN;1", "01/10/2026;T99;P-UN;1", "01/10/2026;T01;P-UN;-1"]),
                           TipoImportacao.VENDA, hoje=HOJE)
        linhas = [e.linha for e in res.erros]
        registrar("E21 todos os erros relatados (um por linha)", linhas == [2, 3, 4], f"linhas com erro: {linhas}")

        # E22: vários problemas na MESMA linha aparecem juntos.
        res = importar_csv(db, g, csv_bytes(["xx;T99;NAO-EXISTE;-1"]), TipoImportacao.VENDA, hoje=HOJE)
        msg = res.erros[0].mensagem if res.erros else ""
        partes = ["data inválida", "loja 'T99'", "produto 'NAO-EXISTE'", "negativa"]
        registrar("E22 varios problemas na mesma linha", all(p in msg for p in partes), msg)

        # ---------------- D13 ----------------
        caso_sucesso(db, g, "D1 UN com ',0' e aceito (valor inteiro)", csv_bytes(["01/09/2026;T01;P-UN;2,0"]), 1, 0)
        caso_sucesso(db, g, "D2 produto inativo e aceito (D13 b)", csv_bytes(["01/09/2026;T01;P-INAT;3"]), 1, 0)
        caso_sucesso(db, g, "D3 produto nao habilitado: aceito com aviso (D13 c)",
                     csv_bytes(["02/09/2026;T01;P-NH;4", "02/09/2026;T01;P-UN;1"]), 2, 0,
                     avisos=["'P-NH' não está habilitado na loja 'T01'"])
        caso_sucesso(db, g, "D4 produto desabilitado na loja: aceito com aviso (D13 c)",
                     csv_bytes(["03/09/2026;T01;P-OFF;5"]), 1, 0, avisos=["'P-OFF' está desabilitado na loja 'T01'"])
        caso_erro(db, g, "D5 data futura (D13 d)", csv_bytes(["14/10/2026;T01;P-UN;1"]), 2, "data futura")
        caso_sucesso(db, g, "D6 data de hoje e aceita", csv_bytes(["13/10/2026;T01;P-UN;1"]), 1, 0)
        res = importar_csv(db, g, csv_bytes(["04/09/2026;T01;P-NH;1", "04/09/2026;T01;NAO-EXISTE;1"]),
                           TipoImportacao.VENDA, hoje=HOJE)
        n = db.query(VendaDiaria).filter(VendaDiaria.negocio_id == neg_a.id, VendaDiaria.data == date(2026, 9, 4)).count()
        registrar("D7 arquivo com erro traz erros e avisos, e nao grava",
                  (not res.sucesso) and len(res.erros) == 1 and len(res.avisos) == 1 and n == 0,
                  f"erros={[e.linha for e in res.erros]}, avisos={[a.linha for a in res.avisos]}, gravadas={n}")

        # E25: campo maior que o limite do módulo csv (128 KB) -> mensagem em português.
        caso_erro(db, g, "E25 campo grande demais para o leitor de CSV",
                  csv_bytes(["01/09/2026;T01;P-UN;1", " " * 200_000]), 0, "não pôde ser lido como CSV")

        # E23/E24: arquivo que não é texto não derruba o serviço.
        caso_erro(db, g, "E23 arquivo binario (byte nulo)", bytes(range(256)) * 4, 0, "bytes nulos")
        caso_erro(db, g, "E24 bytes que nao sao UTF-8 nem Windows-1252", CAB.encode() + b"\r\n\x81\x8d;T01;P-UN;1\r\n",
                  0, "nem em Windows-1252")

    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste de importação de CSV ===")
            for r in resultados:
                print(r)
            falhas = [r for r in resultados if r.startswith(FAIL)]
            print(f"\n{len(resultados)} verificações; " + ("TODAS PASSARAM" if not falhas else f"{len(falhas)} FALHARAM"))
        finally:
            try:
                db.rollback()
                _limpar(db, negocio_ids)
            except Exception as e:
                print(f"[aviso] Erro na limpeza: {e}")
            db.close()

    if not resultados or any(r.startswith(FAIL) for r in resultados):
        sys.exit(1)


if __name__ == "__main__":
    main()
