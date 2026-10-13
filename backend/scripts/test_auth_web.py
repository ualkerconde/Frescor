"""
Testa as rotas de autenticação do SaaS web (/auth/web/login e
/auth/web/refresh), a separação de tokens por porta de entrada (decisão
D10) e faz a regressão completa do app mobile (login, /produtos,
/estoque, /zeragem), tudo por HTTP com o TestClient do FastAPI.

Requer: pip install -r requirements-dev.txt (httpx), migration 0014 e
python scripts/seed_dev.py + seed_produtos.py.

Os dados de teste ficam em negócios próprios ("_Teste Auth Web ...") e são
apagados no início (resíduos) e no fim. A zeragem roda numa loja de teste
com um produto de teste: as contagens das lojas do seed não são tocadas.
Os usuários do seed só são usados em operações de leitura (login,
/produtos, /produtos/buscar).

O TestClient é usado sem "with", de propósito: assim o lifespan da API
não roda e o agendador de zeragem automática não é iniciado.

Uso: python scripts/test_auth_web.py
"""

import re
import sys
import uuid
from dataclasses import asdict
from datetime import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import Depends  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.dependencies import GestorCentralAutenticado, obter_gestor_central  # noqa: E402
from app.core.security import hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.estoque_atual import EstoqueAtual  # noqa: E402
from app.models.historico_contagem import HistoricoContagem  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"

SENHA_TESTE = "senha-teste"
SENHA_SEED = "senha123"
PREFIXO_NEGOCIO_TESTE = "_Teste Auth Web"
EMAIL_TESTE = re.compile(r"^taw_[a-z_]+_[0-9a-f]{8}@teste[.]com$")

# Rota existente só neste processo de teste (não está no código da API):
# a dependency obter_gestor_central ainda não protege nenhuma rota real.
ROTA_GESTOR = "/_teste/gestor"


@app.get(ROTA_GESTOR)
def _rota_teste_gestor(gestor: GestorCentralAutenticado = Depends(obter_gestor_central)):
    return asdict(gestor)


cliente = TestClient(app)
resultados = []


# ----------------------------------------------------------------------
# Utilitários
# ----------------------------------------------------------------------

def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")
    return ok


def checar(nome, resp, status_esperado, trecho=None):
    """[OK] se o status bater e, se informado, o detail contiver o trecho."""
    try:
        corpo = resp.json()
    except ValueError:
        corpo = resp.text
    detalhe = corpo.get("detail") if isinstance(corpo, dict) and "detail" in corpo else corpo
    if resp.status_code != status_esperado:
        return registrar(nome, False, f"esperado {status_esperado}, obtido {resp.status_code} -> {detalhe}")
    if trecho and trecho not in str(detalhe):
        return registrar(nome, False, f"status {resp.status_code} certo, mas pelo motivo errado -> {detalhe}")
    resumo = detalhe if trecho or resp.status_code >= 400 else "ok"
    return registrar(nome, True, f"{resp.status_code} -> {resumo}")


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def login_web(email, senha):
    return cliente.post("/auth/web/login", json={"email": email, "senha": senha})


def login_app(email, senha):
    return cliente.post("/auth/login", json={"email": email, "senha": senha})


def claim_porta(token):
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]).get("porta")


# ----------------------------------------------------------------------
# Dados de teste
# ----------------------------------------------------------------------

def _limpar(db, negocio_ids):
    """Remove tudo o que este teste cria nos negócios informados."""
    if not negocio_ids:
        return
    central_ids = [
        c.id for c in db.query(CentralProducao).filter(CentralProducao.negocio_id.in_(negocio_ids))
    ]
    loja_ids = [lj.id for lj in db.query(Loja).filter(Loja.negocio_id.in_(negocio_ids))]
    produto_ids = [p.id for p in db.query(Produto).filter(Produto.negocio_id.in_(negocio_ids))]

    db.query(HistoricoContagem).filter(HistoricoContagem.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(EstoqueAtual).filter(EstoqueAtual.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    if produto_ids or loja_ids:
        db.query(ProdutoLoja).filter(
            ProdutoLoja.produto_id.in_(produto_ids) | ProdutoLoja.loja_id.in_(loja_ids)
        ).delete(synchronize_session=False)
    db.query(Produto).filter(Produto.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Usuario).filter(
        Usuario.negocio_id.in_(negocio_ids) | Usuario.central_producao_id.in_(central_ids)
    ).delete(synchronize_session=False)
    db.query(Loja).filter(Loja.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(CentralProducao).filter(CentralProducao.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Negocio).filter(Negocio.id.in_(negocio_ids)).delete(synchronize_session=False)
    db.commit()


def _limpar_residuos():
    """Apaga dados de execuções anteriores que quebraram antes da limpeza."""
    db = SessionLocal()
    try:
        negocios = [n for n in db.query(Negocio).all() if n.nome.startswith(PREFIXO_NEGOCIO_TESTE + " ")]
        negocio_ids = [n.id for n in negocios]
        avulsos = [
            u for u in db.query(Usuario).filter(Usuario.email.like("taw_%@teste.com")).all()
            if EMAIL_TESTE.match(u.email) and u.negocio_id not in negocio_ids
        ]
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
        _limpar(db, negocio_ids)
        print("[limpeza inicial] Resíduos apagados.")
    finally:
        db.close()


def _criar_dados(db, run_id):
    negocio_a = Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run_id} A", ativo=True)
    negocio_b = Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run_id} B", ativo=True)
    db.add_all([negocio_a, negocio_b])
    db.flush()

    central_a = CentralProducao(negocio_id=negocio_a.id, nome="_Central Teste A", ativa=True)
    central_inativa = CentralProducao(negocio_id=negocio_a.id, nome="_Central Teste A Inativa", ativa=False)
    central_b = CentralProducao(negocio_id=negocio_b.id, nome="_Central Teste B", ativa=True)
    db.add_all([central_a, central_inativa, central_b])
    db.flush()

    loja_a = Loja(
        negocio_id=negocio_a.id, central_producao_id=central_a.id,
        nome="_Loja Teste A", horario_zeragem=time(6, 0), ativo=True,
    )
    db.add(loja_a)
    db.flush()

    produto = Produto(
        negocio_id=negocio_a.id, nome="_Produto Teste", codigo=f"TST-{run_id}",
        unidade_medida=UnidadeMedida.UN, ativo=True,
    )
    db.add(produto)
    db.flush()
    db.add(ProdutoLoja(produto_id=produto.id, loja_id=loja_a.id))

    def usuario(rotulo, **campos):
        u = Usuario(
            negocio_id=negocio_a.id, nome=f"Teste {rotulo}",
            email=f"taw_{rotulo}_{run_id}@teste.com", senha_hash=hash_senha(SENHA_TESTE),
            status=campos.pop("status", StatusUsuario.ATIVO),
            tem_acesso_app=campos.pop("tem_acesso_app", False),
            tem_acesso_web=campos.pop("tem_acesso_web", False),
            **campos,
        )
        db.add(u)
        db.flush()
        return u

    gestor = dict(tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=central_a.id)
    operador = dict(tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=loja_a.id)
    dados = {
        "negocio_ids": [negocio_a.id, negocio_b.id],
        "central_a": central_a,
        "loja_a": loja_a,
        "produto": produto,
        "gestor_valido": usuario("gestor_valido", tem_acesso_web=True, **gestor),
        "gestor_sem_web": usuario("gestor_sem_web", **gestor),
        "gestor_bloqueado": usuario("gestor_bloqueado", tem_acesso_web=True, status=StatusUsuario.BLOQUEADO, **gestor),
        "gestor_cruzado": usuario(
            "gestor_cruzado", tem_acesso_web=True,
            tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=central_b.id,
        ),
        "gestor_central_inativa": usuario(
            "gestor_central_inativa", tem_acesso_web=True,
            tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=central_inativa.id,
        ),
        "gestor_com_app": usuario("gestor_com_app", tem_acesso_web=True, tem_acesso_app=True, **gestor),
        "operador_web": usuario("operador_web", tem_acesso_web=True, tem_acesso_app=True, **operador),
        "operador_app": usuario("operador_app", tem_acesso_app=True, **operador),
    }
    db.commit()
    return dados


# ----------------------------------------------------------------------
# Casos
# ----------------------------------------------------------------------

def testar_saas(db, d):
    print("  (rodando casos do SaaS web...)")
    gv = d["gestor_valido"]

    # W1: login do gestor válido, claim porta=web, token aceito pela dependency
    r = login_web(gv.email, SENHA_TESTE)
    if checar("W1 login web do gestor valido", r, 200):
        tokens = r.json()
        registrar(
            "W1b claim porta nos tokens web",
            claim_porta(tokens["access_token"]) == "web" and claim_porta(tokens["refresh_token"]) == "web",
            f"access={claim_porta(tokens['access_token'])!r}, refresh={claim_porta(tokens['refresh_token'])!r}",
        )
        r2 = cliente.get(ROTA_GESTOR, headers=bearer(tokens["access_token"]))
        ok = r2.status_code == 200 and r2.json() == {
            "usuario_id": gv.id, "negocio_id": gv.negocio_id, "central_producao_id": d["central_a"].id,
        }
        registrar("W1c access token web passa na obter_gestor_central", ok, f"{r2.status_code} -> {r2.json()}")
    else:
        tokens = None

    checar("W2 senha errada", login_web(gv.email, "errada"), 401, "E-mail ou senha incorretos")
    checar("W3 e-mail inexistente", login_web("ninguem_x@teste.com", SENHA_TESTE), 401, "E-mail ou senha incorretos")
    checar("W4 operador de loja (com tem_acesso_web)", login_web(d["operador_web"].email, SENHA_TESTE), 403, "restrito a gestores")
    checar("W5 gestor sem tem_acesso_web", login_web(d["gestor_sem_web"].email, SENHA_TESTE), 403, "sistema web")
    checar("W6 gestor bloqueado", login_web(d["gestor_bloqueado"].email, SENHA_TESTE), 403, "bloqueado")
    checar("W7 gestor com central de outro negocio", login_web(d["gestor_cruzado"].email, SENHA_TESTE), 403, "central de produção válida")
    checar("W8 gestor com central inativa", login_web(d["gestor_central_inativa"].email, SENHA_TESTE), 403, "está inativa")

    if tokens is None:
        registrar("W9-W15", False, "sem tokens do W1 para continuar")
        return

    # W9: refresh válido
    r = cliente.post("/auth/web/refresh", json={"refresh_token": tokens["refresh_token"]})
    if checar("W9 refresh web valido", r, 200):
        novo = r.json()["access_token"]
        r2 = cliente.get(ROTA_GESTOR, headers=bearer(novo))
        registrar(
            "W9b novo access token (porta web) funciona",
            claim_porta(novo) == "web" and r2.status_code == 200,
            f"porta={claim_porta(novo)!r}, rota -> {r2.status_code}",
        )

    checar(
        "W10 access token usado como refresh",
        cliente.post("/auth/web/refresh", json={"refresh_token": tokens["access_token"]}),
        401,
    )

    r_app = login_app(d["operador_app"].email, SENHA_TESTE)
    if r_app.status_code == 200:
        tokens_app = r_app.json()
        checar(
            "W11 refresh token do app em /auth/web/refresh",
            cliente.post("/auth/web/refresh", json={"refresh_token": tokens_app["refresh_token"]}),
            401,
        )
        checar("W14 token do app na rota do gestor", cliente.get(ROTA_GESTOR, headers=bearer(tokens_app["access_token"])), 401)
    else:
        registrar("W11/W14", False, f"login do operador_app no app falhou: {r_app.status_code}")

    checar("W13 token web do gestor em rota do app (/produtos)", cliente.get("/produtos", headers=bearer(tokens["access_token"])), 401)

    # W15: refresh token web na rota de refresh do APP -> 401 (D10). Usa o
    # gestor com tem_acesso_app ligado: sem a checagem da claim "porta",
    # este é o único usuário que a rota do app aceitaria.
    r = login_web(d["gestor_com_app"].email, SENHA_TESTE)
    if r.status_code == 200:
        checar(
            "W15 refresh token web em /auth/refresh do app",
            cliente.post("/auth/refresh", json={"refresh_token": r.json()["refresh_token"]}),
            401,
        )
    else:
        registrar("W15", False, f"login web do gestor_com_app falhou: {r.status_code}")

    # W12: revogação depois do login: refresh e access antigos recusados
    gv_db = db.get(Usuario, gv.id)
    gv_db.tem_acesso_web = False
    db.commit()
    checar(
        "W12 refresh depois de revogar tem_acesso_web",
        cliente.post("/auth/web/refresh", json={"refresh_token": tokens["refresh_token"]}),
        403, "sistema web",
    )
    checar("W12b access antigo depois da revogacao", cliente.get(ROTA_GESTOR, headers=bearer(tokens["access_token"])), 403, "sistema web")


def testar_regressao_app(db, d):
    print("  (rodando regressão do app...)")

    # Usuário do seed, só leitura.
    r = login_app("admin@teste.com", SENHA_SEED)
    if checar("A1 login app admin@teste.com (seed)", r, 200):
        t = r.json()
        registrar("A1b token do app sem claim porta", claim_porta(t["access_token"]) is None, f"porta={claim_porta(t['access_token'])!r}")
        r2 = cliente.get("/produtos", headers=bearer(t["access_token"]))
        n = len(r2.json()) if r2.status_code == 200 else None
        registrar("A2 GET /produtos (admin)", r2.status_code == 200 and n == 11, f"{r2.status_code} -> {n} produtos")
        r3 = cliente.get("/produtos/buscar", params={"q": "INT-001"}, headers=bearer(t["access_token"]))
        nome = r3.json().get("nome") if r3.status_code == 200 else r3.text
        registrar("A3 GET /produtos/buscar?q=INT-001", r3.status_code == 200 and nome == "Croissant", f"{r3.status_code} -> {nome}")
        r4 = cliente.post("/auth/refresh", json={"refresh_token": t["refresh_token"]})
        if checar("A6 POST /auth/refresh (app)", r4, 200):
            r5 = cliente.get("/produtos", headers=bearer(r4.json()["access_token"]))
            registrar("A6b token renovado funciona no /produtos", r5.status_code == 200, f"{r5.status_code}")
    checar("A4 GET /produtos sem token (comportamento antigo: 403)", cliente.get("/produtos"), 403, "Not authenticated")
    checar("A5 GET /produtos com token invalido", cliente.get("/produtos", headers=bearer("abc.def.ghi")), 401)
    checar("A7 login app do gestor do seed", login_app("gestor@teste.com", SENHA_SEED), 403, "permissão para acessar o app")

    # Fluxo completo de contagem + zeragem numa loja de teste.
    r = login_app(d["operador_app"].email, SENHA_TESTE)
    if not checar("A8 login app operador da loja de teste", r, 200):
        return
    h = bearer(r.json()["access_token"])
    pid = d["produto"].id

    r = cliente.get("/produtos", headers=h)
    registrar("A8b GET /produtos (loja de teste)", r.status_code == 200 and [p["id"] for p in r.json()] == [pid],
              f"{r.status_code} -> {[p['nome'] for p in r.json()] if r.status_code == 200 else r.text}")

    r = cliente.patch(f"/estoque/{pid}", json={"quantidade_inventariada": 7}, headers=h)
    ok = r.status_code == 200 and r.json().get("quantidade_inventariada") == 7
    registrar("A8c PATCH /estoque (contagem = 7)", ok, f"{r.status_code} -> {r.json()}")

    r = cliente.post("/zeragem/executar-agora", headers=h)
    ok = r.status_code == 200 and r.json()["detalhes"][0]["produtos_processados"] == 1
    registrar("A8d POST /zeragem/executar-agora", ok, f"{r.status_code} -> {r.json()}")

    r = cliente.get("/produtos", headers=h)
    qtd = r.json()[0]["quantidade_inventariada"] if r.status_code == 200 and r.json() else None
    registrar("A8e contagem zerada depois da zeragem", qtd == 0, f"quantidade_inventariada={qtd}")

    db.expire_all()
    hist = db.query(HistoricoContagem).filter(HistoricoContagem.loja_id == d["loja_a"].id).all()
    registrar(
        "A8f snapshot gravado em historico_contagens",
        len(hist) == 1 and hist[0].quantidade_inventariada == 7,
        f"{len(hist)} linha(s), quantidade={[h_.quantidade_inventariada for h_ in hist]}",
    )

    checar("A10 segunda zeragem no mesmo dia sem forcar", cliente.post("/zeragem/executar-agora", headers=h), 409, "já foi zerada hoje")

    # D10: gestor com tem_acesso_app ligado. A rota de login do app não foi
    # alterada (emite token), mas a dependency do app recusa o uso.
    r = login_app(d["gestor_com_app"].email, SENHA_TESTE)
    if checar("A9 login app de gestor com tem_acesso_app (rota inalterada)", r, 200):
        h2 = bearer(r.json()["access_token"])
        checar("A9b gestor no GET /produtos (D10)", cliente.get("/produtos", headers=h2), 403, "restrito a operadores")
        checar("A9c gestor no POST /zeragem (D10)", cliente.post("/zeragem/executar-agora", headers=h2), 403, "restrito a operadores")


def main():
    _limpar_residuos()
    db = SessionLocal()
    negocio_ids = []
    try:
        run_id = uuid.uuid4().hex[:8]
        dados = _criar_dados(db, run_id)
        negocio_ids = dados["negocio_ids"]
        testar_saas(db, dados)
        testar_regressao_app(db, dados)
    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste de auth web + regressão do app ===")
            for r in resultados:
                print(r)
            falhas = [r for r in resultados if r.startswith(FAIL)]
            print(f"\n{len(resultados)} verificações; " + ("TODAS PASSARAM" if not falhas else f"{len(falhas)} FALHARAM"))
        finally:
            try:
                db.rollback()
                _limpar(db, negocio_ids)
            except Exception as e:
                print(f"[aviso] Erro na limpeza: {e}")
            db.close()

    if not resultados or any(r.startswith(FAIL) for r in resultados):
        sys.exit(1)


if __name__ == "__main__":
    main()
