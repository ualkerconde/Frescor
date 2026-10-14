"""
Testa a gravação das previsões (Fase 3 / F7, D22): tabela
`previsoes_diarias` (migration 0019) e `gerar_previsoes`.

Cenário (referência 12/10/2026; horizonte 13/10 a 19/10):
  negócio A, central A1: L1 e L2; central A2: L3. Negócio B: LB.
  Categoria (1º nível): P1, P2, P3 = Pães (UN); P4 = Frios (KG); P5 = Bolos (KG).
  L1: P1 10/dia, P2 20/dia, P4 5/dia (56 dias); P3 habilitado, nunca vendeu
  L2: P1 30/dia, P2 20/dia; P5 habilitado, nunca vendeu (sem par KG em L2)
  L3 (A2): P1 10/dia · LB (B): PB 10/dia
  Evento: valor fixo 50 em L1/P1 no dia 14/10.
  -> A1: 7 previsões por dia (L1: P1-P4; L2: P1, P2, P5) × 7 dias = 49.

Casos:
  G01 gera 49 linhas (7 sem previsão: L2/P5) nos 7 dias do horizonte
  G02 cada linha gravada = prever_central (valor e componentes, 4 casas)
  G03 componentes: evento em JSON, previsão sem evento, proxy, mediana,
      versão do método; L2/P5 gravada com previsão NULL
  G04 auditoria: data de referência, quem gerou, quando
  G05 gerar de novo não duplica: 49 linhas, todas substituídas (ids novos)
  G06 dado novo muda a regravação (venda api alta ontem em L2/P2 -> tendência 1,3)
  G07 produto desabilitado na loja some na regravação (não fica linha velha)
  G08 previsões da central A2 e do negócio B ficam intactas
  G09 falha no meio da geração não deixa nada pela metade (vale a anterior)
  G10 horizonte fora de 1 a 7 -> ValueError, nada muda
  G11 horizonte de 3 dias substitui só esses 3 dias
  G12 banco recusa duas previsões para a mesma loja + produto + dia
  G13 banco recusa previsão com loja de outro negócio (FK composta)
  G14 banco recusa previsão negativa e dia previsto antes da referência
  G15 geração simultânea da mesma central espera a outra terminar (trava)

Uso: python scripts/test_previsoes_gravadas.py
"""

import re
import sys
import threading
import uuid
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.core.security import hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.evento import EscopoLoja, EscopoProduto, Evento, EventoLoja, EventoProduto, TipoAjuste  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.nivel_classificacao import NivelClassificacao  # noqa: E402
from app.models.previsao_diaria import PrevisaoDiaria  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.produto_classificacao import ProdutoClassificacao  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402
from app.services import previsao_gravacao  # noqa: E402
from app.services.previsao_gravacao import VERSAO_METODO, gerar_previsoes  # noqa: E402
from app.services.previsao_service import prever_central  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 15
PREFIXO_NEGOCIO_TESTE = "_Teste Previsoes Gravadas"
EMAIL_TESTE = re.compile(r"^tpg_[a-z_0-9]+_[0-9a-f]{8}@teste[.]com$")
D = Decimal
REF = date(2026, 10, 12)
HORIZONTE = [REF + timedelta(days=k) for k in range(1, 8)]
QUATRO = D("0.0001")

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def q(x):
    return None if x is None else D(x).quantize(QUATRO)


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    db.query(PrevisaoDiaria).filter(PrevisaoDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    ev_ids = [e.id for e in db.query(Evento).filter(Evento.negocio_id.in_(negocio_ids))]
    if ev_ids:
        db.query(EventoLoja).filter(EventoLoja.evento_id.in_(ev_ids)).delete(synchronize_session=False)
        db.query(EventoProduto).filter(EventoProduto.evento_id.in_(ev_ids)).delete(synchronize_session=False)
        db.query(Evento).filter(Evento.id.in_(ev_ids)).delete(synchronize_session=False)
    db.query(VendaDiaria).filter(VendaDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    produto_ids = [p.id for p in db.query(Produto).filter(Produto.negocio_id.in_(negocio_ids))]
    if produto_ids:
        db.query(ProdutoLoja).filter(ProdutoLoja.produto_id.in_(produto_ids)).delete(synchronize_session=False)
        db.query(ProdutoClassificacao).filter(ProdutoClassificacao.produto_id.in_(produto_ids)).delete(
            synchronize_session=False)
    db.query(NivelClassificacao).filter(NivelClassificacao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
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
        avulsos = [u for u in db.query(Usuario).filter(Usuario.email.like("tpg_%@teste.com")).all()
                   if EMAIL_TESTE.match(u.email) and u.negocio_id not in [n.id for n in negocios]]
        if not negocios and not avulsos:
            print("[limpeza inicial] Nenhum resíduo de teste encontrado.")
            return
        print("[limpeza inicial] Resíduos de execuções anteriores encontrados:")
        for n in negocios:
            print(f"  negocio id={n.id} nome={n.nome!r}")
        for u in avulsos:
            db.delete(u)
        db.commit()
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
        nivel = NivelClassificacao(negocio_id=neg_a.id, ordem=1, nome="Categoria")
        db.add(nivel)
        db.flush()

        def loja(neg, central, codigo):
            lj = Loja(negocio_id=neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}", codigo=codigo,
                      horario_zeragem=time(6, 0), ativo=True)
            db.add(lj)
            db.flush()
            return lj

        l1, l2, l3, lb = loja(neg_a, c_a1, "L1"), loja(neg_a, c_a1, "L2"), loja(neg_a, c_a2, "L3"), loja(neg_b, c_b, "LB")

        def produto(neg, codigo, categoria=None, unidade=UnidadeMedida.UN):
            p = Produto(negocio_id=neg.id, nome=f"_{codigo}", codigo=codigo, unidade_medida=unidade, ativo=True)
            db.add(p)
            db.flush()
            if categoria:
                db.add(ProdutoClassificacao(produto_id=p.id, nivel_id=nivel.id, valor=categoria))
            return p

        p1, p2, p3 = produto(neg_a, "P1", "Pães"), produto(neg_a, "P2", "Pães"), produto(neg_a, "P3", "Pães")
        p4 = produto(neg_a, "P4", "Frios", UnidadeMedida.KG)
        p5 = produto(neg_a, "P5", "Bolos", UnidadeMedida.KG)
        pb = produto(neg_b, "PB")
        vendas = [(neg_a, l1, p1, "10"), (neg_a, l1, p2, "20"), (neg_a, l1, p4, "5"), (neg_a, l2, p1, "30"),
                  (neg_a, l2, p2, "20"), (neg_a, l3, p1, "10"), (neg_b, lb, pb, "10")]
        habilitados = {(lj.id, p.id) for _, lj, p, _ in vendas} | {(l1.id, p3.id), (l2.id, p5.id)}
        for loja_id, produto_id in habilitados:
            db.add(ProdutoLoja(produto_id=produto_id, loja_id=loja_id))
        for neg, lj, p, qtd in vendas:
            for k in range(56):
                db.add(VendaDiaria(negocio_id=neg.id, loja_id=lj.id, produto_id=p.id, data=REF - timedelta(days=k),
                                   quantidade=D(qtd), origem=OrigemVenda.MANUAL))
        ev = Evento(negocio_id=neg_a.id, central_producao_id=c_a1.id, nome="Promo P1", data_inicio=HORIZONTE[1],
                    data_fim=HORIZONTE[1], escopo_loja=EscopoLoja.ESPECIFICAS, escopo_produto=EscopoProduto.ESPECIFICOS,
                    tipo_ajuste=TipoAjuste.VALOR_FIXO, valor_ajuste=D("50"))
        db.add(ev)
        db.flush()
        db.add_all([EventoLoja(evento_id=ev.id, loja_id=l1.id, negocio_id=neg_a.id),
                    EventoProduto(evento_id=ev.id, produto_id=p1.id, negocio_id=neg_a.id)])
        gestor = Usuario(negocio_id=neg_a.id, tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=c_a1.id,
                         nome="Teste gestor", email=f"tpg_gestor_{run_id}@teste.com", senha_hash=hash_senha("x"),
                         status=StatusUsuario.ATIVO, tem_acesso_app=False, tem_acesso_web=True)
        db.add(gestor)
        db.commit()

        nl = {l1.id: "L1", l2.id: "L2", l3.id: "L3", lb.id: "LB"}
        npr = {p.id: p.codigo for p in (p1, p2, p3, p4, p5, pb)}

        def linhas(central):
            db.expire_all()
            return (db.query(PrevisaoDiaria)
                    .filter(PrevisaoDiaria.negocio_id.in_(negocio_ids), PrevisaoDiaria.central_producao_id == central.id)
                    .order_by(PrevisaoDiaria.data, PrevisaoDiaria.loja_id, PrevisaoDiaria.produto_id).all())

        def linha(central, lj, p, dia):
            return next((r for r in linhas(central) if (r.loja_id, r.produto_id, r.data) == (lj.id, p.id, dia)), None)

        # ---- outras centrais primeiro (G08) ----
        gerar_previsoes(db, neg_a.id, c_a2.id, REF)
        gerar_previsoes(db, neg_b.id, c_b.id, REF)
        ids_a2 = {r.id for r in linhas(c_a2)}
        ids_b = {r.id for r in linhas(c_b)}

        # ---- G01 ----
        res = gerar_previsoes(db, neg_a.id, c_a1.id, REF, usuario_id=gestor.id)
        rs = linhas(c_a1)
        print(f"Geração A1: {res}")
        for r in rs[:7]:
            print(f"  {r.data:%d/%m} {nl[r.loja_id]}/{npr[r.produto_id]}: previsão {r.previsao}, base {r.base}, "
                  f"tendência {r.tendencia}, peso {r.peso_historico}, proxy {r.proxy} ({r.origem_proxy}), "
                  f"eventos {r.eventos}")
        registrar("G01 gera 49 linhas nos 7 dias",
                  res.gravadas == 49 and res.sem_previsao == 7 and res.substituidas == 0 and len(rs) == 49
                  and sorted({r.data for r in rs}) == HORIZONTE and (res.data_inicio, res.data_fim) == (HORIZONTE[0], HORIZONTE[-1]),
                  f"gravadas {res.gravadas}, sem previsão {res.sem_previsao}, substituídas {res.substituidas}, "
                  f"linhas no banco {len(rs)}, dias {res.data_inicio:%d/%m} a {res.data_fim:%d/%m}")

        # ---- G02 ----
        gravado = {(r.loja_id, r.produto_id, r.data): r for r in rs}
        divergencias = []
        for dia in HORIZONTE:
            for x in prever_central(db, neg_a.id, c_a1.id, REF, dia):
                r = gravado.get((x.loja_id, x.produto_id, dia))
                esperado = (q(x.previsao), q(x.componentes.base), q(x.componentes.tendencia), q(x.peso_historico),
                            q(x.proxy), x.origem_proxy, x.componentes.metodo)
                obtido = None if r is None else (q(r.previsao), q(r.base), q(r.tendencia), q(r.peso_historico),
                                                 q(r.proxy), r.origem_proxy.value if r.origem_proxy else None,
                                                 r.metodo.value)
                if obtido != esperado:
                    divergencias.append(f"{dia} {nl[x.loja_id]}/{npr[x.produto_id]}: {obtido} != {esperado}")
        registrar("G02 gravado = prever_central", not divergencias, "; ".join(divergencias[:3]) or "49 linhas conferidas")

        # ---- G03 ----
        promo, novo, sem = linha(c_a1, l1, p1, HORIZONTE[1]), linha(c_a1, l1, p3, HORIZONTE[0]), linha(c_a1, l2, p5, HORIZONTE[0])
        ok = (promo.previsao == D("50") and promo.previsao_sem_evento == D("10")
              and promo.eventos == [{"id": ev.id, "nome": "Promo P1", "tipo_ajuste": "valor_fixo", "valor_ajuste": "50.0000"}]
              and promo.estatistica.value == "mediana" and promo.versao_metodo == VERSAO_METODO
              and novo.origem_proxy.value == "categoria" and novo.proxy == D("15") and novo.peso_historico == 0
              and sem.previsao is None and sem.proxy is None)
        registrar("G03 componentes gravados", ok,
                  f"L1/P1 14/10: {promo.previsao} (sem evento {promo.previsao_sem_evento}), eventos {promo.eventos}, "
                  f"{promo.estatistica.value}, {promo.versao_metodo}; L1/P3: proxy {novo.proxy} ({novo.origem_proxy.value}); "
                  f"L2/P5: previsão {sem.previsao}")

        # ---- G04 ----
        registrar("G04 auditoria", all(r.data_referencia == REF and r.gerado_por_usuario_id == gestor.id
                                       and r.gerado_em is not None for r in rs),
                  f"referência {rs[0].data_referencia}, gerado por {rs[0].gerado_por_usuario_id} "
                  f"(gestor {gestor.id}) em {rs[0].gerado_em:%d/%m %H:%M}")

        # ---- G05 ----
        ids_antes = {r.id for r in rs}
        res = gerar_previsoes(db, neg_a.id, c_a1.id, REF, usuario_id=gestor.id)
        rs = linhas(c_a1)
        chaves = {(r.loja_id, r.produto_id, r.data) for r in rs}
        registrar("G05 gerar de novo nao duplica",
                  len(rs) == 49 and len(chaves) == 49 and res.substituidas == 49 and not ({r.id for r in rs} & ids_antes),
                  f"{len(rs)} linhas, {len(chaves)} chaves, substituídas {res.substituidas}, ids novos")

        # ---- G06 ----
        antes = linha(c_a1, l2, p2, HORIZONTE[0]).previsao
        db.add(VendaDiaria(negocio_id=neg_a.id, loja_id=l2.id, produto_id=p2.id, data=REF, quantidade=D("200"),
                           origem=OrigemVenda.API))
        db.commit()
        gerar_previsoes(db, neg_a.id, c_a1.id, REF)
        depois = linha(c_a1, l2, p2, HORIZONTE[0])
        registrar("G06 dado novo muda a regravacao", antes == D("20") and depois.previsao == D("26")
                  and depois.tendencia == D("1.3"), f"L2/P2 13/10: {antes} -> {depois.previsao} (tendência {depois.tendencia})")

        # ---- G07 ----
        db.query(ProdutoLoja).filter(ProdutoLoja.loja_id == l1.id, ProdutoLoja.produto_id == p2.id).update({"ativo": False})
        db.commit()
        gerar_previsoes(db, neg_a.id, c_a1.id, REF)
        rs = linhas(c_a1)
        restos = [r for r in rs if (r.loja_id, r.produto_id) == (l1.id, p2.id)]
        registrar("G07 desabilitado some na regravacao", len(rs) == 42 and not restos,
                  f"{len(rs)} linhas; linhas de L1/P2: {len(restos)}")

        # ---- G08 ----
        agora_a2, agora_b = {r.id for r in linhas(c_a2)}, {r.id for r in linhas(c_b)}
        registrar("G08 central A2 e negocio B intactos",
                  agora_a2 == ids_a2 and agora_b == ids_b and len(ids_a2) == 7 and len(ids_b) == 7,
                  f"A2: {len(agora_a2)} de {len(ids_a2)} linhas originais "
                  f"({len(agora_a2 & ids_a2)} com o mesmo id); B: {len(agora_b)} de {len(ids_b)} "
                  f"({len(agora_b & ids_b)} com o mesmo id)")

        # ---- G09 ----
        ids_antes = {r.id for r in linhas(c_a1)}
        chamadas = {"n": 0}
        original = previsao_gravacao.prever_central

        def falha_no_quarto_dia(*args, **kwargs):
            chamadas["n"] += 1
            if chamadas["n"] == 4:
                raise RuntimeError("falha simulada no 4º dia")
            return original(*args, **kwargs)

        try:
            with mock.patch.object(previsao_gravacao, "prever_central", side_effect=falha_no_quarto_dia):
                gerar_previsoes(db, neg_a.id, c_a1.id, REF)
            levantou = False
        except RuntimeError:
            levantou = True
        registrar("G09 falha no meio nao deixa pela metade", levantou and {r.id for r in linhas(c_a1)} == ids_antes,
                  f"erro propagado: {levantou}; linhas da geração anterior intactas: {len(ids_antes)}")

        # ---- G10 ----
        erros = []
        for dias in (0, 8):
            try:
                gerar_previsoes(db, neg_a.id, c_a1.id, REF, dias=dias)
                erros.append(f"dias={dias} aceito")
            except ValueError:
                pass
        registrar("G10 horizonte fora de 1 a 7", not erros and {r.id for r in linhas(c_a1)} == ids_antes,
                  "; ".join(erros) or "0 e 8 recusados; nada mudou")

        # ---- G11 ----
        res = gerar_previsoes(db, neg_a.id, c_a1.id, REF, dias=3)
        rs = linhas(c_a1)
        novos = {r.data for r in rs if r.id not in ids_antes}
        velhos = {r.data for r in rs if r.id in ids_antes}
        registrar("G11 horizonte de 3 dias substitui so esses dias",
                  len(rs) == 42 and novos == set(HORIZONTE[:3]) and velhos == set(HORIZONTE[3:]) and res.substituidas == 18,
                  f"novos: {sorted(d.day for d in novos)}, mantidos: {sorted(d.day for d in velhos)}, "
                  f"substituídas {res.substituidas}")

        # ---- G15: trava da central ----
        outra = SessionLocal()
        estado = {}
        try:
            outra.execute(text("SELECT pg_advisory_xact_lock(:a, :b)"),
                          {"a": previsao_gravacao._TRAVA_GERACAO, "b": c_a1.id})

            def gerar_em_paralelo():
                s = SessionLocal()
                try:
                    estado["resultado"] = gerar_previsoes(s, neg_a.id, c_a1.id, REF)
                finally:
                    s.close()

            t = threading.Thread(target=gerar_em_paralelo)
            t.start()
            t.join(timeout=2)
            estado["esperou"] = t.is_alive()
        finally:
            outra.commit()  # libera a trava
            outra.close()
        t.join(timeout=60)
        registrar("G15 geracao simultanea espera a trava da central",
                  estado.get("esperou") is True and not t.is_alive() and estado.get("resultado") is not None
                  and len(linhas(c_a1)) == 42,
                  f"bloqueada enquanto a outra sessão segurava a trava: {estado.get('esperou')}; "
                  f"terminou depois: {estado.get('resultado') is not None}; linhas {len(linhas(c_a1))}")

        # ---- banco ----
        modelo = linha(c_a1, l1, p1, HORIZONTE[0])

        def copia(**mudancas):
            campos = {c.name: getattr(modelo, c.name) for c in PrevisaoDiaria.__table__.columns if c.name != "id"}
            return PrevisaoDiaria(**(campos | mudancas))

        def recusa(nome, objeto):
            try:
                db.add(objeto)
                db.flush()
                registrar(nome, False, "o banco ACEITOU")
            except IntegrityError as e:
                registrar(nome, True, f"IntegrityError ({str(e.orig).splitlines()[0][:80]})")
            finally:
                db.rollback()

        recusa("G12 duplicada (loja + produto + dia)", copia())
        recusa("G13 loja de outro negocio", copia(loja_id=lb.id, data=date(2027, 1, 1)))
        try:
            db.add(copia(previsao=D("-1"), data=date(2027, 1, 2)))
            db.flush()
            negativa = False
        except IntegrityError:
            negativa = True
        finally:
            db.rollback()
        try:
            db.add(copia(data=REF, data_referencia=REF))
            db.flush()
            antes_ref = False
        except IntegrityError:
            antes_ref = True
        finally:
            db.rollback()
        registrar("G14 previsao negativa e dia antes da referencia", negativa and antes_ref,
                  f"negativa recusada: {negativa}; dia = referência recusado: {antes_ref}")

    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste das previsões gravadas ===")
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
