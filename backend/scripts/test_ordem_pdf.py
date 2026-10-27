"""
Testa a impressão da ordem de produção em PDF (Fase 4 / N9b, D67), pelas
rotas reais (TestClient), lendo o texto de cada página com o pypdf, e as
regras de banco dos setores (migration 0023).

Cenário (negócio A): central A com L1 e L2; central B do mesmo negócio;
negócio X. Setores da central A: Pães (1), Bolos (2), Biscoitos (3, sem
produto na ordem), Antigo (4, INATIVO); setor B1 da central B.
Produtos e quantidade final por loja (L1 / L2) na ordem APROVADA:
  PAO   Pão Francês   Pães                       44 / 22 un
  BAG   Baguete       Pães (KG)                  3,5 kg / 0 (L2 não sai)
  BL01..BL12 Bolo     Bolos                      i / i un (12 produtos: 2+ páginas)
  EMP   Empada        sem setor                  10 / 5 un
  ROS   Rosca         setor Antigo (inativo)     7 / 3 un  -> "Sem setor"
  CUC   Cuca          setor B1 (outra central)   4 / 2 un  -> "Sem setor"
  MAN   Manteiga      Pães, DISTRIBUÍDO          9 / 9 un  -> não sai
  SON   Sonho         Bolos                      0 / 0     -> não sai
Ordem em rascunho (outro dia) para o 409.

Casos:
  P1  todos: 200, application/pdf, nome do arquivo; folhas na ordem Pães,
      Bolos (2+ páginas), Sem setor; Biscoitos (sem produto) não sai
  P2  nunca dois setores na mesma página: cada página tem um cabeçalho de
      setor e só produtos desse setor
  P3  folha de Pães: total em destaque e por loja (Pão 66 un: 44 e 22;
      Baguete 3,5 kg só na L1); sem a Manteiga (distribuída) e sem a loja
      com 0
  P4  folha "Sem setor": Empada, Rosca (setor inativo) e Cuca (setor de
      outra central); sem o Sonho (total 0)
  P5  cabeçalho: central, dia de produção, entrega e hora da impressão
  P6  filtro: só Bolos; Pães + sem setor (nessa ordem)
  P7  setor escolhido sem produto (Biscoitos): 1 página dizendo isso
  P8  setor inválido, inativo ou de outra central -> 422 em português
  P9  rascunho -> 409 em português
  P10 central de outro negócio, outra central do mesmo negócio e ordem
      inexistente -> 404 igual
  P11 GET /producao/setores: só os da central do gestor, na ordem
  M1  banco: nome repetido na central -> uq_setor_central_nome; produto com
      setor de outro negócio -> fk_produto_negocio_setor; nome vazio ->
      ck_setor_nome_preenchido

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_ordem_pdf.py
"""

import io
import re
import sys
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from pypdf import PdfReader  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.core.security import PORTA_WEB, criar_access_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.ordem_producao import OrdemProducao, StatusOrdemProducao  # noqa: E402
from app.models.ordem_producao_item import OrdemProducaoItem  # noqa: E402
from app.models.ordem_producao_linha import OrdemProducaoLinha  # noqa: E402
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida  # noqa: E402
from app.models.setor_producao import SetorProducao  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 12
PREFIXO_NEGOCIO_TESTE = "_Teste Ordem PDF"
D = date(2026, 11, 2)  # segunda
DEC = Decimal
BOLOS = [f"BL{i:02d}" for i in range(1, 13)]
PRODUTOS_DO_SETOR = {"Pães": ["PAO", "BAG"], "Bolos": BOLOS, "Sem setor": ["EMP", "ROS", "CUC"]}
NUNCA = ["MAN", "SON"]

cliente = TestClient(app, raise_server_exceptions=False)
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def detalhe(r):
    try:
        b = r.json()
        return b.get("detail") if isinstance(b, dict) else b
    except ValueError:
        return r.text[:80]


def paginas(r):
    """Texto de cada página do PDF da resposta."""
    return [p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages]


def setor_da_pagina(texto):
    achados = re.findall(r"Setor: ([^\n]+?)\s*$", texto, flags=re.MULTILINE)
    return achados


def codigos_na_pagina(texto):
    todos = [c for lista in PRODUTOS_DO_SETOR.values() for c in lista] + NUNCA
    return {c for c in todos if re.search(rf"\b{c} ·", texto)}


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    db.query(OrdemProducao).filter(OrdemProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Usuario).filter(Usuario.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Produto).filter(Produto.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(SetorProducao).filter(SetorProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
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


def montar(db):
    run = uuid.uuid4().hex[:8]

    def add(obj):
        db.add(obj)
        db.flush()
        return obj

    neg = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} A", ativo=True))
    neg_x = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} X", ativo=True))
    a = add(CentralProducao(negocio_id=neg.id, nome="Central Teste PDF", ativa=True))
    b = add(CentralProducao(negocio_id=neg.id, nome="_Central B", ativa=True))
    cx = add(CentralProducao(negocio_id=neg_x.id, nome="_Central X", ativa=True))
    l1 = add(Loja(negocio_id=neg.id, central_producao_id=a.id, nome="Loja Um", codigo="L1",
                  horario_zeragem=time(6, 0), ativo=True))
    l2 = add(Loja(negocio_id=neg.id, central_producao_id=a.id, nome="Loja Dois", codigo="L2",
                  horario_zeragem=time(6, 0), ativo=True))
    setores = {
        "Pães": add(SetorProducao(negocio_id=neg.id, central_producao_id=a.id, nome="Pães", ordem=1)),
        "Bolos": add(SetorProducao(negocio_id=neg.id, central_producao_id=a.id, nome="Bolos", ordem=2)),
        "Biscoitos": add(SetorProducao(negocio_id=neg.id, central_producao_id=a.id, nome="Biscoitos", ordem=3)),
        "Antigo": add(SetorProducao(negocio_id=neg.id, central_producao_id=a.id, nome="Antigo", ordem=4,
                                    ativo=False)),
        "B1": add(SetorProducao(negocio_id=neg.id, central_producao_id=b.id, nome="B1", ordem=1)),
    }

    def usuario(rotulo, n, central):
        return add(Usuario(negocio_id=n.id, nome=f"Gestor {rotulo}", email=f"topdf_{rotulo}_{run}@teste.com",
                           senha_hash=hash_senha("x"), tipo_usuario=TipoUsuario.GESTOR_CENTRAL,
                           central_producao_id=central.id, tem_acesso_web=True, tem_acesso_app=False))

    gestores = {"a": usuario("a", neg, a), "b": usuario("b", neg, b), "x": usuario("x", neg_x, cx)}

    # codigo: (nome, setor, unidade, tipo, L1, L2)
    produtos = {
        "PAO": ("Pão Francês", "Pães", UnidadeMedida.UN, TipoAbastecimento.PRODUZIDO, "44", "22"),
        "BAG": ("Baguete", "Pães", UnidadeMedida.KG, TipoAbastecimento.PRODUZIDO, "3.5", "0"),
        "EMP": ("Empada", None, UnidadeMedida.UN, TipoAbastecimento.PRODUZIDO, "10", "5"),
        "ROS": ("Rosca", "Antigo", UnidadeMedida.UN, TipoAbastecimento.PRODUZIDO, "7", "3"),
        "CUC": ("Cuca", "B1", UnidadeMedida.UN, TipoAbastecimento.PRODUZIDO, "4", "2"),
        "MAN": ("Manteiga", "Pães", UnidadeMedida.UN, TipoAbastecimento.DISTRIBUIDO, "9", "9"),
        "SON": ("Sonho", "Bolos", UnidadeMedida.UN, TipoAbastecimento.PRODUZIDO, "0", "0"),
    }
    for i, c in enumerate(BOLOS, 1):
        produtos[c] = (f"Bolo {i}", "Bolos", UnidadeMedida.UN, TipoAbastecimento.PRODUZIDO, str(i), str(i))

    def ordem(dia, status):
        aprovada = status == StatusOrdemProducao.APROVADA
        o = add(OrdemProducao(negocio_id=neg.id, central_producao_id=a.id, data_producao=dia, data_entrega=dia,
                              status=status, versao_metodo="teste", gerado_em=datetime(2026, 11, 1, 23, 0),
                              aprovado_em=datetime(2026, 11, 1, 23, 30) if aprovada else None,
                              aprovado_por_usuario_id=gestores["a"].id if aprovada else None))
        for codigo, (nome, setor, unidade, tipo, q1, q2) in produtos.items():
            p = db.query(Produto).filter(Produto.negocio_id == neg.id, Produto.codigo == codigo).one_or_none()
            if p is None:
                p = add(Produto(negocio_id=neg.id, nome=nome, codigo=codigo, unidade_medida=unidade, ativo=True,
                                tipo_abastecimento=tipo, setor_producao_id=setores[setor].id if setor else None))
            item = add(OrdemProducaoItem(negocio_id=neg.id, ordem_id=o.id, produto_id=p.id, tipo_abastecimento=tipo,
                                         unidade=unidade))
            for loja, q in ((l1, q1), (l2, q2)):
                db.add(OrdemProducaoLinha(negocio_id=neg.id, item_id=item.id, loja_id=loja.id,
                                          quantidade_sugerida=DEC(q), quantidade_final=DEC(q)))
        return o

    aprovada = ordem(D, StatusOrdemProducao.APROVADA)
    rascunho = ordem(D + timedelta(days=1), StatusOrdemProducao.RASCUNHO)
    db.commit()
    tokens = {k: criar_access_token(u.id, u.negocio_id, porta=PORTA_WEB) for k, u in gestores.items()}
    return neg, neg_x, setores, aprovada.id, rascunho.id, tokens


def main():
    _limpar_residuos()
    db = SessionLocal()
    negocio_ids = []
    try:
        neg, neg_x, setores, ordem_id, rascunho_id, tk = montar(db)
        negocio_ids = [neg.id, neg_x.id]

        def pdf(token, sufixo="", ordem=None):
            return cliente.get(f"/producao/ordens/{ordem or ordem_id}/pdf{sufixo}",
                               headers={"Authorization": f"Bearer {token}"})

        # ---- P1/P2: todos ----
        r = pdf(tk["a"])
        textos = paginas(r) if r.status_code == 200 else []
        cabecalhos = [setor_da_pagina(t) for t in textos]
        sequencia = [c[0] if len(c) == 1 else c for c in cabecalhos]
        compacta = [s for i, s in enumerate(sequencia) if i == 0 or s != sequencia[i - 1]]
        ok = (r.status_code == 200 and r.headers.get("content-type") == "application/pdf"
              and 'filename="ordem-producao-2026-11-02.pdf"' in r.headers.get("content-disposition", "")
              and compacta == ["Pães", "Bolos", "Sem setor"] and sequencia.count("Bolos") >= 2)
        registrar("P1 todos os setores, cada um em pagina nova", ok,
                  f"{r.status_code} {len(textos)} páginas: {sequencia}")

        erros = []
        for i, (t, cab) in enumerate(zip(textos, cabecalhos), 1):
            if len(cab) != 1:
                erros.append(f"página {i} com cabeçalhos {cab}")
                continue
            alheios = codigos_na_pagina(t) - set(PRODUTOS_DO_SETOR.get(cab[0], []))
            if alheios:
                erros.append(f"página {i} ({cab[0]}) com {sorted(alheios)}")
        registrar("P2 nunca dois setores na mesma pagina", textos != [] and not erros,
                  "cada página tem um setor e só os produtos dele" if not erros else "; ".join(erros))

        paes = next((t for t, c in zip(textos, cabecalhos) if c == ["Pães"]), "")
        ok = ("PAO · Pão Francês" in paes and "66 un" in paes and "44 un" in paes and "22 un" in paes
              and "BAG · Baguete" in paes and "3,5 kg" in paes and paes.count("L2 · Loja Dois") == 1
              and "MAN ·" not in paes)
        registrar("P3 folha de Paes: total e lojas", ok,
                  "Pão 66 un (44 + 22); Baguete 3,5 kg só na L1; sem Manteiga" if ok else paes[:300])

        sem = next((t for t, c in zip(textos, cabecalhos) if c == ["Sem setor"]), "")
        ok = all(f"{c} ·" in sem for c in ("EMP", "ROS", "CUC")) and "SON ·" not in "".join(textos)
        registrar("P4 folha Sem setor", ok, "Empada, Rosca (setor inativo), Cuca (outra central); sem o Sonho (0)"
                  if ok else sem[:300])

        primeira = textos[0] if textos else ""
        ok = ("Central Teste PDF" in primeira and "Produção: segunda, 02/11/2026" in primeira
              and "Entrega: 02/11/2026" in primeira and re.search(r"Impresso em \d\d/\d\d/\d{4} às \d\d:\d\d", primeira))
        registrar("P5 cabecalho da folha", bool(ok), "central, produção, entrega e hora da impressão"
                  if ok else primeira[-300:])

        # ---- P6/P7: filtro ----
        r_bolos = pdf(tk["a"], f"?setores={setores['Bolos'].id}")
        s_bolos = [setor_da_pagina(t) for t in paginas(r_bolos)] if r_bolos.status_code == 200 else []
        r_dois = pdf(tk["a"], f"?setores=sem,{setores['Pães'].id}")
        s_dois = [setor_da_pagina(t) for t in paginas(r_dois)] if r_dois.status_code == 200 else []
        ok = (s_bolos and all(c == ["Bolos"] for c in s_bolos) and s_dois == [["Pães"], ["Sem setor"]])
        registrar("P6 filtro de setores", bool(ok), f"só Bolos: {len(s_bolos)} páginas; Pães + sem setor: {s_dois}")

        r_vazio = pdf(tk["a"], f"?setores={setores['Biscoitos'].id}")
        t_vazio = paginas(r_vazio) if r_vazio.status_code == 200 else []
        ok = len(t_vazio) == 1 and "Nenhum produto deste setor" in t_vazio[0] and setor_da_pagina(t_vazio[0]) == ["Biscoitos"]
        registrar("P7 setor escolhido sem produto", ok, f"{len(t_vazio)} página")

        # ---- P8-P10: erros ----
        invalidos = [pdf(tk["a"], s) for s in ("?setores=abc", f"?setores={setores['Antigo'].id}",
                                                f"?setores={setores['B1'].id}")]
        ok = all(x.status_code == 422 and isinstance(detalhe(x), str) for x in invalidos)
        registrar("P8 setor invalido, inativo ou de outra central -> 422", ok,
                  " | ".join(f"{x.status_code} {detalhe(x)}" for x in invalidos))

        r_rasc = pdf(tk["a"], ordem=rascunho_id)
        registrar("P9 rascunho -> 409", r_rasc.status_code == 409 and "aprovada" in str(detalhe(r_rasc)),
                  f"{r_rasc.status_code} {detalhe(r_rasc)}")

        r_x, r_b, r_inex = pdf(tk["x"]), pdf(tk["b"]), pdf(tk["a"], ordem=2_000_000_000)
        ok = r_x.status_code == r_b.status_code == r_inex.status_code == 404 and detalhe(r_x) == detalhe(r_b) == detalhe(r_inex)
        registrar("P10 outro negocio, outra central, inexistente -> 404 igual", ok,
                  f"{r_x.status_code} {r_b.status_code} {r_inex.status_code} {detalhe(r_x)}")

        # ---- P11: lista de setores ----
        def nomes(token):
            r_ = cliente.get("/producao/setores", headers={"Authorization": f"Bearer {token}"})
            return [(s["nome"], s["ativo"]) for s in r_.json()] if r_.status_code == 200 else r_.status_code

        lista_a, lista_b, lista_x = nomes(tk["a"]), nomes(tk["b"]), nomes(tk["x"])
        ok = (lista_a == [("Pães", True), ("Bolos", True), ("Biscoitos", True), ("Antigo", False)]
              and lista_b == [("B1", True)] and lista_x == [])
        registrar("P11 setores da central do gestor", ok, f"A={lista_a} B={lista_b} X={lista_x}")

        # ---- M1: banco ----
        erros = []
        for rotulo, criar, esperado in (
            ("nome repetido", lambda s: s.add(SetorProducao(negocio_id=neg.id,
                                                            central_producao_id=setores["Pães"].central_producao_id,
                                                            nome="Pães")), "uq_setor_central_nome"),
            ("setor de outro negócio", lambda s: s.add(Produto(negocio_id=neg_x.id, nome="_X", ativo=True,
                                                               unidade_medida=UnidadeMedida.UN,
                                                               setor_producao_id=setores["Pães"].id)),
             "fk_produto_negocio_setor"),
            ("nome vazio", lambda s: s.add(SetorProducao(negocio_id=neg.id,
                                                         central_producao_id=setores["Pães"].central_producao_id,
                                                         nome="  ")), "ck_setor_nome_preenchido"),
        ):
            s = SessionLocal()
            try:
                criar(s)
                s.commit()
                erros.append(f"{rotulo}: aceito")
            except IntegrityError as e:
                s.rollback()
                nome_c = getattr(getattr(e.orig, "diag", None), "constraint_name", None)
                if nome_c != esperado:
                    erros.append(f"{rotulo}: {nome_c} (esperada {esperado})")
            finally:
                s.close()
        registrar("M1 regras de banco dos setores", not erros, "3 recusadas pela constraint certa" if not erros
                  else "; ".join(erros))
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste da impressão da ordem (N9b) ===")
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
