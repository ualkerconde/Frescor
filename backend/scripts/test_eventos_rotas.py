"""
Testa a API mínima de eventos (Fase 3 / F3, D24) por HTTP, com o
TestClient: autenticação, validação, escopo da central (D8, D27),
isolamento entre negócios, erros de validação em português (handler
único) e as FKs compostas por negócio (migration 0018).

Cenário:
  negócio A: central A1 com lojas L1 e L2; central A2 com loja L3
  negócio B: central B com loja LB
  produtos de A: P1, P2; de B: PB
  eventos gravados direto no banco:
    ev_todas     (A, antigo sem central, "todas": vale para o negócio todo)
    ev_comp      (A, antigo sem central, lojas L2 + L3)
    ev_a2        (A, central A2, só L3)
    ev_a2_todas  (A, central A2, "todas")
    ev_b         (B, central B, só LB)
Usuários: gestor A1, gestor A2, gestor B, gestor A1 sem tem_acesso_web,
operador (token do app).

Casos:
  A1 sem token -> 401 · A2 token do app -> 401 · A3 sem acesso web -> 403
  C1 cria com L1, L2 e P1 -> 201 com os campos
  C2 cria sem produtos -> escopo "todos"
  C3 cria "todas as lojas" -> 201, sem lojas na resposta, central A1 no banco
  V1..V11, V13 validações -> 422 com mensagem (fim < início, valor
     negativo, 5 casas, loja de outra central, loja de outro negócio, sem
     lojas, produto de outro negócio, nome em branco, tipo inválido em
     português, período de mais de 366 dias, loja repetida, "todas" com
     lojas)
  V12 nenhuma das requisições inválidas gravou evento
  L1 lista do gestor A1: os 3 criados + ev_todas + ev_comp (só com L2)
  L2 filtro por período · L3 gestor B vê só o de B
  L4 gestor A2 não vê os eventos da A1 e vê os da A2
  P1 o evento criado pela API entra na previsão (prever_central)
  P2 o "todas" da A1 vale para L1 e L2 e não para L3 (A2)
  D1 apaga o próprio -> 204; some da lista e das associações
  D2 evento só de outra central -> 404 · D3 de outro negócio -> 404
  D4 inexistente -> 404 · D5 as três respostas 404 são idênticas
  D6 antigo "todas" sem central -> 403 · D7 compartilhado -> 403
  D8 apaga o próprio "todas" -> 204 · D9 "todas" da A2 -> 404
  H2..H7 erros de validação em português: data inválida no corpo, campo
     obrigatório, data inválida na query, JSON inválido, limite de outra
     rota (/vendas), id não numérico no caminho
  B1..B4 o banco recusa misturar negócios: evento de A com loja de B;
     associação com negocio_id de B para evento de A; evento de A com
     produto de B; evento de A com central de B

Uso: python scripts/test_eventos_rotas.py
"""

import re
import sys
import uuid
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.core.security import PORTA_WEB, criar_access_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.evento import EscopoLoja, EscopoProduto, Evento, EventoLoja, EventoProduto, TipoAjuste  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402
from app.services.eventos_service import eventos_das_lojas  # noqa: E402
from app.services.previsao_service import prever_central  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 44
PREFIXO_NEGOCIO_TESTE = "_Teste Eventos Rotas"
EMAIL_TESTE = re.compile(r"^ter_[a-z_0-9]+_[0-9a-f]{8}@teste[.]com$")
INEXISTENTE = 2_000_000_000
NATAL = date(2026, 12, 24)

cliente = TestClient(app)
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
    return b.get("detail") if isinstance(b, dict) else b


def h(token):
    return {"Authorization": f"Bearer {token}"} if token else {}


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    ev_ids = [e.id for e in db.query(Evento).filter(Evento.negocio_id.in_(negocio_ids))]
    if ev_ids:
        db.query(EventoLoja).filter(EventoLoja.evento_id.in_(ev_ids)).delete(synchronize_session=False)
        db.query(EventoProduto).filter(EventoProduto.evento_id.in_(ev_ids)).delete(synchronize_session=False)
        db.query(Evento).filter(Evento.id.in_(ev_ids)).delete(synchronize_session=False)
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
        avulsos = [u for u in db.query(Usuario).filter(Usuario.email.like("ter_%@teste.com")).all()
                   if EMAIL_TESTE.match(u.email) and u.negocio_id not in [n.id for n in negocios]]
        if not negocios and not avulsos:
            print("[limpeza inicial] Nenhum resíduo de teste encontrado.")
            return
        print("[limpeza inicial] Resíduos de execuções anteriores encontrados:")
        for n in negocios:
            print(f"  negocio id={n.id} nome={n.nome!r}")
        for u in avulsos:
            print(f"  usuario avulso id={u.id} email={u.email!r}")
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

        def loja(neg, central, codigo):
            lj = Loja(negocio_id=neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}", codigo=codigo,
                      horario_zeragem=time(6, 0), ativo=True)
            db.add(lj)
            db.flush()
            return lj

        l1, l2, l3, lb = loja(neg_a, c_a1, "L1"), loja(neg_a, c_a1, "L2"), loja(neg_a, c_a2, "L3"), loja(neg_b, c_b, "LB")
        p1 = Produto(negocio_id=neg_a.id, nome="_P1", codigo="P1", unidade_medida=UnidadeMedida.UN, ativo=True)
        p2 = Produto(negocio_id=neg_a.id, nome="_P2", codigo="P2", unidade_medida=UnidadeMedida.UN, ativo=True)
        pb = Produto(negocio_id=neg_b.id, nome="_PB", codigo="PB", unidade_medida=UnidadeMedida.UN, ativo=True)
        db.add_all([p1, p2, pb])
        db.flush()

        def evento(neg, central, nome, inicio, lojas=None):
            e = Evento(negocio_id=neg.id, central_producao_id=central.id if central else None, nome=nome,
                       data_inicio=inicio, data_fim=inicio,
                       escopo_loja=EscopoLoja.TODAS if lojas is None else EscopoLoja.ESPECIFICAS,
                       escopo_produto=EscopoProduto.TODOS, tipo_ajuste=TipoAjuste.MULTIPLICADOR,
                       valor_ajuste=Decimal("2"))
            db.add(e)
            db.flush()
            for lj in lojas or []:
                db.add(EventoLoja(evento_id=e.id, loja_id=lj.id, negocio_id=neg.id))
            return e

        ev_todas = evento(neg_a, None, "ev_todas", date(2026, 11, 2))
        ev_comp = evento(neg_a, None, "ev_comp", date(2026, 11, 15), [l2, l3])
        ev_a2 = evento(neg_a, c_a2, "ev_a2", date(2026, 11, 20), [l3])
        ev_a2_todas = evento(neg_a, c_a2, "ev_a2_todas", date(2026, 11, 25))
        ev_b = evento(neg_b, c_b, "ev_b", date(2026, 11, 20), [lb])

        def usuario(rotulo, neg, **campos):
            u = Usuario(negocio_id=neg.id, nome=f"Teste {rotulo}", email=f"ter_{rotulo}_{run_id}@teste.com",
                        senha_hash=hash_senha("x"), status=StatusUsuario.ATIVO, **campos)
            db.add(u)
            db.flush()
            return u

        gestor = dict(tipo_usuario=TipoUsuario.GESTOR_CENTRAL, tem_acesso_app=False)
        g_a1 = usuario("gestor_a1", neg_a, central_producao_id=c_a1.id, tem_acesso_web=True, **gestor)
        g_a2 = usuario("gestor_a2", neg_a, central_producao_id=c_a2.id, tem_acesso_web=True, **gestor)
        g_b = usuario("gestor_b", neg_b, central_producao_id=c_b.id, tem_acesso_web=True, **gestor)
        g_sem_web = usuario("gestor_sem_web", neg_a, central_producao_id=c_a1.id, tem_acesso_web=False, **gestor)
        operador = usuario("operador", neg_a, tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=l1.id,
                           tem_acesso_web=False, tem_acesso_app=True)
        db.commit()
        tk = lambda u: criar_access_token(u.id, u.negocio_id, porta=PORTA_WEB)  # noqa: E731
        ta1, ta2, tb = tk(g_a1), tk(g_a2), tk(g_b)

        valido = {"nome": "Natal", "data_inicio": str(NATAL), "data_fim": str(NATAL + timedelta(days=1)),
                  "tipo_ajuste": "multiplicador", "valor_ajuste": "1.8", "loja_ids": [l1.id, l2.id],
                  "produto_ids": [p1.id]}

        def post(token, **mudancas):
            return cliente.post("/eventos", json=valido | mudancas, headers=h(token))

        # ---------------- autenticação ----------------
        r = post(None)
        registrar("A1 sem token", r.status_code == 401, f"{r.status_code}")
        r = post(criar_access_token(operador.id, operador.negocio_id))
        registrar("A2 token do app", r.status_code == 401, f"{r.status_code}")
        r = post(tk(g_sem_web))
        registrar("A3 gestor sem acesso web", r.status_code == 403, f"{r.status_code} -> {corpo(r)}")

        # ---------------- criação ----------------
        r = post(ta1)
        b = corpo(r)
        esperado = {"nome": "Natal", "data_inicio": "2026-12-24", "data_fim": "2026-12-25", "tipo_ajuste": "multiplicador",
                    "escopo_loja": "especificas", "loja_ids": sorted([l1.id, l2.id]), "escopo_produto": "especificos",
                    "produto_ids": [p1.id]}
        ok = r.status_code == 201 and all(b.get(k) == v for k, v in esperado.items()) and Decimal(b["valor_ajuste"]) == Decimal("1.8")
        registrar("C1 cria com lojas e produto", ok, f"{r.status_code} -> {b}")
        id_natal = b.get("id") if isinstance(b, dict) else None
        r = post(ta1, nome="  Feriado municipal ", produto_ids=None, tipo_ajuste="valor_fixo", valor_ajuste="0",
                 data_inicio="2026-11-03", data_fim="2026-11-03", loja_ids=[l1.id])
        b = corpo(r)
        registrar("C2 cria sem produtos -> todos", r.status_code == 201 and b.get("escopo_produto") == "todos"
                  and b.get("produto_ids") == [] and b.get("nome") == "Feriado municipal", f"{r.status_code} -> {b}")
        r = post(ta1, nome="Semana do pão", escopo_loja="todas", loja_ids=None, produto_ids=None,
                 data_inicio="2026-11-04", data_fim="2026-11-05", valor_ajuste="3")
        b = corpo(r)
        id_semana = b.get("id") if isinstance(b, dict) else None
        db.expire_all()
        central_gravada = db.query(Evento.central_producao_id).filter(Evento.id == id_semana).scalar() if id_semana else None
        registrar("C3 cria 'todas as lojas' (D27)", r.status_code == 201 and b.get("escopo_loja") == "todas"
                  and b.get("loja_ids") == [] and central_gravada == c_a1.id,
                  f"{r.status_code} -> escopo {b.get('escopo_loja')}, lojas {b.get('loja_ids')}, "
                  f"central no banco {central_gravada} (A1={c_a1.id})")

        # ---------------- validação ----------------
        invalidos = [
            ("V1 fim antes do inicio", dict(data_fim="2026-12-23"), "antes da inicial"),
            ("V2 valor negativo", dict(valor_ajuste="-1"), "negativo"),
            ("V3 5 casas decimais", dict(valor_ajuste="1.12345"), "4 casas"),
            ("V4 loja de outra central", dict(loja_ids=[l1.id, l3.id]), f"Loja {l3.id} não encontrada"),
            ("V5 loja de outro negocio", dict(loja_ids=[lb.id]), f"Loja {lb.id} não encontrada"),
            ("V6 sem lojas", dict(loja_ids=[]), "pelo menos uma loja"),
            ("V7 produto de outro negocio", dict(produto_ids=[p1.id, pb.id]), f"Produto {pb.id} não encontrado"),
            ("V8 nome em branco", dict(nome="   "), "nome do evento"),
            ("V9 tipo invalido (em portugues)", dict(tipo_ajuste="percentual"),
             "Valor inválido em 'tipo_ajuste'. Use um destes: 'multiplicador' ou 'valor_fixo'."),
            ("V10 periodo de mais de 366 dias", dict(data_fim="2027-12-25"), "366 dias"),
            ("V11 loja repetida", dict(loja_ids=[l1.id, l1.id]), "mais de uma vez"),
            ("V13 'todas' com lojas", dict(escopo_loja="todas"), "não informe lojas"),
        ]
        for nome, mudancas, trecho in invalidos:
            r = post(ta1, **mudancas)
            d = detalhe(r)
            registrar(nome, r.status_code == 422 and isinstance(d, str) and trecho in d, f"{r.status_code} -> {d}")
        db.expire_all()
        n = db.query(Evento).filter(Evento.negocio_id == neg_a.id).count()
        registrar("V12 invalidos nao gravaram", n == 7, f"{n} eventos no negocio A (4 do cenario + 3 criados)")

        # ---------------- listagem ----------------
        r = cliente.get("/eventos", headers=h(ta1))
        b = corpo(r)
        nomes = [e["nome"] for e in b] if r.status_code == 200 else None
        comp = next((e for e in b if e["nome"] == "ev_comp"), None) if r.status_code == 200 else None
        registrar("L1 lista do gestor A1",
                  nomes == ["ev_todas", "Feriado municipal", "Semana do pão", "ev_comp", "Natal"]
                  and comp and comp["loja_ids"] == [l2.id],
                  f"{nomes}; ev_comp lojas {comp['loja_ids'] if comp else None} (L2={l2.id}, L3={l3.id} oculta)")
        r = cliente.get("/eventos", params={"data_inicio": "2026-11-03", "data_fim": "2026-11-30"}, headers=h(ta1))
        nomes = [e["nome"] for e in corpo(r)] if r.status_code == 200 else corpo(r)
        registrar("L2 filtro por periodo", nomes == ["Feriado municipal", "Semana do pão", "ev_comp"], f"{nomes}")
        r = cliente.get("/eventos", headers=h(tb))
        nomes = [e["nome"] for e in corpo(r)] if r.status_code == 200 else corpo(r)
        registrar("L3 gestor B so ve o de B", nomes == ["ev_b"], f"{nomes}")
        r = cliente.get("/eventos", headers=h(ta2))
        nomes = [e["nome"] for e in corpo(r)] if r.status_code == 200 else corpo(r)
        registrar("L4 gestor A2 nao ve os da A1", nomes == ["ev_todas", "ev_comp", "ev_a2", "ev_a2_todas"], f"{nomes}")

        # ---------------- previsão ----------------
        # P1: o feriado (valor fixo 0 em L1, 03/11) criado pela API zera a
        # previsão de L1 naquele dia; L2 segue a previsão normal.
        db.add_all([ProdutoLoja(produto_id=p1.id, loja_id=l1.id), ProdutoLoja(produto_id=p1.id, loja_id=l2.id)])
        ref_nov = date(2026, 11, 2)
        for k in range(56):
            for lj in (l1, l2):
                db.add(VendaDiaria(negocio_id=neg_a.id, loja_id=lj.id, produto_id=p1.id, data=ref_nov - timedelta(days=k),
                                   quantidade=Decimal("10"), origem=OrigemVenda.MANUAL))
        db.commit()
        prev = {(x.loja_id, x.produto_id): x for x in prever_central(db, neg_a.id, c_a1.id, ref_nov, date(2026, 11, 3))}
        x1, x2 = prev.get((l1.id, p1.id)), prev.get((l2.id, p1.id))
        registrar("P1 evento da API entra na previsao",
                  x1 is not None and x1.previsao == Decimal("0") and x1.previsao_sem_evento == Decimal("10")
                  and x2 is not None and x2.previsao == Decimal("10"),
                  f"L1 {x1.previsao_sem_evento if x1 else None} -> {x1.previsao if x1 else None}; "
                  f"L2 {x2.previsao if x2 else None}")
        carregados = eventos_das_lojas(db, neg_a.id, [l1.id, l2.id, l3.id], date(2026, 11, 4), date(2026, 11, 5))
        com_semana = sorted(lid for lid, evs in carregados.items() if any(e.nome == "Semana do pão" for e in evs))
        registrar("P2 'todas' da A1 vale em L1 e L2, nao em L3", com_semana == sorted([l1.id, l2.id]),
                  f"lojas com o evento {com_semana} (L1={l1.id}, L2={l2.id}, L3={l3.id})")

        # ---------------- apagar ----------------
        r = cliente.delete(f"/eventos/{id_natal}", headers=h(ta1))
        db.expire_all()
        sobras = (db.query(EventoLoja).filter(EventoLoja.evento_id == id_natal).count()
                  + db.query(EventoProduto).filter(EventoProduto.evento_id == id_natal).count()
                  + db.query(Evento).filter(Evento.id == id_natal).count())
        nomes = [e["nome"] for e in corpo(cliente.get("/eventos", headers=h(ta1)))]
        registrar("D1 apaga o proprio", r.status_code == 204 and sobras == 0 and "Natal" not in nomes,
                  f"{r.status_code}; linhas restantes {sobras}; lista {nomes}")
        respostas = []
        for nome, eid in (("D2 evento so de outra central", ev_a2.id), ("D3 evento de outro negocio", ev_b.id),
                          ("D4 inexistente", INEXISTENTE)):
            r = cliente.delete(f"/eventos/{eid}", headers=h(ta1))
            respostas.append((r.status_code, r.text))
            registrar(nome, r.status_code == 404, f"{r.status_code} -> {corpo(r)}")
        registrar("D5 respostas 404 identicas", len(set(respostas)) == 1, f"{len(set(respostas))} resposta(s) distinta(s)")
        for nome, eid in (("D6 antigo 'todas' sem central", ev_todas.id), ("D7 compartilhado com outra central", ev_comp.id)):
            r = cliente.delete(f"/eventos/{eid}", headers=h(ta1))
            db.expire_all()
            existe = db.query(Evento).filter(Evento.id == eid).count() == 1
            registrar(nome, r.status_code == 403 and existe, f"{r.status_code} -> {corpo(r)}; continua gravado: {existe}")
        r = cliente.delete(f"/eventos/{id_semana}", headers=h(ta1))
        registrar("D8 apaga o proprio 'todas'", r.status_code == 204, f"{r.status_code}")
        r = cliente.delete(f"/eventos/{ev_a2_todas.id}", headers=h(ta1))
        db.expire_all()
        existe = db.query(Evento).filter(Evento.id == ev_a2_todas.id).count() == 1
        registrar("D9 'todas' da A2 -> 404", r.status_code == 404 and existe, f"{r.status_code}; continua gravado: {existe}")

        # ---------------- erros de validação em português ----------------
        r = post(ta1, data_inicio="2026-13-40")
        registrar("H2 data invalida no corpo", r.status_code == 422 and detalhe(r) ==
                  "Data inválida em 'data_inicio'. Use o formato AAAA-MM-DD.", f"{r.status_code} -> {detalhe(r)}")
        sem_nome = {k: v for k, v in valido.items() if k != "nome"}
        r = cliente.post("/eventos", json=sem_nome, headers=h(ta1))
        b = corpo(r)
        registrar("H3 campo obrigatorio", r.status_code == 422 and detalhe(r) == "O campo 'nome' é obrigatório."
                  and b.get("erros") == [{"campo": "nome", "mensagem": "O campo 'nome' é obrigatório."}],
                  f"{r.status_code} -> {b}")
        r = cliente.get("/eventos", params={"data_inicio": "ontem"}, headers=h(ta1))
        registrar("H4 data invalida na query", r.status_code == 422 and "Data inválida em 'data_inicio'" in str(detalhe(r)),
                  f"{r.status_code} -> {detalhe(r)}")
        r = cliente.post("/eventos", content="{nome: ", headers=h(ta1) | {"Content-Type": "application/json"})
        registrar("H5 JSON invalido", r.status_code == 422 and "não é um JSON válido" in str(detalhe(r)),
                  f"{r.status_code} -> {detalhe(r)}")
        r = cliente.get("/vendas", params={"data_inicio": "2026-09-01", "data_fim": "2026-09-30", "limit": 5000},
                        headers=h(ta1))
        registrar("H6 limite em outra rota (/vendas)", r.status_code == 422 and
                  detalhe(r) == "O campo 'limit' pode ser no máximo 1000.", f"{r.status_code} -> {detalhe(r)}")
        r = cliente.delete("/eventos/abc", headers=h(ta1))
        registrar("H7 id nao numerico no caminho", r.status_code == 422 and
                  detalhe(r) == "O campo 'evento_id' precisa ser um número inteiro.", f"{r.status_code} -> {detalhe(r)}")

        # ---------------- banco: FKs compostas por negócio ----------------
        def recusa(nome, objetos):
            try:
                db.add_all(objetos)
                db.flush()
                registrar(nome, False, "o banco ACEITOU")
            except IntegrityError as e:
                registrar(nome, True, f"IntegrityError ({str(e.orig).splitlines()[0][:90]})")
            finally:
                db.rollback()

        ev_ok = db.query(Evento).filter(Evento.id == ev_a2.id).one()
        recusa("B1 evento de A com loja de B", [EventoLoja(evento_id=ev_ok.id, loja_id=lb.id, negocio_id=neg_a.id)])
        recusa("B2 associacao com negocio_id de B", [EventoLoja(evento_id=ev_a2.id, loja_id=lb.id, negocio_id=neg_b.id)])
        recusa("B3 evento de A com produto de B", [EventoProduto(evento_id=ev_a2.id, produto_id=pb.id, negocio_id=neg_a.id)])
        recusa("B4 evento de A com central de B", [Evento(
            negocio_id=neg_a.id, central_producao_id=c_b.id, nome="x", data_inicio=NATAL, data_fim=NATAL,
            escopo_loja=EscopoLoja.TODAS, escopo_produto=EscopoProduto.TODOS, tipo_ajuste=TipoAjuste.MULTIPLICADOR,
            valor_ajuste=Decimal("2"))])

    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("=== Resultado do teste das rotas de eventos ===")
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
