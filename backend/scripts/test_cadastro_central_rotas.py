"""
Testa o cadastro da central e dos setores de produção pelo SaaS (Fase 6 /
C1, D102 e D103) por HTTP, com o TestClient.

Cenário:
  negócio A: central A1 (lojas L1, L2) e central A2 (loja L3)
  negócio B: central B (loja LB), com o setor "Pães B"
Usuários: gestor A1, gestor A2, gestor B, gestor A1 sem tem_acesso_web,
operador (token do app).

Casos:
  A1 sem token -> 401 · A2 token do app -> 401 · A3 sem acesso web -> 403
  G1 GET /web/central: a central do gestor (nome, seção, prazo, ativa, 2 lojas)
  E1 PATCH nome + prazo -> 200 e gravado · E2 só o nome mantém o prazo
  E3..E7 inválidos -> 422 em português (prazo 8, -1, texto; nome vazio,
     nome com 256 caracteres) e nada gravado
  E8 seção e "ativa" no corpo são ignoradas (só leitura, D103)
  E9 a central A2 não mudou; o gestor A2 vê a A2
  S1 cria setor -> 201, ativo, ordem 1 · S2 o 2º vai para o fim (ordem 2)
  S3 com ordem informada · S4 nome repetido sem diferenciar maiúsculas -> 422
  S5 nome vazio · S6 nome com 81 caracteres -> 422
  S7 o mesmo nome em outra central (A2) é aceito
  S8 renomeia · S9 renomear para nome de outro setor -> 422
  S10 renomear para o próprio nome (outra caixa) é aceito
  S11 desativa -> a lista GET /producao/setores mostra inativo · S12 reativa
  S13 ordem negativa -> 422 · S14 PATCH vazio não muda nada
  S15 setor da A2 pelo gestor A1 -> 404 · S16 de outro negócio -> 404
  S17 inexistente -> 404 · S18 as três respostas 404 são idênticas
  S19 nome null -> 422 · S20 o gestor A2 não vê os setores da A1

Uso: python scripts/test_cadastro_central_rotas.py
"""

import re
import sys
import uuid
from datetime import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import PORTA_WEB, criar_access_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.setor_producao import SetorProducao  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 33
PREFIXO_NEGOCIO_TESTE = "_Teste Cadastro Central"
EMAIL_TESTE = re.compile(r"^tcc_[a-z_0-9]+_[0-9a-f]{8}@teste[.]com$")
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
    db.query(Usuario).filter(Usuario.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(SetorProducao).filter(SetorProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Loja).filter(Loja.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(CentralProducao).filter(CentralProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Negocio).filter(Negocio.id.in_(negocio_ids)).delete(synchronize_session=False)
    db.commit()


def _limpar_residuos():
    db = SessionLocal()
    try:
        negocios = [n for n in db.query(Negocio).all() if n.nome.startswith(PREFIXO_NEGOCIO_TESTE + " ")]
        avulsos = [u for u in db.query(Usuario).filter(Usuario.email.like("tcc_%@teste.com")).all()
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
        c_a2 = CentralProducao(negocio_id=neg_a.id, nome="_Central A2", ativa=True, prazo_entrega_dias=2)
        c_b = CentralProducao(negocio_id=neg_b.id, nome="_Central B", ativa=True)
        db.add_all([c_a1, c_a2, c_b])
        db.flush()
        for neg, central, codigo in ((neg_a, c_a1, "L1"), (neg_a, c_a1, "L2"), (neg_a, c_a2, "L3"), (neg_b, c_b, "LB")):
            db.add(Loja(negocio_id=neg.id, central_producao_id=central.id, nome=f"_Loja {codigo}", codigo=codigo,
                        horario_zeragem=time(6, 0), ativo=True))
        setor_b = SetorProducao(negocio_id=neg_b.id, central_producao_id=c_b.id, nome="Pães B", ordem=1)
        setor_a2 = SetorProducao(negocio_id=neg_a.id, central_producao_id=c_a2.id, nome="Biscoitos A2", ordem=5)
        db.add_all([setor_b, setor_a2])
        db.flush()

        def usuario(rotulo, neg, **campos):
            u = Usuario(negocio_id=neg.id, nome=f"Teste {rotulo}", email=f"tcc_{rotulo}_{run_id}@teste.com",
                        senha_hash=hash_senha("x"), status=StatusUsuario.ATIVO, **campos)
            db.add(u)
            db.flush()
            return u

        gestor = dict(tipo_usuario=TipoUsuario.GESTOR_CENTRAL, tem_acesso_app=False)
        g_a1 = usuario("gestor_a1", neg_a, central_producao_id=c_a1.id, tem_acesso_web=True, **gestor)
        g_a2 = usuario("gestor_a2", neg_a, central_producao_id=c_a2.id, tem_acesso_web=True, **gestor)
        g_sem_web = usuario("gestor_sem_web", neg_a, central_producao_id=c_a1.id, tem_acesso_web=False, **gestor)
        loja_l1 = db.query(Loja).filter(Loja.negocio_id == neg_a.id, Loja.codigo == "L1").one()
        operador = usuario("operador", neg_a, tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=loja_l1.id,
                           tem_acesso_web=False, tem_acesso_app=True)
        db.commit()
        tk = lambda u: criar_access_token(u.id, u.negocio_id, porta=PORTA_WEB)  # noqa: E731
        ta1, ta2 = tk(g_a1), tk(g_a2)

        # ---------------- autenticação ----------------
        r = cliente.get("/web/central")
        registrar("A1 sem token", r.status_code == 401, f"{r.status_code}")
        r = cliente.get("/web/central", headers=h(criar_access_token(operador.id, operador.negocio_id)))
        registrar("A2 token do app", r.status_code == 401, f"{r.status_code}")
        r = cliente.patch("/web/central", json={"nome": "x"}, headers=h(tk(g_sem_web)))
        registrar("A3 gestor sem acesso web", r.status_code == 403, f"{r.status_code}")

        # ---------------- central ----------------
        r = cliente.get("/web/central", headers=h(ta1))
        b = corpo(r)
        registrar("G1 central do gestor", r.status_code == 200 and b == {
            "id": c_a1.id, "nome": "_Central A1", "secao": "padaria", "prazo_entrega_dias": 0, "ativa": True, "lojas": 2,
        }, f"{r.status_code} -> {b}")

        r = cliente.patch("/web/central", json={"nome": "  Central Norte ", "prazo_entrega_dias": 1}, headers=h(ta1))
        db.expire_all()
        c = db.get(CentralProducao, c_a1.id)
        registrar("E1 nome e prazo", r.status_code == 200 and corpo(r)["nome"] == "Central Norte"
                  and c.nome == "Central Norte" and c.prazo_entrega_dias == 1, f"{r.status_code} -> {corpo(r)}")
        r = cliente.patch("/web/central", json={"nome": "Central Norte 2"}, headers=h(ta1))
        db.expire_all()
        c = db.get(CentralProducao, c_a1.id)
        registrar("E2 so o nome mantem o prazo", r.status_code == 200 and c.prazo_entrega_dias == 1
                  and c.nome == "Central Norte 2", f"{r.status_code} -> {corpo(r)}")
        invalidos = [
            ("E3 prazo 8", {"prazo_entrega_dias": 8}, "entre 0 e 7"),
            ("E4 prazo negativo", {"prazo_entrega_dias": -1}, "entre 0 e 7"),
            ("E5 prazo texto", {"prazo_entrega_dias": "dois"}, "número inteiro"),
            ("E6 nome vazio", {"nome": "   "}, "Informe o nome da central"),
            ("E7 nome com 256", {"nome": "x" * 256}, "no máximo 255"),
        ]
        for nome, mud, trecho in invalidos:
            r = cliente.patch("/web/central", json=mud, headers=h(ta1))
            d = detalhe(r)
            registrar(nome, r.status_code == 422 and isinstance(d, str) and trecho in d, f"{r.status_code} -> {d}")
        db.expire_all()
        c = db.get(CentralProducao, c_a1.id)
        r = cliente.patch("/web/central", json={"secao": "acougue", "ativa": False}, headers=h(ta1))
        db.expire_all()
        c = db.get(CentralProducao, c_a1.id)
        registrar("E8 secao e ativa sao so leitura", r.status_code == 200 and c.secao.value == "padaria" and c.ativa
                  and c.nome == "Central Norte 2" and c.prazo_entrega_dias == 1,
                  f"{r.status_code}; banco: {c.nome}, {c.secao.value}, ativa={c.ativa}, prazo={c.prazo_entrega_dias}")
        r = cliente.get("/web/central", headers=h(ta2))
        b = corpo(r)
        registrar("E9 central A2 intacta", r.status_code == 200 and b["id"] == c_a2.id and b["nome"] == "_Central A2"
                  and b["prazo_entrega_dias"] == 2 and b["lojas"] == 1, f"{b}")

        # ---------------- setores ----------------
        def post(token, **corpo_setor):
            return cliente.post("/producao/setores", json=corpo_setor, headers=h(token))

        r = post(ta1, nome=" Pães ")
        b = corpo(r)
        id_paes = b.get("id") if isinstance(b, dict) else None
        registrar("S1 cria setor", r.status_code == 201 and b.get("nome") == "Pães" and b.get("ordem") == 1
                  and b.get("ativo") is True, f"{r.status_code} -> {b}")
        r = post(ta1, nome="Bolos")
        b = corpo(r)
        id_bolos = b.get("id") if isinstance(b, dict) else None
        registrar("S2 segundo vai para o fim", r.status_code == 201 and b.get("ordem") == 2, f"{r.status_code} -> {b}")
        r = post(ta1, nome="Salgados", ordem=10)
        registrar("S3 ordem informada", r.status_code == 201 and corpo(r).get("ordem") == 10, f"{r.status_code} -> {corpo(r)}")
        for nome, mud, trecho in [
            ("S4 nome repetido (maiusculas)", dict(nome="PÃES"), "Já existe um setor chamado"),
            ("S5 nome vazio", dict(nome="  "), "Informe o nome do setor"),
            ("S6 nome com 81", dict(nome="y" * 81), "no máximo 80"),
        ]:
            r = post(ta1, **mud)
            d = detalhe(r)
            registrar(nome, r.status_code == 422 and isinstance(d, str) and trecho in d, f"{r.status_code} -> {d}")
        r = post(ta2, nome="Pães")
        registrar("S7 mesmo nome em outra central", r.status_code == 201, f"{r.status_code} -> {corpo(r)}")

        def patch(token, setor_id, **mud):
            return cliente.patch(f"/producao/setores/{setor_id}", json=mud, headers=h(token))

        r = patch(ta1, id_bolos, nome="Bolos e doces")
        registrar("S8 renomeia", r.status_code == 200 and corpo(r).get("nome") == "Bolos e doces", f"{r.status_code} -> {corpo(r)}")
        r = patch(ta1, id_bolos, nome="pães")
        registrar("S9 renomear para nome de outro", r.status_code == 422 and "Já existe" in str(detalhe(r)),
                  f"{r.status_code} -> {detalhe(r)}")
        r = patch(ta1, id_paes, nome="PÃES")
        registrar("S10 renomear para o proprio nome", r.status_code == 200 and corpo(r).get("nome") == "PÃES",
                  f"{r.status_code} -> {corpo(r)}")
        r = patch(ta1, id_paes, ativo=False)
        lista = corpo(cliente.get("/producao/setores", headers=h(ta1)))
        paes = next((s for s in lista if s["id"] == id_paes), None)
        registrar("S11 desativa", r.status_code == 200 and paes and paes["ativo"] is False
                  and [s["nome"] for s in lista] == ["PÃES", "Bolos e doces", "Salgados"], f"{r.status_code}; lista {lista}")
        r = patch(ta1, id_paes, ativo=True, ordem=3)
        lista = corpo(cliente.get("/producao/setores", headers=h(ta1)))
        registrar("S12 reativa e muda a ordem", r.status_code == 200 and corpo(r)["ativo"] is True
                  and [s["nome"] for s in lista] == ["Bolos e doces", "PÃES", "Salgados"], f"{lista}")
        r = patch(ta1, id_paes, ordem=-1)
        registrar("S13 ordem negativa", r.status_code == 422 and "entre 0 e 9999" in str(detalhe(r)), f"{r.status_code} -> {detalhe(r)}")
        r = patch(ta1, id_paes)
        registrar("S14 PATCH vazio", r.status_code == 200 and corpo(r) == {"id": id_paes, "nome": "PÃES", "ordem": 3, "ativo": True},
                  f"{r.status_code} -> {corpo(r)}")
        r1 = patch(ta1, setor_a2.id, nome="invasão")
        r2 = patch(ta1, setor_b.id, nome="invasão")
        r3 = patch(ta1, INEXISTENTE, nome="invasão")
        registrar("S15 setor de outra central", r1.status_code == 404, f"{r1.status_code} -> {corpo(r1)}")
        registrar("S16 setor de outro negocio", r2.status_code == 404, f"{r2.status_code} -> {corpo(r2)}")
        registrar("S17 setor inexistente", r3.status_code == 404, f"{r3.status_code} -> {corpo(r3)}")
        db.expire_all()
        registrar("S18 404 identicos e nada mudou", corpo(r1) == corpo(r2) == corpo(r3)
                  and db.get(SetorProducao, setor_a2.id).nome == "Biscoitos A2"
                  and db.get(SetorProducao, setor_b.id).nome == "Pães B",
                  f"{corpo(r1)}")
        r = patch(ta1, id_paes, nome=None)
        registrar("S19 nome null", r.status_code == 422 and "Informe o nome do setor" in str(detalhe(r)), f"{r.status_code} -> {detalhe(r)}")
        lista = corpo(cliente.get("/producao/setores", headers=h(ta2)))
        registrar("S20 gestor A2 ve so os da A2", [(s["nome"], s["ordem"]) for s in lista] == [("Biscoitos A2", 5), ("Pães", 6)],
                  f"{lista}")
    finally:
        db.rollback()
        _limpar(db, negocio_ids)
        db.close()

    print("\n".join(resultados))
    falhas = sum(1 for x in resultados if x.startswith(FAIL))
    if len(resultados) != TOTAL_CASOS:
        print(f"{FAIL} esperados {TOTAL_CASOS} casos, rodaram {len(resultados)}")
        falhas += 1
    print(f"\n{len(resultados) - (falhas if falhas else 0)}/{TOTAL_CASOS} casos ok" if not falhas else f"\n{falhas} falha(s)")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
