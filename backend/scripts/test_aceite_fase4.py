"""
Critério de aceite da Fase 4 (doc §8): "rodar gerar-ordem-do-dia numa
central de teste com 2+ lojas produz uma ordem_producao com itens
agregados corretamente, respeitando produtos inativos/fora de vigência".

De ponta a ponta, pela rota real (`POST /producao/ordens/gerar`, padrão
amanhã), com a data de hoje do servidor: vendas -> previsão (o motor da
Fase 3 roda sozinho porque não há previsão gravada, D41) -> necessidade ->
ordem -> aprovação. Negócio de teste isolado, apagado no fim.

Vendas CONSTANTES por 8 semanas até ontem, para a conta à mão ser exata:
mediana de valores iguais = o valor; tendência = 1; histórico completo
(sem cold start). Margem padrão 10% (D34). Fuso America/Sao_Paulo.

Central A (prazo 0): L1 e L2 ativas, L3 inativa. Central B: LB.
Produtos (habilitados em todas as lojas; venda por dia na L1 / L2):
  PA Pão           produzido, diário, validade 1     40 / 20
  PB Bolo          produzido, D, D+2 e D+4, valid. 3 10 / 6   (L1 contou 5)
  PC Manteiga      distribuído, diário, validade 30   8 / 4
  PD Sonho         produzido, diário, desabilitado na L2   15 / 15
  PI Inativo       inativo no catálogo                 9 / 9
  PV Fora vigência vigência terminou hoje              9 / 9
  PN Não é do dia  calendário sem o dia D              9 / 9

Conta à mão (necessidade = previsão da cobertura × 1,10 − estoque,
UN para cima):
  PA  L1 40 × 1,1 = 44          L2 20 × 1,1 = 22         total 66
  PB  L1 (10 + 10) × 1,1 = 22 − 5 contados = 17
      L2 (6 + 6) × 1,1 = 13,2 -> 14                      total 31
      (cobertura D e D+1: a próxima produção é D+2; validade 3 cobre)
  PC  L1 8 × 1,1 = 8,8 -> 9     L2 4 × 1,1 = 4,4 -> 5    total 14 (distribuído)
  PD  L1 15 × 1,1 = 16,5 -> 17  (L2 desabilitada)        total 17
Fora da ordem: PI (inativo), PV (fora da vigência em D), PN (D não é dia
de produção), L3 (inativa), LB (outra central).

Casos:
  F1 POST /producao/ordens/gerar -> 200; previsão atualizada pelo motor
     (D41); 4 itens, 7 linhas, nenhuma sem quantidade
  F2 o motor gravou a previsão exata (PA/L1 em D = 40)
  F3 cada uma das 7 linhas com o número da conta à mão
  F4 itens agregados: totais por produto 66 / 31 / 14 / 17 (D54), e o PC
     como distribuído
  F5 fora da ordem: PI, PV, PN, L3 e LB
  F6 a conta gravada do PB/L1: cobertura de 2 dias, mínimo 20, estoque 5
  F7 aprovar -> aprovada; gerar de novo o mesmo dia -> 409

Uso: python scripts/test_aceite_fase4.py
"""

import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

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
from app.models.previsao_diaria import PrevisaoDiaria  # noqa: E402
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 7
PREFIXO_NEGOCIO_TESTE = "_Teste Aceite Fase4"
DEC = Decimal
HOJE = date.today()
D = HOJE + timedelta(days=1)
SEMANAS_VENDA = 8
FUSO = ZoneInfo("America/Sao_Paulo")
DIAS = list(DiaSemana)  # segunda = 0, como date.weekday()

cliente = TestClient(app, raise_server_exceptions=False)
resultados = []

# Linhas esperadas: (produto, loja) -> necessidade (conta à mão no docstring).
ESPERADO = {
    ("PA", "L1"): DEC(44), ("PA", "L2"): DEC(22),
    ("PB", "L1"): DEC(17), ("PB", "L2"): DEC(14),
    ("PC", "L1"): DEC(9), ("PC", "L2"): DEC(5),
    ("PD", "L1"): DEC(17),
}
TOTAIS = {"PA": DEC(66), "PB": DEC(31), "PC": DEC(14), "PD": DEC(17)}


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def corpo(r):
    try:
        return r.json()
    except ValueError:
        return r.text


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    lojas = [i for (i,) in db.query(Loja.id).filter(Loja.negocio_id.in_(negocio_ids))]
    db.query(OrdemProducao).filter(OrdemProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    for modelo in (OrdemProducaoLinha, OrdemProducaoItem, PrevisaoDiaria, EstoqueAtual, VendaDiaria,
                   CalendarioProducao):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    if lojas:
        db.query(ProdutoLoja).filter(ProdutoLoja.loja_id.in_(lojas)).delete(synchronize_session=False)
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


def montar(db):
    run = uuid.uuid4().hex[:8]

    def add(obj):
        db.add(obj)
        db.flush()
        return obj

    neg = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run}", ativo=True))
    a = add(CentralProducao(negocio_id=neg.id, nome="_Central A", ativa=True))
    b = add(CentralProducao(negocio_id=neg.id, nome="_Central B", ativa=True))
    lojas = {}
    for codigo, central, ativa in (("L1", a, True), ("L2", a, True), ("L3", a, False), ("LB", b, True)):
        lojas[codigo] = add(Loja(negocio_id=neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}",
                                 codigo=codigo, horario_zeragem=time(6, 0), ativo=ativa))
    gestor = add(Usuario(negocio_id=neg.id, nome="Gestor Aceite", email=f"taf4_{run}@teste.com",
                         senha_hash=hash_senha("x"), tipo_usuario=TipoUsuario.GESTOR_CENTRAL,
                         central_producao_id=a.id, tem_acesso_web=True, tem_acesso_app=False))

    todos = DIAS
    dias_pb = [DIAS[(D + timedelta(days=k)).weekday()] for k in (0, 2, 4)]
    sem_d = [d for d in DIAS if d != DIAS[D.weekday()]]
    # codigo: (calendário, validade, tipo, ativo, fim da vigência, venda/dia L1, L2)
    definicao = {
        "PA": (todos, 1, TipoAbastecimento.PRODUZIDO, True, None, 40, 20),
        "PB": (dias_pb, 3, TipoAbastecimento.PRODUZIDO, True, None, 10, 6),
        "PC": (todos, 30, TipoAbastecimento.DISTRIBUIDO, True, None, 8, 4),
        "PD": (todos, 1, TipoAbastecimento.PRODUZIDO, True, None, 15, 15),
        "PI": (todos, 1, TipoAbastecimento.PRODUZIDO, False, None, 9, 9),
        "PV": (todos, 1, TipoAbastecimento.PRODUZIDO, True, HOJE, 9, 9),
        "PN": (sem_d, 1, TipoAbastecimento.PRODUZIDO, True, None, 9, 9),
    }
    produtos = {}
    for codigo, (dias, validade, tipo, ativo, fim, v1, v2) in definicao.items():
        p = add(Produto(negocio_id=neg.id, nome=f"_Produto {codigo}", codigo=codigo,
                        unidade_medida=UnidadeMedida.UN, ativo=ativo, dias_validade=validade,
                        tipo_abastecimento=tipo, data_fim_vigencia=fim))
        produtos[codigo] = p
        for d in dias:
            db.add(CalendarioProducao(negocio_id=neg.id, produto_id=p.id, dia_semana=d))
        vendas = {"L1": v1, "L2": v2, "L3": 30, "LB": 50}
        for loja_codigo, loja in lojas.items():
            ativa = not (codigo == "PD" and loja_codigo == "L2")
            db.add(ProdutoLoja(produto_id=p.id, loja_id=loja.id, ativo=ativa))
            for k in range(1, 7 * SEMANAS_VENDA + 1):
                db.add(VendaDiaria(negocio_id=neg.id, loja_id=loja.id, produto_id=p.id,
                                   data=HOJE - timedelta(days=k), quantidade=DEC(vendas[loja_codigo]),
                                   origem=OrigemVenda.MANUAL))
    # Contagem do Bolo na L1 no fechamento de hoje (21:00 local), em UTC como o app grava.
    contagem = datetime.combine(HOJE, time(21, 0), tzinfo=FUSO).astimezone(timezone.utc).replace(tzinfo=None)
    db.add(EstoqueAtual(negocio_id=neg.id, loja_id=lojas["L1"].id, produto_id=produtos["PB"].id,
                        quantidade_inventariada=5, estoque_atual_calculado=DEC(5), atualizado_em=contagem))
    db.commit()
    return neg, a, lojas, produtos, gestor


def main():
    _limpar_residuos()
    db = SessionLocal()
    negocio_ids = []
    try:
        neg, central, lojas, produtos, gestor = montar(db)
        negocio_ids = [neg.id]
        cabecalho = {"Authorization": f"Bearer {criar_access_token(gestor.id, neg.id, porta=PORTA_WEB)}"}

        r = cliente.post("/producao/ordens/gerar", headers=cabecalho)
        b = corpo(r)
        ok = (r.status_code == 200 and b["data_producao"] == str(D) and b["previsao_atualizada"]
              and b["itens"] == 4 and b["linhas"] == 7 and b["sem_quantidade"] == 0)
        registrar("F1 gerar a ordem de amanha", ok, f"{r.status_code} {b}")
        ordem_id = b.get("ordem_id") if isinstance(b, dict) else None

        prev = db.query(PrevisaoDiaria.previsao).filter(
            PrevisaoDiaria.negocio_id == neg.id, PrevisaoDiaria.loja_id == lojas["L1"].id,
            PrevisaoDiaria.produto_id == produtos["PA"].id, PrevisaoDiaria.data == D).scalar()
        registrar("F2 motor gravou a previsao exata", prev == DEC(40), f"PA/L1 em {D:%d/%m} = {prev}")

        det = corpo(cliente.get(f"/producao/ordens/{ordem_id}", headers=cabecalho))
        itens = {i["produto"]["codigo"]: i for i in det.get("itens", [])} if isinstance(det, dict) else {}
        linhas = {(cod, x["loja"]["codigo"]): x for cod, i in itens.items() for x in i["linhas"]}
        obtido = {k: DEC(x["quantidade_sugerida"]) for k, x in linhas.items() if x["quantidade_sugerida"] is not None}
        diferencas = {f"{p}/{l}": (str(obtido.get((p, l))), str(v)) for (p, l), v in ESPERADO.items()
                      if obtido.get((p, l)) != v}
        sobrando = sorted(f"{p}/{l}" for p, l in linhas if (p, l) not in ESPERADO)
        registrar("F3 linhas com a conta a mao", not diferencas and not sobrando and len(linhas) == 7,
                  f"{len(linhas)} linhas" + ("; as 7 esperadas batem" if not diferencas else
                                             f"; (obtido, esperado): {diferencas}")
                  + (f"; linhas a mais: {sobrando}" if sobrando else ""))

        totais = {cod: DEC(i["total_final"]) for cod, i in itens.items()}
        ok = totais == TOTAIS and itens.get("PC", {}).get("tipo_abastecimento") == "distribuido"
        registrar("F4 itens agregados por produto", ok,
                  f"totais={ {k: str(v) for k, v in totais.items()} } PC={itens.get('PC', {}).get('tipo_abastecimento')}")

        fora_produtos = {"PI", "PV", "PN"} & set(itens)
        fora_lojas = {"L3", "LB"} & {loja for _, loja in linhas}
        registrar("F5 inativo, fora de vigencia, fora do dia e lojas de fora", not fora_produtos and not fora_lojas,
                  f"produtos na ordem={sorted(itens)} lojas={sorted({loja for _, loja in linhas})}")

        comp = linhas.get(("PB", "L1"), {}).get("componentes", {})
        ok = (len(comp.get("dias_cobertura") or []) == 2 and DEC(comp.get("minimo") or "0") == DEC(20)
              and DEC(comp.get("estoque_na_chegada") or "0") == DEC(5) and comp.get("contagem_valida") is True)
        registrar("F6 conta gravada do Bolo na L1", ok, f"cobertura={comp.get('dias_cobertura')} "
                  f"minimo={comp.get('minimo')} estoque_na_chegada={comp.get('estoque_na_chegada')}")

        r_ap = cliente.post(f"/producao/ordens/{ordem_id}/aprovar", headers=cabecalho)
        r_de_novo = cliente.post("/producao/ordens/gerar", headers=cabecalho)
        registrar("F7 aprovar e travar", r_ap.status_code == 200 and corpo(r_ap).get("status") == "aprovada"
                  and r_de_novo.status_code == 409, f"aprovar {r_ap.status_code}; gerar de novo {r_de_novo.status_code}")
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Critério de aceite da Fase 4 (gerar a ordem do dia) ===")
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
