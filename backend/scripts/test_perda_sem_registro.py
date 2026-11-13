"""
Testa a perda sem registro e a ruptura (D111, segunda parte).

Parte pura (sem banco):
  P1 balanço: 10 + 18 − 15 − 1 − 8 = 4, sem ruptura
  P2 ruptura: fechou com 0 e vendeu; fechou com 0 sem venda não é ruptura
  P3 janela do fechamento (fechamento 21:00, hora de São Paulo): 19:00 e
     21:30 de D e 08:59 de D+1 são de D; 18:59 de D e 09:00 de D+1 não são
     de dia nenhum (contagem no meio do dia)
  P4 o lançamento mais tarde da janela vale; o mesmo lançamento repetido em
     vários snapshots conta uma vez
  P5 montar: sem a contagem de ontem ou sem venda na loja no dia, não há
     balanço; produto sem linha de venda (com a loja vendendo) = vendeu 0

Parte com banco e HTTP (GET /web/acompanhamento), período D1–D3:
  loja 001 (central A1, fechamento 21:00), produto PA (UN)
  contagens (hora local; gravadas em UTC como o app grava):
    D0 21:00 = 10 (snapshot), D1 21:00 = 8 (snapshot, repetido em dois),
    D2 21:30 = 0 (snapshot e linha atual), D3 21:00 = 5 (linha atual);
    D2 14:00 = 99 (meio do dia, fica de fora)
  recebido: D1 entrega recebida (enviado 20, recebido 18) -> 18;
            D2 entrega expedida sem confirmação (enviado 5) -> 5 (D89);
            D3 entrega aguardando saída (7) -> não conta
  venda: D1 = 15 (api; manual 50 no mesmo dia fica de reserva), D2 = 12;
         D3 sem venda nenhuma na loja
  perda lançada: D1 = 1
  loja 201 (outra central, mesmo negócio) e negócio B: contagens e vendas
  que não podem aparecer
  H1 UN: sem_registro = 4 (D1) + 1 (D2) = 5; balancos 2; rupturas 1
  H2 dia a dia: D1 4, D2 1, D3 None (sem venda na loja)
  H3 produto PA: balancos 2, rupturas 1, sem_registro 5
  H4 filtro loja 001 dá o mesmo; gestor do negócio B não vê nada
  Z1 lançar contagem grava contado_em e a zeragem copia para o histórico
     (e não muda contado_em)

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_perda_sem_registro.py
"""

import sys
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import PORTA_WEB, criar_access_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.estoque_atual import EstoqueAtual  # noqa: E402
from app.models.historico_contagem import HistoricoContagem  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.ordem_producao import OrdemProducao, StatusOrdemProducao  # noqa: E402
from app.models.ordem_producao_item import OrdemProducaoItem  # noqa: E402
from app.models.ordem_producao_linha import OrdemProducaoLinha  # noqa: E402
from app.models.perda_diaria import OrigemPerda, PerdaDiaria  # noqa: E402
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.romaneio import Romaneio, StatusRomaneio  # noqa: E402
from app.models.romaneio_entrega import RomaneioEntrega, SituacaoEntrega  # noqa: E402
from app.models.romaneio_item import MotivoDivergencia, RomaneioItem  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402
from app.services import perda_sem_registro_service as svc  # noqa: E402
from app.services.estoque_service import aplicar_contagem  # noqa: E402
from app.services.zeragem_service import zerar_loja  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 10
PREFIXO_NEGOCIO_TESTE = "_Teste Perda sem registro"
DEC = Decimal
D0, D1, D2, D3 = date(2026, 10, 4), date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)
FECHA = time(21, 0)

cliente = TestClient(app, raise_server_exceptions=False)
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def utc(dia: date, hora: int, minuto: int = 0) -> datetime:
    """Hora local de São Paulo (UTC−3, sem horário de verão) -> UTC sem fuso, como o banco guarda."""
    return datetime.combine(dia, time(hora, minuto)) + timedelta(hours=3)


def n(valor):
    return None if valor is None else DEC(str(valor)).normalize()


# ------------------------------------------------------------------ parte pura

def parte_pura():
    b = svc.balanco(10, 18, 15, 1, 8)
    registrar("P1 balanco 10+18-15-1-8 = 4", (b.sem_registro, b.ruptura) == (DEC(4), False), f"{b}")

    r1, r2 = svc.balanco(8, 5, 12, 0, 0), svc.balanco(3, 0, 0, 0, 0)
    registrar("P2 ruptura so com venda", (r1.ruptura, r2.ruptura) == (True, False), f"{r1.ruptura} {r2.ruptura}")

    casos = [(utc(D1, 19), D1), (utc(D1, 21, 30), D1), (utc(D2, 8, 59), D1), (utc(D1, 18, 59), None),
             (utc(D2, 9), None)]
    obtidos = [svc.dia_do_fechamento(t, FECHA) for t, _ in casos]
    registrar("P3 janela do fechamento", obtidos == [e for _, e in casos], f"{obtidos}")

    lanc = [(1, 7, utc(D1, 21), DEC(4)), (1, 7, utc(D2, 7), DEC(6)), (1, 7, utc(D2, 7), DEC(6)),
            (1, 7, utc(D2, 14), DEC(99))]
    f = svc.fechamentos(lanc, {1: FECHA})
    registrar("P4 vale o lancamento mais tarde da janela", f == {(1, 7, D1): DEC(6)}, f"{f}")

    contagens = {(1, 7, D0): DEC(10), (1, 7, D1): DEC(8), (1, 8, D1): DEC(2), (1, 8, D0): DEC(3),
                 (1, 7, D3): DEC(1)}
    m = svc.montar(D1, D3, contagens, {}, {(1, 7, D1): DEC(2)}, {}, {(1, D1)})
    esperado = {(1, 7, D1): DEC(0), (1, 8, D1): DEC(1)}  # D3 sem abertura; produto 8 sem venda = 0
    obtido = {c: b.sem_registro for c, b in m.items()}
    registrar("P5 montar (abertura, venda na loja, produto sem venda = 0)", obtido == esperado, f"{obtido}")


# ------------------------------------------------------------------ banco

def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    db.query(Romaneio).filter(Romaneio.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (RomaneioItem, RomaneioEntrega):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(OrdemProducao).filter(OrdemProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (OrdemProducaoLinha, OrdemProducaoItem, VendaDiaria, PerdaDiaria, HistoricoContagem,
                   EstoqueAtual):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    lojas = [x for (x,) in db.query(Loja.id).filter(Loja.negocio_id.in_(negocio_ids))]
    if lojas:
        db.query(ProdutoLoja).filter(ProdutoLoja.loja_id.in_(lojas)).delete(synchronize_session=False)
    for modelo in (Usuario, Produto, Loja, CentralProducao):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Negocio).filter(Negocio.id.in_(negocio_ids)).delete(synchronize_session=False)
    db.commit()


def _limpar_residuos():
    db = SessionLocal()
    try:
        negocios = [x for x in db.query(Negocio).all() if x.nome.startswith(PREFIXO_NEGOCIO_TESTE + " ")]
        if negocios:
            print(f"[limpeza inicial] Apagando {len(negocios)} negócio(s) de execuções anteriores.")
            _limpar(db, [x.id for x in negocios])
        else:
            print("[limpeza inicial] Nenhum resíduo de teste encontrado.")
    finally:
        db.close()


def parte_banco():
    db = SessionLocal()
    negocio_ids = []
    try:
        run = uuid.uuid4().hex[:8]

        def add(obj):
            db.add(obj)
            db.flush()
            return obj

        neg = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} A", ativo=True))
        neg_b = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} B", ativo=True))
        negocio_ids = [neg.id, neg_b.id]
        a1 = add(CentralProducao(negocio_id=neg.id, nome="_A1", ativa=True))
        a2 = add(CentralProducao(negocio_id=neg.id, nome="_A2", ativa=True))
        cb = add(CentralProducao(negocio_id=neg_b.id, nome="_B", ativa=True))

        def loja(codigo, ng, central):
            return add(Loja(negocio_id=ng.id, central_producao_id=central.id, nome=f"_Loja {codigo}", codigo=codigo,
                            horario_zeragem=time(6, 0), horario_fechamento=FECHA, ativo=True))

        l1, l201, lb = loja("001", neg, a1), loja("201", neg, a2), loja("B1", neg_b, cb)
        g = add(Usuario(negocio_id=neg.id, nome="_G", email=f"tpsr_g_{run}@teste.com", senha_hash=hash_senha("x"),
                        tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=a1.id, tem_acesso_app=False,
                        tem_acesso_web=True))
        gb = add(Usuario(negocio_id=neg_b.id, nome="_GB", email=f"tpsr_gb_{run}@teste.com", senha_hash=hash_senha("x"),
                         tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=cb.id, tem_acesso_app=False,
                         tem_acesso_web=True))
        pa = add(Produto(negocio_id=neg.id, nome="_Produto PA", codigo="PA", unidade_medida=UnidadeMedida.UN,
                         ativo=True, tipo_abastecimento=TipoAbastecimento.PRODUZIDO))
        pz = add(Produto(negocio_id=neg_b.id, nome="_Produto PZ", codigo="PZ", unidade_medida=UnidadeMedida.UN,
                         ativo=True, tipo_abastecimento=TipoAbastecimento.PRODUZIDO))

        def snap(ng, lj, p, contado, valor, ref):
            add(HistoricoContagem(negocio_id=ng.id, loja_id=lj.id, produto_id=p.id, quantidade_inventariada=int(valor),
                                  estoque_atual_calculado=DEC(valor), contado_em=contado, data_referencia=ref))

        snap(neg, l1, pa, utc(D0, 21), 10, datetime.combine(D1, time(6)))
        snap(neg, l1, pa, utc(D1, 21), 8, datetime.combine(D2, time(6)))
        snap(neg, l1, pa, utc(D1, 21), 8, datetime.combine(D2, time(6, 1)))  # o mesmo lançamento, repetido
        snap(neg, l1, pa, utc(D2, 14), 99, datetime.combine(D2, time(15)))  # meio do dia: fora
        snap(neg, l1, pa, utc(D2, 21, 30), 0, datetime.combine(D3, time(6)))
        add(EstoqueAtual(negocio_id=neg.id, loja_id=l1.id, produto_id=pa.id, quantidade_inventariada=5,
                         estoque_atual_calculado=DEC(5), contado_em=utc(D3, 21)))
        for ng, lj, p in ((neg, l201, pa), (neg_b, lb, pz)):  # fora do escopo do gestor A1
            snap(ng, lj, p, utc(D0, 21), 500, datetime.combine(D1, time(6)))
            snap(ng, lj, p, utc(D1, 21), 0, datetime.combine(D2, time(6)))

        def venda(ng, lj, p, dia, valor, origem="manual"):
            add(VendaDiaria(negocio_id=ng.id, loja_id=lj.id, produto_id=p.id, data=dia, quantidade=DEC(valor),
                            origem=OrigemVenda(origem)))

        venda(neg, l1, pa, D1, 50)
        venda(neg, l1, pa, D1, 15, "api")
        venda(neg, l1, pa, D2, 12)
        venda(neg, l201, pa, D1, 1)
        venda(neg_b, lb, pz, D1, 1)
        add(PerdaDiaria(negocio_id=neg.id, loja_id=l1.id, produto_id=pa.id, data=D1, quantidade=DEC(1),
                        origem=OrigemPerda.MANUAL))

        agora = datetime(2026, 10, 1, 12, 0)

        def entrega(dia, situacao, enviado, recebido=None):
            o = add(OrdemProducao(negocio_id=neg.id, central_producao_id=a1.id, data_producao=dia - timedelta(days=1),
                                  data_entrega=dia, versao_metodo="teste", gerado_em=agora,
                                  status=StatusOrdemProducao.APROVADA, aprovado_em=agora, aprovado_por_usuario_id=g.id))
            item = add(OrdemProducaoItem(negocio_id=neg.id, ordem_id=o.id, produto_id=pa.id,
                                         tipo_abastecimento=pa.tipo_abastecimento, unidade=pa.unidade_medida))
            linha = add(OrdemProducaoLinha(negocio_id=neg.id, item_id=item.id, loja_id=l1.id,
                                           quantidade_sugerida=DEC(enviado), quantidade_final=DEC(enviado)))
            rom = add(Romaneio(negocio_id=neg.id, central_producao_id=a1.id, ordem_id=o.id, data_entrega=dia,
                               status=StatusRomaneio.APROVADO, gerado_em=agora, aprovado_em=agora,
                               aprovado_por_usuario_id=g.id))
            saiu = situacao != SituacaoEntrega.AGUARDANDO_SAIDA
            chegou = situacao == SituacaoEntrega.RECEBIDA
            ent = add(RomaneioEntrega(negocio_id=neg.id, romaneio_id=rom.id, loja_id=l1.id, situacao=situacao,
                                      expedido_em=agora if saiu else None,
                                      expedido_por_usuario_id=g.id if saiu else None,
                                      recebido_em=agora if chegou else None,
                                      recebido_por_usuario_id=g.id if chegou else None))
            add(RomaneioItem(negocio_id=neg.id, entrega_id=ent.id, produto_id=pa.id, ordem_linha_id=linha.id,
                             unidade=pa.unidade_medida, quantidade_sugerida=DEC(enviado),
                             quantidade_final=DEC(enviado),
                             quantidade_recebida=None if recebido is None else DEC(recebido),
                             motivo_divergencia=MotivoDivergencia.FALTA
                             if recebido is not None and recebido != enviado else None))

        entrega(D1, SituacaoEntrega.RECEBIDA, 20, 18)
        entrega(D2, SituacaoEntrega.EXPEDIDA, 5)
        entrega(D3, SituacaoEntrega.AGUARDANDO_SAIDA, 7)
        db.commit()

        tg = criar_access_token(g.id, g.negocio_id, porta=PORTA_WEB)
        tgb = criar_access_token(gb.id, gb.negocio_id, porta=PORTA_WEB)

        def get(query, token=tg):
            r = cliente.get(f"/web/acompanhamento?data_inicio={D1}&data_fim={D3}{query}",
                            headers={"Authorization": f"Bearer {token}"})
            return r.status_code, (r.json() if r.status_code == 200 else r.text)

        status, b = get("")
        un = next((u for u in b.get("unidades", []) if u["unidade"] == "UN"), {}) if status == 200 else {}
        registrar("H1 UN: sem_registro 5, balancos 2, rupturas 1",
                  (n(un.get("totais", {}).get("sem_registro")), un.get("balancos"), un.get("rupturas"))
                  == (DEC(5), 2, 1), f"{status} {un.get('totais')} {un.get('balancos')} {un.get('rupturas')}")
        dias = {d["data"]: n(d["sem_registro"]) for d in un.get("dias", [])}
        registrar("H2 dia a dia: D1 4, D2 1, D3 None",
                  dias == {str(D1): DEC(4), str(D2): DEC(1), str(D3): None}, f"{dias}")
        prod = next((p for p in b.get("produtos", []) if p["produto"]["codigo"] == "PA"), {}) if status == 200 else {}
        registrar("H3 produto PA", (prod.get("balancos"), prod.get("rupturas"), n(prod.get("totais", {}).get(
            "sem_registro"))) == (2, 1, DEC(5)), f"{prod.get('balancos')} {prod.get('rupturas')}")

        s_loja, b_loja = get(f"&loja_id={l1.id}")
        un_loja = next((u for u in b_loja.get("unidades", []) if u["unidade"] == "UN"), {}) if s_loja == 200 else {}
        s_b, b_b = get("", token=tgb)
        # O gestor B vê só a própria loja (500 − 1 − 0 = 499), nada do negócio A.
        nada_b = s_b == 200 and [(n(u["totais"]["sem_registro"]), u["balancos"]) for u in b_b["unidades"]] \
            == [(DEC(499), 1)]
        registrar("H4 filtro de loja igual; negocio B so ve o proprio",
                  n(un_loja.get("totais", {}).get("sem_registro")) == DEC(5) and un_loja.get("rupturas") == 1
                  and nada_b, f"{s_loja} {un_loja.get('totais', {}).get('sem_registro')} {s_b} {b_b}")

        # ---- Z1: o app grava contado_em e a zeragem copia sem mudar ----
        add(ProdutoLoja(loja_id=lb.id, produto_id=pz.id, ativo=True))
        db.commit()
        est = aplicar_contagem(db, neg_b.id, lb.id, pz.id, 7)
        contado = est.contado_em
        zerar_loja(db, db.get(Loja, lb.id), datetime.now())
        ultimo = (db.query(HistoricoContagem).filter(HistoricoContagem.loja_id == lb.id)
                  .order_by(HistoricoContagem.id.desc()).first())
        db.refresh(est)
        registrar("Z1 contagem grava contado_em; zeragem copia e nao muda",
                  contado is not None and ultimo.contado_em == contado and est.contado_em == contado
                  and est.quantidade_inventariada == 0, f"{contado} {ultimo.contado_em} {est.contado_em}")
    finally:
        db.rollback()
        _limpar(db, negocio_ids)
        db.close()


def main():
    parte_pura()
    _limpar_residuos()
    parte_banco()
    print()
    for linha in resultados:
        print(linha)
    falhas = [r for r in resultados if r.startswith(FAIL)]
    print()
    if len(resultados) != TOTAL_CASOS:
        print(f"Esperados {TOTAL_CASOS} casos, rodaram {len(resultados)}.")
        sys.exit(1)
    if falhas:
        print(f"{len(falhas)}/{TOTAL_CASOS} casos FALHARAM")
        sys.exit(1)
    print(f"{TOTAL_CASOS}/{TOTAL_CASOS} casos OK")


if __name__ == "__main__":
    main()
