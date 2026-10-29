"""
Testa o cadastro de produto e a habilitação por loja pelo SaaS (Fase 6 /
C2 e C3; D96–D101, D105) por HTTP, com o TestClient, e o efeito no app
mobile (D100: produto desativado na loja some da contagem).

Cenário:
  negócio A: central A1 com lojas L1, L2 (ativas) e L3 (inativa);
             central A2 com loja L4
  negócio B: central B com loja LB; produto PB (código "PB")
  setores: A1 "Pães" (ativo) e "Velho" (inativo); A2 "Pães A2"
  produtos de A: PX (código "PX", UN, com venda = histórico) e PY (sem
  código, sem histórico, cadastro antigo)
Usuários: gestor A1, gestor B, operador da L1 (token do app).

Casos:
  A1 sem token -> 401 · A2 token do app -> 401
  C1 cria com todos os campos -> 201 (dias na ordem da semana, setor, sem histórico)
  C2 já nasce ativo nas lojas ativas da central (L1, L2), não na inativa (L3) nem na A2 (L4)
  C3 mínimo com habilitar_lojas = false: valores padrão e nenhuma loja
  C4 a lista GET /web/produtos traz tipo, setor e lojas ativas
  C5 o mesmo código de outro negócio é aceito
  C6 sazonal com temporada que vira o ano (01/12 a 06/01)
  V1..V22 inválidos -> 422 em português (código vazio, repetido, nome vazio,
     peso em UN, peso 0, peso com 5 casas, validade 0 e 366, margem -1,
     501 e 3 casas, fim antes do início, sazonal sem datas, ciclo sazonal
     sem recorrência, recorrência sem ciclo sazonal, setor de outra central,
     setor inativo, setor inexistente, dia repetido, dia inválido, código
     de barras repetido, código ausente)
  V23 nenhum inválido gravou produto
  E1 PATCH só o nome não mexe no resto · E2 calendário vazio = todos os dias
  E3 setor null = sem setor · E4 apagar um código existente -> 422
  E5 produto antigo sem código aceita PATCH sem código
  E6 unidade de produto com histórico -> 422 (D98) e nada muda
  E7 sem histórico a unidade muda; voltar para UN apaga o peso médio
  E8 desativar o produto (D99) tira do app
  E9 GET e PATCH de outro negócio e inexistente -> 404 iguais
  E10 o detalhe de PX mostra tem_historico
  L1 lojas do produto: L1 e L2 ativas, L3 sem habilitação, sem a L4
  L2 desativar na L1 mantém a linha e a data de habilitação
  L3 o app da L1 não lista nem acha pelo código o produto desativado (D100)
  L4 reativar na L1: volta ao app, mesma linha
  L5 desativar onde não há habilitação não cria linha
  L6 ativar na L3 cria a habilitação
  L7 loja de outra central, de outro negócio e produto de outro negócio -> 404
  L8 a lista conta as lojas ativas depois das mudanças

Uso: python scripts/test_cadastro_produto_rotas.py
"""

import re
import sys
import uuid
from datetime import date, time
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import PORTA_WEB, criar_access_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.calendario_producao import CalendarioProducao  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.setor_producao import SetorProducao  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 49
PREFIXO_NEGOCIO_TESTE = "_Teste Cadastro Produto"
EMAIL_TESTE = re.compile(r"^tcp_[a-z_0-9]+_[0-9a-f]{8}@teste[.]com$")
INEXISTENTE = 2_000_000_000

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
    produto_ids = [p.id for p in db.query(Produto).filter(Produto.negocio_id.in_(negocio_ids))]
    if produto_ids:
        db.query(ProdutoLoja).filter(ProdutoLoja.produto_id.in_(produto_ids)).delete(synchronize_session=False)
    db.query(CalendarioProducao).filter(CalendarioProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(VendaDiaria).filter(VendaDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Produto).filter(Produto.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(SetorProducao).filter(SetorProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Usuario).filter(Usuario.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Loja).filter(Loja.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(CentralProducao).filter(CentralProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Negocio).filter(Negocio.id.in_(negocio_ids)).delete(synchronize_session=False)
    db.commit()


def _limpar_residuos():
    db = SessionLocal()
    try:
        negocios = [n for n in db.query(Negocio).all() if n.nome.startswith(PREFIXO_NEGOCIO_TESTE + " ")]
        avulsos = [u for u in db.query(Usuario).filter(Usuario.email.like("tcp_%@teste.com")).all()
                   if EMAIL_TESTE.match(u.email) and u.negocio_id not in [n.id for n in negocios]]
        if not negocios and not avulsos:
            print("[limpeza inicial] Nenhum resíduo de teste encontrado.")
            return
        print("[limpeza inicial] Resíduos de execuções anteriores encontrados e apagados.")
        for u in avulsos:
            db.delete(u)
        db.commit()
        _limpar(db, [n.id for n in negocios])
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
            db.flush()
            return lj

        l1, l2, l3 = loja(neg_a, c_a1, "L1"), loja(neg_a, c_a1, "L2"), loja(neg_a, c_a1, "L3", ativo=False)
        l4, lb = loja(neg_a, c_a2, "L4"), loja(neg_b, c_b, "LB")
        s_paes = SetorProducao(negocio_id=neg_a.id, central_producao_id=c_a1.id, nome="Pães", ordem=1)
        s_velho = SetorProducao(negocio_id=neg_a.id, central_producao_id=c_a1.id, nome="Velho", ordem=2, ativo=False)
        s_a2 = SetorProducao(negocio_id=neg_a.id, central_producao_id=c_a2.id, nome="Pães A2", ordem=1)
        db.add_all([s_paes, s_velho, s_a2])
        px = Produto(negocio_id=neg_a.id, nome="_PX", codigo="PX", codigo_barras="7890000000001",
                     unidade_medida=UnidadeMedida.UN, ativo=True)
        py = Produto(negocio_id=neg_a.id, nome="_PY", codigo=None, unidade_medida=UnidadeMedida.UN, ativo=True)
        pb = Produto(negocio_id=neg_b.id, nome="_PB", codigo="PB", unidade_medida=UnidadeMedida.UN, ativo=True)
        db.add_all([px, py, pb])
        db.flush()
        db.add(VendaDiaria(negocio_id=neg_a.id, loja_id=l1.id, produto_id=px.id, data=date(2026, 10, 1),
                           quantidade=Decimal("5"), origem=OrigemVenda.MANUAL))
        db.add(ProdutoLoja(produto_id=px.id, loja_id=l1.id, ativo=True))

        def usuario(rotulo, neg, **campos):
            u = Usuario(negocio_id=neg.id, nome=f"Teste {rotulo}", email=f"tcp_{rotulo}_{run_id}@teste.com",
                        senha_hash=hash_senha("x"), status=StatusUsuario.ATIVO, **campos)
            db.add(u)
            db.flush()
            return u

        gestor = dict(tipo_usuario=TipoUsuario.GESTOR_CENTRAL, tem_acesso_app=False, tem_acesso_web=True)
        g_a1 = usuario("gestor_a1", neg_a, central_producao_id=c_a1.id, **gestor)
        g_b = usuario("gestor_b", neg_b, central_producao_id=c_b.id, **gestor)
        operador = usuario("operador", neg_a, tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=l1.id,
                           tem_acesso_web=False, tem_acesso_app=True)
        db.commit()
        tk = lambda u: criar_access_token(u.id, u.negocio_id, porta=PORTA_WEB)  # noqa: E731
        ta1, tb = tk(g_a1), tk(g_b)
        t_app = criar_access_token(operador.id, operador.negocio_id)

        def no_app(codigo):
            lista = corpo(cliente.get("/produtos", headers=h(t_app)))
            busca = cliente.get("/produtos/buscar", params={"q": codigo}, headers=h(t_app))
            return any(p["codigo"] == codigo for p in lista), busca.status_code

        # ---------------- autenticação ----------------
        r = cliente.get(f"/web/produtos/{px.id}")
        registrar("A1 sem token", r.status_code == 401, f"{r.status_code}")
        r = cliente.post("/web/produtos", json={"nome": "x", "codigo": "x"}, headers=h(t_app))
        registrar("A2 token do app", r.status_code == 401, f"{r.status_code}")

        # ---------------- criação ----------------
        completo = {
            "nome": " Pão de queijo ", "codigo": "PQ-01", "codigo_barras": "7890000000099", "unidade_medida": "KG",
            "peso_medio_kg": "0.0500", "tipo_abastecimento": "produzido", "dias_validade": 2,
            "margem_maxima_percentual": "15.5", "data_inicio_vigencia": "2026-11-01", "data_fim_vigencia": "2027-03-31",
            "setor_producao_id": s_paes.id, "dias_producao": ["sexta", "segunda"],
        }
        r = cliente.post("/web/produtos", json=completo, headers=h(ta1))
        b = corpo(r)
        id_pq = b.get("id") if isinstance(b, dict) else None
        ok = r.status_code == 201 and b.get("nome") == "Pão de queijo" and b.get("codigo") == "PQ-01" \
            and b.get("unidade") == "KG" and Decimal(b.get("peso_medio_kg")) == Decimal("0.05") \
            and b.get("dias_validade") == 2 and Decimal(b.get("margem_maxima_percentual")) == Decimal("15.5") \
            and b.get("setor") == {"id": s_paes.id, "nome": "Pães"} and b.get("dias_producao") == ["segunda", "sexta"] \
            and b.get("tem_historico") is False and b.get("ciclo_previsao") == "semanal" and b.get("ativo") is True \
            and b.get("data_fim_vigencia") == "2027-03-31"
        registrar("C1 cria com todos os campos", ok, f"{r.status_code} -> {b}")
        db.expire_all()
        lojas_pq = {pl.loja_id: pl.ativo for pl in db.query(ProdutoLoja).filter(ProdutoLoja.produto_id == id_pq)}
        registrar("C2 ativo nas lojas ativas da central", lojas_pq == {l1.id: True, l2.id: True},
                  f"{lojas_pq} (L1={l1.id}, L2={l2.id}, L3={l3.id} inativa, L4={l4.id} da A2)")
        r = cliente.post("/web/produtos", json={"nome": "Broa", "codigo": "BR-01", "habilitar_lojas": False}, headers=h(ta1))
        b = corpo(r)
        id_broa = b.get("id") if isinstance(b, dict) else None
        db.expire_all()
        n_lojas = db.query(ProdutoLoja).filter(ProdutoLoja.produto_id == id_broa).count() if id_broa else -1
        registrar("C3 minimo sem lojas", r.status_code == 201 and b.get("unidade") == "UN" and b.get("ativo") is True
                  and b.get("tipo_abastecimento") == "produzido" and b.get("ciclo_previsao") == "semanal"
                  and b.get("vigencia_recorrente") is False and b.get("dias_producao") == [] and b.get("setor") is None
                  and b.get("codigo_barras") is None and n_lojas == 0, f"{r.status_code} -> {b}; lojas {n_lojas}")
        r = cliente.get("/web/produtos", params={"busca": "PQ-01"}, headers=h(ta1))
        item = (corpo(r).get("itens") or [None])[0] if r.status_code == 200 else None
        registrar("C4 lista com tipo, setor e lojas", item is not None and item.get("setor") == "Pães"
                  and item.get("tipo_abastecimento") == "produzido" and item.get("lojas_ativas") == 2, f"{item}")
        r = cliente.post("/web/produtos", json={"nome": "Mesmo código de B", "codigo": "PB"}, headers=h(ta1))
        registrar("C5 codigo de outro negocio aceito", r.status_code == 201, f"{r.status_code} -> {detalhe(r)}")
        r = cliente.post("/web/produtos", json={
            "nome": "Panetone", "codigo": "PAN-01", "ciclo_previsao": "sazonal", "vigencia_recorrente": True,
            "data_inicio_vigencia": "2026-12-01", "data_fim_vigencia": "2027-01-06",
        }, headers=h(ta1))
        registrar("C6 sazonal que vira o ano", r.status_code == 201 and corpo(r).get("ciclo_previsao") == "sazonal"
                  and corpo(r).get("vigencia_recorrente") is True, f"{r.status_code} -> {detalhe(r)}")

        # ---------------- validação ----------------
        db.expire_all()
        produtos_antes = db.query(Produto).filter(Produto.negocio_id == neg_a.id).count()
        base = {"nome": "Inválido", "codigo": "INV-01"}
        invalidos = [
            ("V1 codigo vazio", dict(codigo="  "), "Informe o código do produto"),
            ("V2 codigo repetido", dict(codigo="PX"), "O código \"PX\" já é do produto \"_PX\""),
            ("V3 nome vazio", dict(nome=""), "Informe o nome do produto"),
            ("V4 peso em UN", dict(peso_medio_kg="0.1"), "Peso médio só vale para produto em KG"),
            ("V5 peso zero", dict(unidade_medida="KG", peso_medio_kg="0"), "maior que zero"),
            ("V6 peso com 5 casas", dict(unidade_medida="KG", peso_medio_kg="0.12345"), "4 casas"),
            ("V7 validade 0", dict(dias_validade=0), "entre 1 e 365"),
            ("V8 validade 366", dict(dias_validade=366), "entre 1 e 365"),
            ("V9 margem negativa", dict(margem_maxima_percentual="-1"), "entre 0% e 500%"),
            ("V10 margem 501", dict(margem_maxima_percentual="501"), "entre 0% e 500%"),
            ("V11 margem 3 casas", dict(margem_maxima_percentual="10.125"), "2 casas"),
            ("V12 fim antes do inicio", dict(data_inicio_vigencia="2026-12-10", data_fim_vigencia="2026-12-01"),
             "não pode ser antes da inicial"),
            ("V13 sazonal sem datas", dict(ciclo_previsao="sazonal", vigencia_recorrente=True), "duas datas"),
            ("V14 ciclo sazonal sem recorrencia", dict(ciclo_previsao="sazonal", data_inicio_vigencia="2026-12-01",
                                                       data_fim_vigencia="2026-12-31"), "ciclo sazonal junto"),
            ("V15 recorrencia sem ciclo sazonal", dict(vigencia_recorrente=True, data_inicio_vigencia="2026-12-01",
                                                       data_fim_vigencia="2026-12-31"), "ciclo sazonal junto"),
            ("V16 setor de outra central", dict(setor_producao_id=s_a2.id), "Setor não encontrado"),
            ("V17 setor inativo", dict(setor_producao_id=s_velho.id), "está inativo"),
            ("V18 setor inexistente", dict(setor_producao_id=INEXISTENTE), "Setor não encontrado"),
            ("V19 dia repetido", dict(dias_producao=["segunda", "segunda"]), "mais de uma vez"),
            ("V20 dia invalido", dict(dias_producao=["feriado"]), "Use um destes"),
            ("V21 codigo de barras repetido", dict(codigo_barras="7890000000001"), "já é do produto \"_PX\""),
        ]
        for nome, mud, trecho in invalidos:
            r = cliente.post("/web/produtos", json=base | mud, headers=h(ta1))
            d = detalhe(r)
            registrar(nome, r.status_code == 422 and isinstance(d, str) and trecho in d, f"{r.status_code} -> {d}")
        r = cliente.post("/web/produtos", json={"nome": "Sem código"}, headers=h(ta1))
        registrar("V22 codigo ausente", r.status_code == 422 and "codigo" in str(detalhe(r)), f"{r.status_code} -> {detalhe(r)}")
        db.expire_all()
        produtos_depois = db.query(Produto).filter(Produto.negocio_id == neg_a.id).count()
        registrar("V23 invalidos nao gravaram", produtos_depois == produtos_antes, f"{produtos_antes} -> {produtos_depois}")

        # ---------------- edição ----------------
        def patch(token, pid, **mud):
            return cliente.patch(f"/web/produtos/{pid}", json=mud, headers=h(token))

        r = patch(ta1, id_pq, nome="Pão de queijo grande")
        b = corpo(r)
        registrar("E1 so o nome", r.status_code == 200 and b.get("nome") == "Pão de queijo grande"
                  and b.get("dias_producao") == ["segunda", "sexta"] and b.get("setor", {}).get("id") == s_paes.id
                  and b.get("codigo") == "PQ-01" and b.get("unidade") == "KG", f"{r.status_code} -> {b}")
        r = patch(ta1, id_pq, dias_producao=[])
        db.expire_all()
        n_cal = db.query(CalendarioProducao).filter(CalendarioProducao.produto_id == id_pq).count()
        registrar("E2 calendario vazio", r.status_code == 200 and corpo(r).get("dias_producao") == [] and n_cal == 0,
                  f"{r.status_code}; linhas no calendário {n_cal}")
        r = patch(ta1, id_pq, setor_producao_id=None)
        registrar("E3 sem setor", r.status_code == 200 and corpo(r).get("setor") is None, f"{r.status_code} -> {corpo(r).get('setor')}")
        r = patch(ta1, id_pq, codigo="")
        registrar("E4 apagar codigo", r.status_code == 422 and "Informe o código" in str(detalhe(r)), f"{r.status_code} -> {detalhe(r)}")
        r = patch(ta1, py.id, nome="_PY renomeado")
        registrar("E5 produto antigo sem codigo", r.status_code == 200 and corpo(r).get("codigo") is None
                  and corpo(r).get("nome") == "_PY renomeado", f"{r.status_code} -> {detalhe(r)}")
        r = patch(ta1, px.id, unidade_medida="KG")
        db.expire_all()
        registrar("E6 unidade com historico (D98)", r.status_code == 422 and "não pode mudar" in str(detalhe(r))
                  and db.get(Produto, px.id).unidade_medida == UnidadeMedida.UN, f"{r.status_code} -> {detalhe(r)}")
        r1 = patch(ta1, id_pq, unidade_medida="UN")
        db.expire_all()
        p_pq = db.get(Produto, id_pq)
        r2 = patch(ta1, id_pq, unidade_medida="KG", peso_medio_kg="0.06")
        registrar("E7 sem historico a unidade muda", r1.status_code == 200 and corpo(r1).get("unidade") == "UN"
                  and p_pq.peso_medio_kg is None and r2.status_code == 200 and corpo(r2).get("unidade") == "KG",
                  f"{r1.status_code} {corpo(r1).get('unidade')} peso={p_pq.peso_medio_kg}; {r2.status_code}")
        antes = no_app("PX")
        r = patch(ta1, px.id, ativo=False)
        depois = no_app("PX")
        patch(ta1, px.id, ativo=True)
        registrar("E8 desativar tira do app (D99)", r.status_code == 200 and corpo(r).get("ativo") is False
                  and antes == (True, 200) and depois == (False, 404), f"antes {antes}, depois {depois}")
        respostas = [
            cliente.get(f"/web/produtos/{pb.id}", headers=h(ta1)),
            cliente.get(f"/web/produtos/{INEXISTENTE}", headers=h(ta1)),
            patch(ta1, pb.id, nome="invasão"),
            patch(tb, px.id, nome="invasão"),
        ]
        db.expire_all()
        registrar("E9 outro negocio e inexistente -> 404 iguais", all(x.status_code == 404 for x in respostas)
                  and len({str(corpo(x)) for x in respostas}) == 1 and db.get(Produto, pb.id).nome == "_PB"
                  and db.get(Produto, px.id).nome == "_PX", f"{[x.status_code for x in respostas]} {corpo(respostas[0])}")
        r = cliente.get(f"/web/produtos/{px.id}", headers=h(ta1))
        registrar("E10 tem_historico", r.status_code == 200 and corpo(r).get("tem_historico") is True, f"{corpo(r)}")

        # ---------------- lojas do produto ----------------
        r = cliente.get(f"/web/produtos/{id_pq}/lojas", headers=h(ta1))
        b = corpo(r)
        resumo = [(x["codigo"], x["loja_ativa"], x["habilitado"], x["ativo"]) for x in b] if r.status_code == 200 else b
        registrar("L1 lojas do produto", resumo == [("L1", True, True, True), ("L2", True, True, True), ("L3", False, False, False)],
                  f"{resumo}")
        db.expire_all()
        criado_antes = db.query(ProdutoLoja.criado_em).filter(ProdutoLoja.produto_id == id_pq, ProdutoLoja.loja_id == l1.id).scalar()
        codigo_pq = "PQ-01"
        antes = no_app(codigo_pq)
        r = cliente.put(f"/web/produtos/{id_pq}/lojas/{l1.id}", json={"ativo": False}, headers=h(ta1))
        db.expire_all()
        linha = db.query(ProdutoLoja).filter(ProdutoLoja.produto_id == id_pq, ProdutoLoja.loja_id == l1.id).one_or_none()
        registrar("L2 desativar mantem a linha", r.status_code == 200 and corpo(r).get("habilitado") is True
                  and corpo(r).get("ativo") is False and linha is not None and linha.ativo is False
                  and linha.criado_em == criado_antes, f"{r.status_code} -> {corpo(r)}")
        depois = no_app(codigo_pq)
        registrar("L3 app esconde o desativado na loja (D100)", antes == (True, 200) and depois == (False, 404),
                  f"antes {antes}, depois {depois}")
        r = cliente.put(f"/web/produtos/{id_pq}/lojas/{l1.id}", json={"ativo": True}, headers=h(ta1))
        db.expire_all()
        n_linhas = db.query(ProdutoLoja).filter(ProdutoLoja.produto_id == id_pq, ProdutoLoja.loja_id == l1.id).count()
        registrar("L4 reativar", r.status_code == 200 and corpo(r).get("ativo") is True and no_app(codigo_pq) == (True, 200)
                  and n_linhas == 1, f"{r.status_code} -> {corpo(r)}; linhas {n_linhas}")
        r = cliente.put(f"/web/produtos/{id_pq}/lojas/{l3.id}", json={"ativo": False}, headers=h(ta1))
        db.expire_all()
        n_l3 = db.query(ProdutoLoja).filter(ProdutoLoja.produto_id == id_pq, ProdutoLoja.loja_id == l3.id).count()
        registrar("L5 desativar sem habilitacao nao cria", r.status_code == 200 and corpo(r).get("habilitado") is False
                  and n_l3 == 0, f"{r.status_code} -> {corpo(r)}; linhas {n_l3}")
        r = cliente.put(f"/web/produtos/{id_pq}/lojas/{l3.id}", json={"ativo": True}, headers=h(ta1))
        db.expire_all()
        n_l3 = db.query(ProdutoLoja).filter(ProdutoLoja.produto_id == id_pq, ProdutoLoja.loja_id == l3.id).count()
        registrar("L6 ativar cria a habilitacao", r.status_code == 200 and corpo(r).get("habilitado") is True
                  and corpo(r).get("ativo") is True and n_l3 == 1, f"{r.status_code} -> {corpo(r)}")
        respostas = [
            cliente.put(f"/web/produtos/{id_pq}/lojas/{l4.id}", json={"ativo": True}, headers=h(ta1)),
            cliente.put(f"/web/produtos/{id_pq}/lojas/{lb.id}", json={"ativo": True}, headers=h(ta1)),
            cliente.put(f"/web/produtos/{pb.id}/lojas/{l1.id}", json={"ativo": True}, headers=h(ta1)),
            cliente.get(f"/web/produtos/{pb.id}/lojas", headers=h(ta1)),
        ]
        db.expire_all()
        invadidas = db.query(ProdutoLoja).filter(
            ((ProdutoLoja.produto_id == id_pq) & ProdutoLoja.loja_id.in_([l4.id, lb.id])) | (ProdutoLoja.produto_id == pb.id)
        ).count()
        registrar("L7 fora do escopo -> 404", all(x.status_code == 404 for x in respostas) and invadidas == 0,
                  f"{[x.status_code for x in respostas]} {[detalhe(x) for x in respostas]}; linhas criadas {invadidas}")
        r = cliente.get("/web/produtos", params={"busca": "PQ-01"}, headers=h(ta1))
        item = corpo(r)["itens"][0]
        registrar("L8 lista conta as lojas ativas", item.get("lojas_ativas") == 3, f"{item}")
    finally:
        db.rollback()
        _limpar(db, negocio_ids)
        db.close()

    print("\n".join(resultados))
    falhas = sum(1 for x in resultados if x.startswith(FAIL))
    if len(resultados) != TOTAL_CASOS:
        print(f"{FAIL} esperados {TOTAL_CASOS} casos, rodaram {len(resultados)}")
        falhas += 1
    print(f"\n{TOTAL_CASOS}/{TOTAL_CASOS} casos ok" if not falhas else f"\n{falhas} falha(s)")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
