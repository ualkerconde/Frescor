"""
Testa a impressão do romaneio em PDF (Fase 5 / E8, D81, D94), pela rota
real (TestClient), lendo o texto de cada página com o pypdf.

Cenário (negócio A): central A1 com as lojas 003, 001, 004 e 002 (criadas
fora de ordem, para provar a ordem pelo código); central A2 (mesmo
negócio) com a loja 201; negócio X.
Ordem APROVADA da A1 (produção = planejado), romaneio aprovado:
  PA (un)  001 10 · 002 4 · 003 6 · 004 2 -> editado para 0 (D94)
  PB (kg)  001 2,5 · 002 1,5
  PC (un)  003 3
  PX01..PX30 (un) só na 001, 1 cada (a folha da 001 passa de uma página)
  Carga: PA 20 un · PB 4 kg · PC 3 un · PX01..PX30 1 un
Outra ordem da A1 com o romaneio em RASCUNHO (409); romaneio aprovado da
A2 (404 pelo gestor da A1).

Casos:
  P1  todas: 200, application/pdf, nome do arquivo; a folha de carga é a 1a
      página; depois as lojas na ordem do código (001 em 2 páginas)
  P2  nunca duas lojas na mesma página: um só título por página; cada
      folha de loja só tem os produtos dessa loja
  P3  folha de carga: total de cada produto = soma das folhas das lojas
      (PA 20, PB 4 kg, PC 3, PX 1 cada) e a lista das 4 lojas
  P4  folha de loja: quantidades da loja (002: PA 4 un, PB 1,5 kg) e as
      linhas "Conferido por" e "Recebido por" na última página de cada loja
  P5  cabeçalho: central, entrega, produção e hora da impressão em todas
  P6  loja zerada (004): folha própria com PA 0 un (D94)
  P7  filtro "003,002": só a 002 e a 003, na ordem do código; a carga soma
      só as duas (PA 10, PB 1,5 kg, PC 3; sem PX)
  P8  filtro inválido (loja de outra central, texto, vazio no meio) -> 422
  P9  rascunho -> 409 em português
  P10 romaneio de outra central, de outro negócio e inexistente -> 404 igual

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_romaneio_pdf.py
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
from app.models.romaneio import Romaneio  # noqa: E402
from app.models.romaneio_entrega import RomaneioEntrega  # noqa: E402
from app.models.romaneio_item import RomaneioItem  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402
from app.services.distribuicao_service import (  # noqa: E402
    aprovar_romaneio,
    editar_item,
    gerar_romaneio,
    registrar_producao,
)

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 10
PREFIXO_NEGOCIO_TESTE = "_Teste Romaneio PDF"
D = date(2026, 11, 3)  # terça (produção); entrega na quarta
DEC = Decimal
PX = [f"PX{i:02d}" for i in range(1, 31)]
CARGA = "Folha de carga"

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


def titulos(texto):
    """Títulos de folha na página: 'Folha de carga' ou o código da loja."""
    achados = re.findall(r"^Loja: (\d{3}) ·", texto, flags=re.MULTILINE)
    if re.search(rf"^{CARGA}\s*$", texto, flags=re.MULTILINE):
        achados.append(CARGA)
    return achados


def quantidades(texto):
    """{codigo do produto: '10 un' / '2,5 kg'} das linhas de produto da página."""
    return {c: q for c, q in re.findall(r"\b(P[A-Z]\d{0,2}) · _Produto P[A-Z]\d{0,2}\s+([\d.,]+ (?:un|kg))", texto)}


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    db.query(Romaneio).filter(Romaneio.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (RomaneioItem, RomaneioEntrega):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(OrdemProducao).filter(OrdemProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (OrdemProducaoLinha, OrdemProducaoItem, Usuario, Produto, Loja, CentralProducao):
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


def main():
    _limpar_residuos()
    db = SessionLocal()
    negocio_ids = []
    try:
        run = uuid.uuid4().hex[:8]

        def add(obj):
            db.add(obj)
            db.flush()
            return obj

        neg = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} A", ativo=True))
        neg_x = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} X", ativo=True))
        negocio_ids = [neg.id, neg_x.id]
        a1 = add(CentralProducao(negocio_id=neg.id, nome="_Central A1", ativa=True))
        a2 = add(CentralProducao(negocio_id=neg.id, nome="_Central A2", ativa=True))
        cx = add(CentralProducao(negocio_id=neg_x.id, nome="_Central X", ativa=True))

        def loja(codigo, n, central):
            return add(Loja(negocio_id=n.id, central_producao_id=central.id, nome=f"_Loja {codigo}", codigo=codigo,
                            horario_zeragem=time(6, 0), ativo=True))

        lojas = {c: loja(c, neg, a1) for c in ("003", "001", "004", "002")}
        l201, lx = loja("201", neg, a2), loja("901", neg_x, cx)

        def gestor(rotulo, n, central):
            return add(Usuario(negocio_id=n.id, nome=f"_G {rotulo}", email=f"trp_{rotulo}_{run}@teste.com",
                               senha_hash=hash_senha("x"), tipo_usuario=TipoUsuario.GESTOR_CENTRAL,
                               central_producao_id=central.id, tem_acesso_app=False, tem_acesso_web=True))

        g1, g2, gx = gestor("a1", neg, a1), gestor("a2", neg, a2), gestor("x", neg_x, cx)

        produtos = {}

        def produto(n, codigo, unidade=UnidadeMedida.UN):
            p = add(Produto(negocio_id=n.id, nome=f"_Produto {codigo}", codigo=codigo, unidade_medida=unidade,
                            ativo=True, tipo_abastecimento=TipoAbastecimento.PRODUZIDO))
            produtos[(n.id, codigo)] = p
            return p

        for codigo in ["PA", "PC"] + PX:
            produto(neg, codigo)
        produto(neg, "PB", UnidadeMedida.KG)
        produto(neg_x, "PA")
        agora = datetime.utcnow()  # o banco grava UTC sem fuso, como o resto do sistema

        def ordem(n, central, g, data_producao, linhas):
            o = add(OrdemProducao(negocio_id=n.id, central_producao_id=central.id, data_producao=data_producao,
                                  data_entrega=data_producao + timedelta(days=1), versao_metodo="teste",
                                  gerado_em=agora, status=StatusOrdemProducao.APROVADA, aprovado_em=agora,
                                  aprovado_por_usuario_id=g.id))
            itens = {}
            for codigo, por_loja in linhas.items():
                p = produtos[(n.id, codigo)]
                item = add(OrdemProducaoItem(negocio_id=n.id, ordem_id=o.id, produto_id=p.id,
                                             tipo_abastecimento=p.tipo_abastecimento, unidade=p.unidade_medida))
                itens[item.id] = sum(DEC(q) for _, q in por_loja)
                for lj, q in por_loja:
                    add(OrdemProducaoLinha(negocio_id=n.id, item_id=item.id, loja_id=lj.id,
                                           quantidade_sugerida=DEC(q), quantidade_final=DEC(q)))
            db.commit()
            registrar_producao(db, n.id, central.id, o.id, itens, g.id)
            return o, gerar_romaneio(db, n.id, central.id, o.id, g.id).romaneio_id

        L = lojas
        linhas_a1 = {"PA": [(L["001"], "10"), (L["002"], "4"), (L["003"], "6"), (L["004"], "2")],
                     "PB": [(L["001"], "2.5"), (L["002"], "1.5")], "PC": [(L["003"], "3")]}
        linhas_a1.update({c: [(L["001"], "1")] for c in PX})
        oa, rom = ordem(neg, a1, g1, D, linhas_a1)
        item_004 = (db.query(RomaneioItem.id).join(RomaneioEntrega, RomaneioEntrega.id == RomaneioItem.entrega_id)
                    .filter(RomaneioEntrega.romaneio_id == rom, RomaneioEntrega.loja_id == L["004"].id).scalar())
        editar_item(db, neg.id, a1.id, rom, item_004, DEC(0), g1.id, "faltou na produção")
        aprovar_romaneio(db, neg.id, a1.id, rom, g1.id)
        _, rom_rascunho = ordem(neg, a1, g1, D + timedelta(days=2), {"PA": [(L["001"], "3")]})
        _, rom_a2 = ordem(neg, a2, g2, D, {"PA": [(l201, "5")]})
        aprovar_romaneio(db, neg.id, a2.id, rom_a2, g2.id)
        _, rom_x = ordem(neg_x, cx, gx, D, {"PA": [(lx, "5")]})
        aprovar_romaneio(db, neg_x.id, cx.id, rom_x, gx.id)

        t1 = criar_access_token(g1.id, g1.negocio_id, porta=PORTA_WEB)

        def pdf(romaneio_id, lojas_param=None):
            params = {"lojas": lojas_param} if lojas_param is not None else None
            return cliente.get(f"/distribuicao/romaneios/{romaneio_id}/pdf", params=params,
                               headers={"Authorization": f"Bearer {t1}"})

        # ---- P1 a P6: todas as lojas ----
        r = pdf(rom)
        pags = paginas(r) if r.status_code == 200 else []
        por_pagina = [titulos(t) for t in pags]
        # Folhas = páginas seguidas com o mesmo título (uma folha longa continua na página seguinte).
        sequencia = []
        for tit in por_pagina:
            chave = tit[0] if len(tit) == 1 else f"?{tit}"
            if not sequencia or sequencia[-1][0] != chave:
                sequencia.append([chave, 0])
            sequencia[-1][1] += 1
        registrar("P1 carga primeiro e lojas na ordem do codigo",
                  r.status_code == 200 and r.headers.get("content-type") == "application/pdf"
                  and f'filename="romaneio-{D + timedelta(days=1):%Y-%m-%d}.pdf"' in r.headers.get(
                      "content-disposition", "") and [c for c, _ in sequencia] == [CARGA, "001", "002", "003", "004"]
                  and dict(sequencia)["001"] == 2,
                  f"{r.status_code} {r.headers.get('content-type')}; folhas (titulo, paginas) {sequencia}")

        textos = {}  # titulo -> texto de todas as páginas da folha
        for t, tit in zip(pags, por_pagina):
            if len(tit) == 1:
                textos[tit[0]] = textos.get(tit[0], "") + "\n" + t
        folhas = {k: quantidades(v) for k, v in textos.items() if k != CARGA}
        esperado_lojas = {"001": {"PA", "PB", *PX}, "002": {"PA", "PB"}, "003": {"PA", "PC"}, "004": {"PA"}}
        registrar("P2 uma loja por pagina e so os produtos dela",
                  all(len(t) == 1 for t in por_pagina)
                  and {k: set(v) for k, v in folhas.items()} == esperado_lojas,
                  f"titulos {por_pagina}; produtos {{{', '.join(f'{k}: {len(v)}' for k, v in sorted(folhas.items()))}}}")

        texto_carga = textos.get(CARGA, "")
        carga = quantidades(texto_carga)
        def numero(q):
            valor, unidade = q.split(" ")
            return DEC(valor.replace(".", "").replace(",", ".")), unidade

        somas = {}
        for v in folhas.values():
            for c, q in v.items():
                n, unidade = numero(q)
                somas[c] = (somas.get(c, (DEC(0), unidade))[0] + n, unidade)
        lojas_carga = re.findall(r"^(\d{3}) · _Loja", texto_carga, flags=re.MULTILINE)
        registrar("P3 carga = soma das lojas",
                  carga.get("PA") == "20 un" and carga.get("PB") == "4 kg" and carga.get("PC") == "3 un"
                  and all(carga.get(c) == "1 un" for c in PX)
                  and {c: numero(q) for c, q in carga.items()} == somas
                  and lojas_carga == ["001", "002", "003", "004"],
                  f"PA {carga.get('PA')}, PB {carga.get('PB')}, PC {carga.get('PC')}, {len(carga)} produtos; "
                  f"lojas {lojas_carga}")

        ultima_de = {}
        for i, tit in enumerate(por_pagina):
            ultima_de[tit[0] if tit else "?"] = i
        assinaturas = all("Conferido por:" in pags[i] and "Recebido por:" in pags[i] for i in ultima_de.values())
        # A 1a página da 001 continua na seguinte: as assinaturas ficam só no fim da folha.
        primeira_001 = por_pagina.index(["001"]) if ["001"] in por_pagina else 0
        registrar("P4 folha da loja com as quantidades e as assinaturas",
                  folhas.get("002") == {"PA": "4 un", "PB": "1,5 kg"} and folhas.get("003") == {"PA": "6 un",
                                                                                                  "PC": "3 un"}
                  and assinaturas and "Conferido por:" not in pags[primeira_001],
                  f"002 {folhas.get('002')}; 003 {folhas.get('003')}; assinaturas nas ultimas {assinaturas}")

        entrega_txt = f"{D + timedelta(days=1):%d/%m/%Y}"
        cabecalho_ok = all("_Central A1" in t and "Romaneio aprovado" in t and f"Entrega: quarta, {entrega_txt}" in t
                           and f"Produção: {D:%d/%m/%Y}" in t and re.search(r"Impresso em \d{2}/\d{2}/\d{4} às \d{2}:\d{2}", t)
                           for t in pags)
        registrar("P5 cabecalho em todas as paginas", bool(pags) and cabecalho_ok,
                  f"{len(pags)} paginas; {pags[0].splitlines()[:4] if pags else ''}")
        registrar("P6 loja zerada com folha propria (D94)", folhas.get("004") == {"PA": "0 un"},
                  f"004 {folhas.get('004')}")

        # ---- P7 e P8: filtro ----
        r = pdf(rom, f"{L['003'].id},{L['002'].id}")
        pags_f = paginas(r) if r.status_code == 200 else []
        tit_f = [titulos(t) for t in pags_f]
        carga_f = quantidades(pags_f[0]) if pags_f else {}
        registrar("P7 filtro de lojas",
                  tit_f == [[CARGA], ["002"], ["003"]] and carga_f == {"PA": "10 un", "PB": "1,5 kg", "PC": "3 un"},
                  f"{r.status_code} paginas {tit_f}; carga {carga_f}")
        invalidos = {"loja de outra central": str(l201.id), "texto": "abc", "vazio no meio": f"{L['001'].id},,"}
        rs = {k: pdf(rom, v) for k, v in invalidos.items()}
        registrar("P8 filtro invalido -> 422",
                  all(x.status_code == 422 and "Loja" in str(detalhe(x)) for x in rs.values()),
                  "; ".join(f"{k} {x.status_code} {str(detalhe(x))[:50]}" for k, x in rs.items()))

        # ---- P9 e P10 ----
        r = pdf(rom_rascunho)
        registrar("P9 rascunho -> 409", r.status_code == 409 and "aprovado" in str(detalhe(r)),
                  f"{r.status_code} {detalhe(r)}")
        rs = [pdf(rom_a2), pdf(rom_x), pdf(rom_x + 100000)]
        registrar("P10 outra central, outro negocio, inexistente -> 404 igual",
                  [x.status_code for x in rs] == [404] * 3 and len({x.text for x in rs}) == 1,
                  f"{[x.status_code for x in rs]} {detalhe(rs[0])}")
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste do PDF do romaneio (E8) ===")
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
