"""
Critério de aceite da Fase 6 (doc §8, C6): "um gestor consegue, sem acessar
o banco, cadastrar um produto, ver a ordem de produção gerada e
ajustar/confirmar um romaneio".

Tudo o que o gestor e as lojas fazem passa pelas rotas reais: cadastrar o
setor e o produto (SaaS), importar o CSV de vendas, cadastrar um evento,
gerar a previsão, contar no app, gerar e aprovar a ordem, registrar a
produção, gerar, ajustar e aprovar o romaneio, dar saída, ver a entrega no
app e desativar o produto numa loja. Direto no banco só o que ainda não tem
tela no V1 (seção 2 do STATUS): negócio, central, lojas e usuários.

Cenário (hoje = H, data do servidor): central C (prazo 1), lojas 001 e 002
ativas e 003 inativa. Produto novo P (UN, validade 5, todo dia, margem
10%, setor "Pães"). Vendas importadas: 10 por dia nas lojas 001 e 002, nas
8 semanas até ontem -> previsão 10 por dia (base 10, tendência 1, sem cold
start). Evento ×1,5 em H+3 -> 15 nesse dia.

Conta à mão (a mesma da Fase 5): previsão 10 -> cobertura de 1 dia, alvo
11; com prazo 1 a loja vende 10 em H antes da chegada (D45).
  Contagem 001 = 15, 002 = 0 -> 001: 11 − (15 − 10) = 6 · 002: 11 − 0 = 11.
  Produção 10 (< 17): rateio pela final (D70) 10×6/17 = 3,53 e
  10×11/17 = 6,47 -> 3 e 6 + 1 para o maior resto (001) -> 4 / 6.
  O gestor ajusta a 001 para 3 -> romaneio 3 / 6, aprovado e saído.

Casos:
  A1  setor e produto cadastrados pelo SaaS (201), já ativo nas 2 lojas
      ativas da central e não na inativa (D101)
  A2  o produto aparece no app das lojas (contagem)
  A3  importar o CSV de vendas do produto novo (8 semanas, 2 lojas)
  A4  cadastrar o evento ×1,5 em H+3 (pode apagar)
  A5  gerar a previsão: 2 lojas × 7 dias, nenhuma sem número
  A6  previsão de H+1 = 10 nas duas lojas, sem cold start; H+3 = 15 (evento)
  A7  contagem pelo app (001 = 15, 002 = 0)
  A8  ordem de produção pela rota: sugeridas 6 e 11 (conta à mão); aprovar
  A9  produção parcial (10): o romaneio sugere 4 / 6, com escassez
  A10 ajustar a 001 para 3 e aprovar o romaneio (3 / 6)
  A11 saída: cada loja vê no app só a sua entrega (3 e 6)
  A12 desativar o produto na loja 002: some do app da 002, e a previsão
      gerada de novo só tem a 001 (D100)

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_aceite_fase6.py
"""

import sys
import uuid
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import PORTA_WEB, criar_access_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.calendario_producao import CalendarioProducao  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.estoque_atual import EstoqueAtual  # noqa: E402
from app.models.evento import Evento, EventoLoja, EventoProduto  # noqa: E402
from app.models.historico_contagem import HistoricoContagem  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.ordem_producao import OrdemProducao  # noqa: E402
from app.models.ordem_producao_item import OrdemProducaoItem  # noqa: E402
from app.models.ordem_producao_linha import OrdemProducaoLinha  # noqa: E402
from app.models.previsao_diaria import PrevisaoDiaria  # noqa: E402
from app.models.produto import Produto  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.romaneio import Romaneio  # noqa: E402
from app.models.romaneio_entrega import RomaneioEntrega  # noqa: E402
from app.models.romaneio_item import RomaneioItem  # noqa: E402
from app.models.setor_producao import SetorProducao  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402
from app.models.venda_diaria import VendaDiaria  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 12
PREFIXO_NEGOCIO_TESTE = "_Teste Aceite Fase 6"
DEC = Decimal
H = date.today()  # a mesma "hoje" das rotas
SEMANAS_DE_VENDA = 8

cliente = TestClient(app, raise_server_exceptions=False)
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def corpo(r):
    try:
        return r.json()
    except ValueError:
        return r.text


def detalhe(r):
    b = corpo(r)
    return str(b.get("detail") if isinstance(b, dict) else b)[:120]


def num(v):
    return f"{DEC(str(v)).normalize():f}" if v is not None else None


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    lojas = [i for (i,) in db.query(Loja.id).filter(Loja.negocio_id.in_(negocio_ids))]
    db.query(Romaneio).filter(Romaneio.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (RomaneioItem, RomaneioEntrega):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(OrdemProducao).filter(OrdemProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (OrdemProducaoLinha, OrdemProducaoItem, PrevisaoDiaria, EstoqueAtual, HistoricoContagem,
                   CalendarioProducao, VendaDiaria):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    ev_ids = [e.id for e in db.query(Evento).filter(Evento.negocio_id.in_(negocio_ids))]
    if ev_ids:
        for modelo in (EventoLoja, EventoProduto):
            db.query(modelo).filter(modelo.evento_id.in_(ev_ids)).delete(synchronize_session=False)
        db.query(Evento).filter(Evento.id.in_(ev_ids)).delete(synchronize_session=False)
    if lojas:
        db.query(ProdutoLoja).filter(ProdutoLoja.loja_id.in_(lojas)).delete(synchronize_session=False)
    for modelo in (Usuario, Produto, SetorProducao, Loja, CentralProducao):
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

        # O que ainda não tem tela no V1 (seção 2 do STATUS): negócio, central, lojas e usuários.
        neg = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run}", ativo=True))
        negocio_ids = [neg.id]
        c = add(CentralProducao(negocio_id=neg.id, nome="_C", ativa=True, prazo_entrega_dias=1))
        lojas = {cod: add(Loja(negocio_id=neg.id, central_producao_id=c.id, nome=f"_Loja {cod}", codigo=cod,
                               horario_zeragem=time(6, 0), ativo=(cod != "003")))
                 for cod in ("001", "002", "003")}

        def usuario(rotulo, **campos):
            return add(Usuario(negocio_id=neg.id, nome=f"_U {rotulo}", email=f"taf6_{rotulo}_{run}@teste.com",
                               senha_hash=hash_senha("x"), **campos))

        gestor = usuario("gestor", tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=c.id,
                         tem_acesso_app=False, tem_acesso_web=True)
        ops = {cod: usuario(f"op{cod}", tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=lojas[cod].id,
                            tem_acesso_app=True, tem_acesso_web=False) for cod in ("001", "002")}
        db.commit()

        tg = {"Authorization": f"Bearer {criar_access_token(gestor.id, gestor.negocio_id, porta=PORTA_WEB)}"}
        to = {cod: {"Authorization": f"Bearer {criar_access_token(u.id, u.negocio_id)}"} for cod, u in ops.items()}

        def web(metodo, url, **kw):
            return getattr(cliente, metodo)(url, headers=tg, **kw)

        def codigos_no_app(cod):
            r = cliente.get("/produtos", headers=to[cod])
            return sorted(p["codigo"] for p in corpo(r)) if r.status_code == 200 else r.status_code

        # ---------------- cadastro ----------------
        r_setor = web("post", "/producao/setores", json={"nome": "Pães"})
        setor_id = corpo(r_setor).get("id") if r_setor.status_code == 201 else None
        r_prod = web("post", "/web/produtos", json={
            "nome": "Pão de queijo", "codigo": "PQ-01", "unidade_medida": "UN", "dias_validade": 5,
            "margem_maxima_percentual": "10", "setor_producao_id": setor_id,
            "dias_producao": ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"],
            "tipo_abastecimento": "produzido",
        })
        p_id = corpo(r_prod).get("id") if r_prod.status_code == 201 else None
        r_lojas = web("get", f"/web/produtos/{p_id}/lojas")
        ativas = sorted(lj["codigo"] for lj in corpo(r_lojas) if lj["ativo"]) if r_lojas.status_code == 200 else []
        registrar("A1 setor e produto cadastrados pelo SaaS, ativo nas lojas ativas",
                  r_setor.status_code == 201 and r_prod.status_code == 201
                  and corpo(r_prod)["setor"] == {"id": setor_id, "nome": "Pães"} and ativas == ["001", "002"],
                  f"setor {r_setor.status_code}; produto {r_prod.status_code} "
                  f"{corpo(r_prod).get('setor') if isinstance(corpo(r_prod), dict) else detalhe(r_prod)}; "
                  f"lojas ativas {ativas} (003 inativa fica de fora)")
        if p_id is None:
            raise RuntimeError(f"produto não cadastrado: {detalhe(r_prod)}")

        apps = {cod: codigos_no_app(cod) for cod in ops}
        registrar("A2 o produto aparece no app das lojas", apps == {"001": ["PQ-01"], "002": ["PQ-01"]}, f"{apps}")

        # ---------------- vendas, evento e previsão ----------------
        dias = [H - timedelta(days=k) for k in range(SEMANAS_DE_VENDA * 7, 0, -1)]
        csv = "data;codigo_loja;codigo_produto;quantidade\n" + "".join(
            f"{d.strftime('%d/%m/%Y')};{cod};PQ-01;10\n" for d in dias for cod in ("001", "002"))
        r = web("post", "/vendas/importar", files={"arquivo": ("vendas.csv", csv.encode(), "text/csv")})
        b = corpo(r)
        registrar("A3 importar o CSV de vendas do produto novo", r.status_code == 200 and b.get("sucesso")
                  and b.get("inseridas") == len(dias) * 2,
                  f"{r.status_code}; sucesso {b.get('sucesso')}; inseridas {b.get('inseridas')} "
                  f"de {len(dias) * 2}; erros {b.get('erros', [])[:2]}")

        dia_evento = H + timedelta(days=3)
        r = web("post", "/eventos", json={
            "nome": "Festa do bairro", "data_inicio": dia_evento.isoformat(), "data_fim": dia_evento.isoformat(),
            "tipo_ajuste": "multiplicador", "valor_ajuste": "1.5", "escopo_loja": "todas", "produto_ids": [p_id],
        })
        registrar("A4 cadastrar o evento x1,5 em H+3", r.status_code == 201 and corpo(r)["pode_apagar"] is True
                  and corpo(r)["produto_ids"] == [p_id],
                  f"{r.status_code} {corpo(r).get('pode_apagar') if isinstance(corpo(r), dict) else detalhe(r)}")

        r = web("post", "/previsoes/gerar")
        b = corpo(r)
        registrar("A5 gerar a previsao: 2 lojas x 7 dias", r.status_code == 200 and b["gravadas"] == 14
                  and b["sem_previsao"] == 0, f"{r.status_code} gravadas {b.get('gravadas')} "
                  f"sem numero {b.get('sem_previsao')}")

        def previsoes(dia):
            r = web("get", "/previsoes", params={"data": dia.isoformat(), "produto_id": p_id})
            return {i["loja"]["codigo"]: i for i in corpo(r)["itens"]} if r.status_code == 200 else {}

        amanha, no_evento = previsoes(H + timedelta(days=1)), previsoes(dia_evento)
        resumo = {cod: (num(i["previsao"]), num(i["peso_historico"])) for cod, i in sorted(amanha.items())}
        com_evento = {cod: num(i["previsao"]) for cod, i in sorted(no_evento.items())}
        registrar("A6 previsao 10 sem cold start; 15 no dia do evento",
                  resumo == {"001": ("10", "1"), "002": ("10", "1")} and com_evento == {"001": "15", "002": "15"},
                  f"H+1 (previsao, peso) {resumo}; H+3 {com_evento}")

        # ---------------- contagem e ordem ----------------
        contagens = {cod: cliente.patch(f"/estoque/{p_id}", headers=to[cod], json={"quantidade_inventariada": q})
                     for cod, q in (("001", 15), ("002", 0))}
        registrar("A7 contagem pelo app (001 = 15, 002 = 0)",
                  all(r.status_code == 200 for r in contagens.values()),
                  f"{ {cod: r.status_code for cod, r in contagens.items()} }")

        r = web("post", "/producao/ordens/gerar", json={"data_producao": H.isoformat()})
        ordem_id = corpo(r).get("ordem_id") if r.status_code == 200 else None
        ordem = corpo(web("get", f"/producao/ordens/{ordem_id}")) if ordem_id else {}
        itens = [it for it in ordem.get("itens", []) if it["produto"]["id"] == p_id]
        linhas = {ln["loja"]["codigo"]: ln for it in itens for ln in it["linhas"]}
        sug = {cod: num(ln["quantidade_sugerida"]) for cod, ln in sorted(linhas.items())}
        r_ap = web("post", f"/producao/ordens/{ordem_id}/aprovar")
        registrar("A8 ordem de producao gerada pela rota (6 e 11) e aprovada",
                  sug == {"001": "6", "002": "11"} and r_ap.status_code == 200 and corpo(r_ap)["status"] == "aprovada",
                  f"gerar {r.status_code}; sugeridas {sug}; aprovar {r_ap.status_code}")

        # ---------------- produção e romaneio ----------------
        r = web("post", f"/distribuicao/ordens/{ordem_id}/producao",
                json={"itens": [{"item_id": itens[0]["id"], "quantidade": "10"}]})
        r_rom = web("post", "/distribuicao/romaneios/gerar", json={"ordem_id": ordem_id})
        rom_id = corpo(r_rom).get("romaneio_id") if r_rom.status_code == 200 else None
        url = f"/distribuicao/romaneios/{rom_id}"

        def entregas():
            return {e["loja"]["codigo"]: e for e in corpo(web("get", url))["entregas"]}

        def quantidades(campo="quantidade_final"):
            return {cod: num(e["itens"][0][campo]) for cod, e in sorted(entregas().items())}

        registrar("A9 producao parcial: romaneio sugere 4 / 6, com escassez",
                  r.status_code == 200 and r_rom.status_code == 200
                  and corpo(r_rom)["produtos_com_escassez"] == [p_id]
                  and quantidades("quantidade_sugerida") == {"001": "4", "002": "6"},
                  f"producao {r.status_code}; romaneio {r_rom.status_code}; "
                  f"sugerida {quantidades('quantidade_sugerida') if rom_id else '-'}")

        item_001 = entregas()["001"]["itens"][0]["id"]
        r_ed = web("patch", f"{url}/itens/{item_001}", json={"quantidade_final": "3"})
        r_ap = web("post", f"{url}/aprovar")
        registrar("A10 ajustar a 001 para 3 e aprovar o romaneio",
                  r_ed.status_code == 200 and r_ap.status_code == 200 and corpo(r_ap)["status"] == "aprovado"
                  and quantidades() == {"001": "3", "002": "6"},
                  f"ajustar {r_ed.status_code}; aprovar {r_ap.status_code} "
                  f"{corpo(r_ap).get('status') if isinstance(corpo(r_ap), dict) else detalhe(r_ap)}; "
                  f"finais {quantidades()}")

        r = web("post", f"{url}/saida")
        entrega = (H + timedelta(days=1)).isoformat()

        def no_app(cod):
            r = cliente.get("/recebimentos", headers=to[cod])
            return [(e["data_entrega"], [num(i["quantidade_expedida"]) for i in e["itens"]])
                    for e in corpo(r)] if r.status_code == 200 else r.status_code

        recebe = {cod: no_app(cod) for cod in ops}
        registrar("A11 saida: cada loja ve no app a sua entrega",
                  r.status_code == 200 and recebe == {"001": [(entrega, ["3"])], "002": [(entrega, ["6"])]},
                  f"saida {r.status_code}; {recebe}")

        # ---------------- desativar na loja (D100) ----------------
        r = web("put", f"/web/produtos/{p_id}/lojas/{lojas['002'].id}", json={"ativo": False})
        apps = {cod: codigos_no_app(cod) for cod in ops}
        r_prev = web("post", "/previsoes/gerar")
        so_001 = sorted(previsoes(H + timedelta(days=1)))
        registrar("A12 desativado na 002: some do app e da previsao",
                  r.status_code == 200 and apps == {"001": ["PQ-01"], "002": []}
                  and r_prev.status_code == 200 and corpo(r_prev)["gravadas"] == 7 and so_001 == ["001"],
                  f"desativar {r.status_code}; app {apps}; previsao {corpo(r_prev).get('gravadas')} "
                  f"gravadas, lojas em H+1 {so_001}")
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do aceite da Fase 6 (C6) ===")
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
