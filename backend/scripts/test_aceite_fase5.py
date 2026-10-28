"""
Critério de aceite da Fase 5 (doc §8, D84): "gerar romaneio a partir de uma
ordem de produção com produção parcial (menor que planejado) e confirmar
que o rateio proporcional aparece corretamente como sugestão" + o caso de
ponta a ponta com prazo 1, pelas rotas reais (SaaS e app), com a regra
"sem confirmação" (D79 (4)).

Tudo passa pelas rotas: gerar, editar e aprovar a ordem; registrar a
produção; gerar, editar e aprovar o romaneio; saída; confirmar no app;
gerar a ordem seguinte; consultar o romaneio e as divergências. Direto no
banco só o cenário (cadastro, previsão, contagem) e o PASSAR DOS DIAS: as
rotas usam o relógio de verdade e não geram ordem para o passado, então,
depois do fluxo, as datas e horas das ordens O1 e O2 são recuadas 2 dias,
como se tivessem acontecido antes de hoje. Precisa que a data local (São
Paulo) seja a do servidor: num servidor em UTC, entre 21h e 0h locais o
teste avisa e para (no Windows do Ualker, com o fuso local, sempre vale).

Cenário (hoje = H, data do servidor): central C (prazo 1), lojas 001 e
002, produto P (UN, validade 5, todo dia, margem 10%). Previsão 10 por dia
-> cobertura de 1 dia, alvo 11; com prazo 1 a loja vende 10 em D antes da
chegada (D45). Necessidade = 11 − (contagem + trânsito + recebido depois
da contagem − 10), no mínimo 0.

Conta à mão:
  O1 (produção H, entrega H+1), contagem 001 15 e 002 0, sem trânsito:
     001 11 − (15 − 10) = 6 · 002 11 − 0 = 11. O gestor muda a 002 para 13.
     Produção 10 (< 19): rateio pela FINAL (D70) 10×6/19 = 3,16 e
     10×13/19 = 6,84 -> 3 e 6 + 1 para o maior resto -> 3 / 7 (pela
     sugerida 6/11 daria 4 / 6). Mudar a 002 para 8 (Σ 11 > 10) -> não
     aprova. Saída das duas; a 001 confirma 2 (falta 1); a 002 não confirma.
  O2 (produção H+1, entrega H+2): finais 9 / 9; produção 12 -> 6 / 6
     (pela ordem seria 9 / 9). Saída das duas.
  Os dias passam: O1 vira produção H−2, entrega H−1 (a 002 terminou o dia
     de entrega sem confirmar; ainda pode confirmar hoje, D85); O2 vira
     produção H−1, entrega H. A entrega de H−1 está na janela do provedor
     de trânsito (desde D−1): é ali que a conta em dobro apareceria.
     Contagem nova, 10 nas duas (agora). Depois dela a 001 confirma a O2
     com 4 (falta 2).
  O3 (produção H, chegada H+1):
     001 10 + 4 (recebida da O2 depois da contagem) − 10 = 4 -> 7
         (recebimento ignorado: 11; pela final do romaneio, 6: 5)
     002 10 + 6 (trânsito da O2 pela final do ROMANEIO) − 10 = 6 -> 5
         (trânsito pela ordem, 9: 2). A entrega da O1 sem confirmação é
         presumida pela final do romaneio (7), FORA do trânsito, com a
         marca "sem confirmação" (contada em dobro: 10+6+7−10 -> 0).

Casos:
  F1  O1 pela rota: sugeridas 6 e 11, sem marcas
  F2  editar a 002 para 13 e aprovar a ordem
  F3  produção parcial: o romaneio sugere o rateio proporcional pela final
      (3 / 7), com o produto em escassez (critério de aceite do doc)
  F4  Σ das finais > produzido -> não aprova (422); de volta a 7 -> aprova
  F5  saída das duas; cada loja vê no app só a sua entrega (3 e 7)
  F6  a 001 confirma a O1 com diferença (2, falta)
  F7  O2: finais 9/9, produção 12 -> romaneio 6/6, aprovado e saído
  F8  depois dos dias: a 001 confirma a O2 (4, falta); a 002 vê no app a O1
      (ainda no prazo da confirmação atrasada, D85) e a O2
  F9  O3, loja 001: necessidade 7 pela recebida depois da contagem
  F10 O3, loja 002: necessidade 5 pelo trânsito da O2 pela final do romaneio
  F11 "sem confirmação": marca e presumida 7 na linha da 002, fora do
      trânsito; nada na 001; o romaneio da O1 mostra a 002 "sem
      confirmação" (ainda pode confirmar) e a 001 "recebida" com diferença
  F12 divergências do período: 001 na O1 (3 -> 2) e na O2 (6 -> 4)

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_aceite_fase5.py
"""

import sys
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.security import PORTA_WEB, criar_access_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.calendario_producao import CalendarioProducao, DiaSemana  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.estoque_atual import EstoqueAtual  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.ordem_producao import OrdemProducao  # noqa: E402
from app.models.ordem_producao_item import OrdemProducaoItem  # noqa: E402
from app.models.ordem_producao_linha import OrdemProducaoLinha  # noqa: E402
from app.models.previsao_diaria import EstatisticaBase, MetodoPrevisao, PrevisaoDiaria  # noqa: E402
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.romaneio import Romaneio  # noqa: E402
from app.models.romaneio_entrega import RomaneioEntrega  # noqa: E402
from app.models.romaneio_item import RomaneioItem  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402
from app.services.recebimento_service import dia_local  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 12
PREFIXO_NEGOCIO_TESTE = "_Teste Aceite Fase 5"
DEC = Decimal
H = date.today()  # a mesma "hoje" das rotas

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


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    lojas = [i for (i,) in db.query(Loja.id).filter(Loja.negocio_id.in_(negocio_ids))]
    db.query(Romaneio).filter(Romaneio.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (RomaneioItem, RomaneioEntrega):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(OrdemProducao).filter(OrdemProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (OrdemProducaoLinha, OrdemProducaoItem, PrevisaoDiaria, EstoqueAtual, CalendarioProducao):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    if lojas:
        db.query(ProdutoLoja).filter(ProdutoLoja.loja_id.in_(lojas)).delete(synchronize_session=False)
    for modelo in (Usuario, Produto, Loja, CentralProducao):
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


def _recuar(db, ordem_id, dias):
    """O passar dos dias: recua as datas e as horas da ordem, do romaneio e das entregas."""
    # A ordem e o romaneio mudam no mesmo comando: a FK fk_romaneio_ordem_coerente (com a data de
    # entrega) é conferida no fim de cada comando.
    db.execute(text(
        "WITH r AS (UPDATE romaneios SET data_entrega = data_entrega - :d, gerado_em = gerado_em - :iv, "
        "aprovado_em = aprovado_em - :iv WHERE ordem_id = :o RETURNING id) "
        "UPDATE ordens_producao SET data_producao = data_producao - :d, data_entrega = data_entrega - :d, "
        "gerado_em = gerado_em - :iv, aprovado_em = aprovado_em - :iv WHERE id = :o"
    ), {"d": dias, "iv": timedelta(days=dias), "o": ordem_id})
    db.execute(text(
        "UPDATE romaneios_entregas SET expedido_em = expedido_em - :iv, recebido_em = recebido_em - :iv "
        "WHERE romaneio_id IN (SELECT id FROM romaneios WHERE ordem_id = :o)"
    ), {"iv": timedelta(days=dias), "o": ordem_id})
    db.commit()
    db.expire_all()


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

        neg = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run}", ativo=True))
        negocio_ids = [neg.id]
        c = add(CentralProducao(negocio_id=neg.id, nome="_C", ativa=True, prazo_entrega_dias=1))
        lojas = {cod: add(Loja(negocio_id=neg.id, central_producao_id=c.id, nome=f"_Loja {cod}", codigo=cod,
                               horario_zeragem=time(6, 0), ativo=True)) for cod in ("001", "002")}

        def usuario(rotulo, **campos):
            return add(Usuario(negocio_id=neg.id, nome=f"_U {rotulo}", email=f"taf5_{rotulo}_{run}@teste.com",
                               senha_hash=hash_senha("x"), **campos))

        gestor = usuario("gestor", tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=c.id,
                         tem_acesso_app=False, tem_acesso_web=True)
        ops = {cod: usuario(f"op{cod}", tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=lj.id, tem_acesso_app=True,
                            tem_acesso_web=False) for cod, lj in lojas.items()}
        p = add(Produto(negocio_id=neg.id, nome="_Produto P", codigo="P", ativo=True, unidade_medida=UnidadeMedida.UN,
                        dias_validade=5, tipo_abastecimento=TipoAbastecimento.PRODUZIDO))
        for d in DiaSemana:
            db.add(CalendarioProducao(negocio_id=neg.id, produto_id=p.id, dia_semana=d))
        estoques = {}
        for cod, lj in lojas.items():
            db.add(ProdutoLoja(produto_id=p.id, loja_id=lj.id))
            for k in range(0, 6):
                db.add(PrevisaoDiaria(
                    negocio_id=neg.id, central_producao_id=c.id, loja_id=lj.id, produto_id=p.id,
                    data=H + timedelta(days=k), data_referencia=H - timedelta(days=1), previsao=DEC(10),
                    metodo=MetodoPrevisao.SEMANAL, estatistica=EstatisticaBase.MEDIANA, semanas_na_base=6,
                    tendencia=DEC(1), dias_na_tendencia=7, peso_historico=DEC(1), versao_metodo="teste"))
            estoques[cod] = add(EstoqueAtual(negocio_id=neg.id, loja_id=lj.id, produto_id=p.id,
                                             quantidade_inventariada=0, estoque_atual_calculado=DEC(0),
                                             atualizado_em=datetime.utcnow()))
        db.commit()

        def contar(quantidades):
            """Contagem do fechamento, feita agora (a hora do app é UTC sem fuso)."""
            for cod, q in quantidades.items():
                e = estoques[cod]
                e.quantidade_inventariada = q
                e.estoque_atual_calculado = DEC(q)
                e.atualizado_em = datetime.utcnow() - timedelta(minutes=5)
            db.commit()

        tg = {"Authorization": f"Bearer {criar_access_token(gestor.id, gestor.negocio_id, porta=PORTA_WEB)}"}
        to = {cod: {"Authorization": f"Bearer {criar_access_token(u.id, u.negocio_id)}"} for cod, u in ops.items()}

        def web(metodo, url, **kw):
            return getattr(cliente, metodo)(url, headers=tg, **kw)

        def gerar_ordem(dia):
            r = web("post", "/producao/ordens/gerar", json={"data_producao": dia.isoformat()})
            if r.status_code != 200:
                raise RuntimeError(f"gerar ordem {dia}: {r.status_code} {detalhe(r)}")
            return corpo(r)["ordem_id"]

        def linhas_da_ordem(ordem_id):
            b = corpo(web("get", f"/producao/ordens/{ordem_id}"))
            return {ln["loja"]["codigo"]: ln for it in b["itens"] for ln in it["linhas"]}, b

        def romaneio(rom_id):
            b = corpo(web("get", f"/distribuicao/romaneios/{rom_id}"))
            return {e["loja"]["codigo"]: e for e in b["entregas"]}, b

        def finais_rom(entregas, campo="quantidade_final"):
            return {cod: str(DEC(e["itens"][0][campo]).normalize()) for cod, e in sorted(entregas.items())}

        def produzir_e_gerar(ordem_id, quantidade):
            _, ordem = linhas_da_ordem(ordem_id)
            r = web("post", f"/distribuicao/ordens/{ordem_id}/producao",
                    json={"itens": [{"item_id": ordem["itens"][0]["id"], "quantidade": str(quantidade)}]})
            if r.status_code != 200:
                raise RuntimeError(f"produção: {r.status_code} {detalhe(r)}")
            return web("post", "/distribuicao/romaneios/gerar", json={"ordem_id": ordem_id})

        def lista_app(cod):
            r = cliente.get("/recebimentos", headers=to[cod])
            return [(e["data_entrega"], [str(DEC(i["quantidade_expedida"]).normalize()) for i in e["itens"]])
                    for e in corpo(r)] if r.status_code == 200 else r.status_code

        def confirmar(cod, entrega, recebida, motivo="falta"):
            item = entrega["itens"][0]["id"]
            return cliente.post(f"/recebimentos/{entrega['id']}/confirmar", headers=to[cod], json={"diferencas": [
                {"item_id": item, "quantidade_recebida": str(recebida), "motivo": motivo}]})

        # ---------------- O1 ----------------
        contar({"001": 15, "002": 0})
        o1 = gerar_ordem(H)
        ln1, _ = linhas_da_ordem(o1)
        sug = {k: str(DEC(v["quantidade_sugerida"]).normalize()) for k, v in sorted(ln1.items())}
        registrar("F1 O1 pela rota: sugeridas pela conta a mao", sug == {"001": "6", "002": "11"}
                  and not any(v["avisos"] for v in ln1.values()), f"{sug}; avisos {[v['avisos'] for v in ln1.values()]}")

        r_ed = web("patch", f"/producao/ordens/{o1}/linhas/{ln1['002']['id']}",
                   json={"quantidade_final": "13", "motivo": "festa no bairro"})
        r_ap = web("post", f"/producao/ordens/{o1}/aprovar")
        registrar("F2 editar a 002 para 13 e aprovar", r_ed.status_code == 200 and r_ap.status_code == 200
                  and corpo(r_ap)["status"] == "aprovada", f"editar {r_ed.status_code}; aprovar {r_ap.status_code} "
                  f"{corpo(r_ap).get('status') if isinstance(corpo(r_ap), dict) else detalhe(r_ap)}")

        r = produzir_e_gerar(o1, 10)
        rom1 = corpo(r)["romaneio_id"] if r.status_code == 200 else None
        ent1, _ = romaneio(rom1) if rom1 else ({}, {})
        registrar("F3 producao parcial: rateio proporcional pela final como sugestao",
                  r.status_code == 200 and corpo(r)["produtos_com_escassez"] == [p.id]
                  and finais_rom(ent1, "quantidade_sugerida") == {"001": "3", "002": "7"}
                  and finais_rom(ent1) == {"001": "3", "002": "7"},
                  f"{r.status_code}; sugerida {finais_rom(ent1, 'quantidade_sugerida') if ent1 else '-'} "
                  f"(pela sugerida da ordem seria 4/6); escassez {corpo(r).get('produtos_com_escassez')}")

        item_002 = ent1["002"]["itens"][0]["id"]
        url1 = f"/distribuicao/romaneios/{rom1}"
        web("patch", f"{url1}/itens/{item_002}", json={"quantidade_final": "8"})
        r_mais = web("post", f"{url1}/aprovar")
        status_depois = corpo(web("get", url1))["status"]
        web("patch", f"{url1}/itens/{item_002}", json={"quantidade_final": "7"})
        r_ok = web("post", f"{url1}/aprovar")
        registrar("F4 soma maior que o produzido nao aprova",
                  r_mais.status_code == 422 and status_depois == "rascunho" and r_ok.status_code == 200,
                  f"com 3+8=11 > 10: {r_mais.status_code} {detalhe(r_mais)[:70]} (continua {status_depois}); "
                  f"com 7: {r_ok.status_code}")

        r = web("post", f"{url1}/saida")
        entrega_h1 = (H + timedelta(days=1)).isoformat()
        apps = {cod: lista_app(cod) for cod in lojas}
        registrar("F5 saida e cada loja ve a sua entrega",
                  r.status_code == 200 and len(corpo(r)["entregas"]) == 2
                  and apps == {"001": [(entrega_h1, ["3"])], "002": [(entrega_h1, ["7"])]}, f"{r.status_code}; {apps}")

        ent1, _ = romaneio(rom1)
        r = confirmar("001", ent1["001"], 2)
        registrar("F6 a 001 confirma a O1 com diferenca", r.status_code == 200
                  and corpo(r)["situacao"]["com_diferenca"] and lista_app("001") == [],
                  f"{r.status_code} {corpo(r).get('situacao') if isinstance(corpo(r), dict) else detalhe(r)}")

        # ---------------- O2 ----------------
        o2 = gerar_ordem(H + timedelta(days=1))
        ln2, _ = linhas_da_ordem(o2)
        for cod in lojas:
            web("patch", f"/producao/ordens/{o2}/linhas/{ln2[cod]['id']}", json={"quantidade_final": "9"})
        web("post", f"/producao/ordens/{o2}/aprovar")
        r = produzir_e_gerar(o2, 12)
        rom2 = corpo(r)["romaneio_id"] if r.status_code == 200 else None
        r_ap = web("post", f"/distribuicao/romaneios/{rom2}/aprovar")
        r_sd = web("post", f"/distribuicao/romaneios/{rom2}/saida")
        ent2, b2 = romaneio(rom2)
        registrar("F7 O2: romaneio 6/6 aprovado e saido",
                  finais_rom(ent2) == {"001": "6", "002": "6"} and b2["status"] == "aprovado"
                  and r_sd.status_code == 200 and all(e["situacao"]["situacao"] == "a_caminho" for e in ent2.values()),
                  f"romaneio {finais_rom(ent2)} (pela ordem 9/9); {b2['status']}; saida {r_sd.status_code}")

        # ---------------- os dias passam ----------------
        if dia_local(datetime.utcnow()) != H:
            raise RuntimeError("a data local (São Paulo) e a do servidor diferem agora (entre 21h e 0h num servidor "
                               "em UTC); rode o teste de novo depois da meia-noite local")
        _recuar(db, o1, 2)
        _recuar(db, o2, 2)
        contar({"001": 10, "002": 10})
        ent2, _ = romaneio(rom2)
        r = confirmar("001", ent2["001"], 4)
        lista_002 = lista_app("002")
        registrar("F8 depois dos dias: 001 confirma a O2; a 002 ainda pode confirmar a O1 (D85)",
                  r.status_code == 200 and lista_002 == [((H - timedelta(days=1)).isoformat(), ["7"]),
                                                         (H.isoformat(), ["6"])],
                  f"confirmar {r.status_code}; app da 002 {lista_002}")

        # ---------------- O3 ----------------
        o3 = gerar_ordem(H)
        ln3, _ = linhas_da_ordem(o3)
        c1, c2 = ln3["001"]["componentes"], ln3["002"]["componentes"]
        num = lambda v: str(DEC(str(v)).normalize()) if v is not None else None  # noqa: E731
        registrar("F9 001: 10 + 4 recebida depois da contagem - 10 -> 7",
                  num(ln3["001"]["quantidade_sugerida"]) == "7" and num(c1["recebido_apos_contagem"]) == "4"
                  and num(c1["transito_considerado"]) == "0",
                  f"sugerida {num(ln3['001']['quantidade_sugerida'])}; recebido depois "
                  f"{num(c1['recebido_apos_contagem'])}; transito {num(c1['transito_considerado'])}")
        registrar("F10 002: transito da O2 pela final do romaneio (6) -> 5",
                  num(ln3["002"]["quantidade_sugerida"]) == "5" and num(c2["transito_considerado"]) == "6"
                  and num(c2["recebido_apos_contagem"]) == "0",
                  f"sugerida {num(ln3['002']['quantidade_sugerida'])}; transito {num(c2['transito_considerado'])}")

        ent1, _ = romaneio(rom1)
        s1, s2 = ent1["001"]["situacao"], ent1["002"]["situacao"]
        registrar("F11 sem confirmacao: marca, presumida 7 fora do transito",
                  "sem_confirmacao" in ln3["002"]["avisos"] and num(c2.get("recebimento_presumido")) == "7"
                  and "sem_confirmacao" not in ln3["001"]["avisos"]
                  and s2 == {"situacao": "sem_confirmacao", "pode_confirmar": True, "com_diferenca": False}
                  and s1["situacao"] == "recebida" and s1["com_diferenca"],
                  f"002 avisos {ln3['002']['avisos']} presumida {num(c2.get('recebimento_presumido'))}; "
                  f"001 avisos {ln3['001']['avisos']}; O1: 001 {s1}, 002 {s2}")

        r = web("get", "/distribuicao/divergencias", params={"data_inicio": (H - timedelta(days=7)).isoformat(),
                                                              "data_fim": H.isoformat()})
        div = sorted((d["data_entrega"], d["loja"]["codigo"], num(d["quantidade_enviada"]),
                      num(d["quantidade_recebida"]), num(d["diferenca"]), d["motivo"])
                     for d in corpo(r).get("divergencias", [])) if r.status_code == 200 else r.status_code
        registrar("F12 divergencias do periodo",
                  div == [((H - timedelta(days=1)).isoformat(), "001", "3", "2", "-1", "falta"),
                          (H.isoformat(), "001", "6", "4", "-2", "falta")], f"{r.status_code} {div}")
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do aceite da Fase 5 (E9) ===")
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
