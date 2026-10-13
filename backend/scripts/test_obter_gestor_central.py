"""
Testa a dependency obter_gestor_central (app/core/dependencies.py).

Casos:
  [1]  gestor do seed (gestor@teste.com) válido -> passa, com negocio_id e central_producao_id corretos
  [2]  sem token -> 401
  [3a] token inválido -> 401
  [3b] token expirado -> 401
  [3c] refresh token no lugar do access token -> 401
  [4]  operador de loja (mesmo com tem_acesso_web=True) -> 403
  [5]  gestor com tem_acesso_web=False -> 403
  [6]  gestor bloqueado (status != ativo) -> 403
  [7]  gestor ligado a uma central de outro negócio -> 403
  [8]  gestor ligado a uma central inativa -> 403 (decisão D4)
  [9]  token do app (sem a claim "porta": "web") de um gestor válido -> 401 (decisão D10)

Os tokens são gerados direto (criar_access_token com porta=PORTA_WEB),
sem passar por /auth/web/login: o teste é da dependency, não do login
(as rotas de login têm o próprio teste, test_auth_web.py). Cada chamada
monta uma requisição real e passa pelo esquema bearer_scheme_web antes da
dependency, o mesmo caminho que o FastAPI percorre (sem subir servidor).

Pré-requisitos: migration 0014 aplicada e `python scripts/seed_dev.py`.

Saída só com caracteres que o console do Windows (cp1252) imprime, e
limpeza de resíduos no início e no fim (mesmo padrão do
test_constraint_usuario.py).

Uso: python scripts/test_obter_gestor_central.py
"""

import asyncio
import re
import sys
import uuid
from datetime import time, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.core.dependencies import bearer_scheme_web, obter_gestor_central  # noqa: E402
from app.core.security import PORTA_WEB, _criar_token, criar_access_token, criar_refresh_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 11

EMAIL_GESTOR_SEED = "gestor@teste.com"

# Identificação dos dados criados por este teste.
PREFIXO_NEGOCIO_TESTE = "_Teste Gestor Central"
EMAIL_TESTE = re.compile(r"^tgc_[a-z_]+_[0-9a-f]{8}@teste[.]com$")


def _limpar(db, negocio_ids):
    """Remove os dados de teste dos negócios informados."""
    if not negocio_ids:
        return
    central_ids = [
        c.id for c in db.query(CentralProducao).filter(CentralProducao.negocio_id.in_(negocio_ids))
    ]
    # Usuários primeiro: o gestor do caso 7 pertence a um negócio e aponta
    # para a central do outro.
    db.query(Usuario).filter(
        (Usuario.negocio_id.in_(negocio_ids)) | (Usuario.central_producao_id.in_(central_ids))
    ).delete(synchronize_session=False)
    db.query(Loja).filter(Loja.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(CentralProducao).filter(CentralProducao.negocio_id.in_(negocio_ids)).delete(
        synchronize_session=False
    )
    db.query(Negocio).filter(Negocio.id.in_(negocio_ids)).delete(synchronize_session=False)
    db.commit()


def _limpar_residuos():
    """
    Apaga dados de teste deixados por execuções anteriores que quebraram
    antes da limpeza. Mostra o que encontrou antes de apagar.
    """
    db = SessionLocal()
    try:
        negocios = [
            n for n in db.query(Negocio).all()
            if n.nome.startswith(PREFIXO_NEGOCIO_TESTE + " ")
        ]
        negocio_ids = [n.id for n in negocios]
        usuarios_avulsos = [
            u for u in db.query(Usuario).filter(Usuario.email.like("tgc_%@teste.com")).all()
            if EMAIL_TESTE.match(u.email) and u.negocio_id not in negocio_ids
        ]

        if not negocios and not usuarios_avulsos:
            print("[limpeza inicial] Nenhum resíduo de teste encontrado.")
            return

        print("[limpeza inicial] Resíduos de execuções anteriores encontrados:")
        for n in negocios:
            emails = [u.email for u in db.query(Usuario).filter(Usuario.negocio_id == n.id)]
            print(f"  negocio id={n.id} nome={n.nome!r} usuarios={emails}")
        for u in usuarios_avulsos:
            print(f"  usuario avulso id={u.id} email={u.email!r} negocio_id={u.negocio_id}")

        for u in usuarios_avulsos:
            db.delete(u)
        db.commit()
        _limpar(db, negocio_ids)
        print("[limpeza inicial] Resíduos apagados.")
    finally:
        db.close()


def _chamar_dependency(db, token):
    """
    Monta uma requisição (com ou sem header Authorization), passa pelo
    bearer_scheme_web e chama a dependency. Devolve (status_code, resultado):
    200 e o GestorCentralAutenticado, ou o status e o detail da HTTPException.
    """
    headers = [] if token is None else [(b"authorization", f"Bearer {token}".encode())]
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": headers})
    credenciais = asyncio.run(bearer_scheme_web(request))
    try:
        return 200, obter_gestor_central(credenciais=credenciais, db=db)
    except HTTPException as e:
        return e.status_code, e.detail


def _verificar_recusa(resultados, nome, db, token, status_esperado, trecho_detail=None):
    """Registra [OK] se a dependency recusar com o status (e a mensagem) esperados."""
    try:
        status_obtido, detalhe = _chamar_dependency(db, token)
    except Exception as e:
        resultados.append(f"{FAIL} {nome}: erro inesperado -> {type(e).__name__}: {e}")
        return
    if status_obtido != status_esperado:
        resultados.append(f"{FAIL} {nome}: esperado {status_esperado}, obtido {status_obtido} -> {detalhe}")
    elif trecho_detail and trecho_detail not in str(detalhe):
        resultados.append(
            f"{FAIL} {nome}: status {status_obtido} certo, mas pelo motivo errado -> {detalhe}"
        )
    else:
        resultados.append(f"{PASS} {nome}: {status_obtido} -> {detalhe}")


def _criar_usuario(db, negocio_id, run_id, rotulo, **campos):
    usuario = Usuario(
        negocio_id=negocio_id,
        nome=f"Teste {rotulo}",
        email=f"tgc_{rotulo}_{run_id}@teste.com",
        senha_hash=hash_senha("x"),
        tem_acesso_app=False,
        **campos,
    )
    db.add(usuario)
    db.flush()
    return usuario


def main():
    _limpar_residuos()

    db = SessionLocal()
    negocio_ids = []
    resultados = []
    try:
        # --- Setup: negócio A (central + loja) e negócio B (só central) ---
        run_id = uuid.uuid4().hex[:8]
        negocio_a = Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run_id} A", ativo=True)
        negocio_b = Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run_id} B", ativo=True)
        db.add_all([negocio_a, negocio_b])
        db.flush()
        negocio_ids = [negocio_a.id, negocio_b.id]

        central_a = CentralProducao(negocio_id=negocio_a.id, nome="_Central Teste A", ativa=True)
        central_b = CentralProducao(negocio_id=negocio_b.id, nome="_Central Teste B", ativa=True)
        # Mesmo negócio do gestor, mas desativada (caso 8).
        central_inativa = CentralProducao(negocio_id=negocio_a.id, nome="_Central Teste A Inativa", ativa=False)
        db.add_all([central_a, central_b, central_inativa])
        db.flush()

        loja_a = Loja(
            negocio_id=negocio_a.id,
            central_producao_id=central_a.id,
            nome="_Loja Teste A",
            horario_zeragem=time(6, 0),
            ativo=True,
        )
        db.add(loja_a)
        db.flush()

        operador = _criar_usuario(
            db, negocio_a.id, run_id, "operador",
            tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=loja_a.id,
            status=StatusUsuario.ATIVO, tem_acesso_web=True,
        )
        gestor_sem_web = _criar_usuario(
            db, negocio_a.id, run_id, "gestor_sem_web",
            tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=central_a.id,
            status=StatusUsuario.ATIVO, tem_acesso_web=False,
        )
        gestor_bloqueado = _criar_usuario(
            db, negocio_a.id, run_id, "gestor_bloqueado",
            tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=central_a.id,
            status=StatusUsuario.BLOQUEADO, tem_acesso_web=True,
        )
        gestor_cruzado = _criar_usuario(
            db, negocio_a.id, run_id, "gestor_cruzado",
            tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=central_b.id,
            status=StatusUsuario.ATIVO, tem_acesso_web=True,
        )
        gestor_central_inativa = _criar_usuario(
            db, negocio_a.id, run_id, "gestor_central_inativa",
            tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=central_inativa.id,
            status=StatusUsuario.ATIVO, tem_acesso_web=True,
        )
        db.commit()

        # ---- CASO 1: gestor do seed válido ----
        nome = "CASO 1 (gestor do seed valido)"
        gestor = db.query(Usuario).filter(Usuario.email == EMAIL_GESTOR_SEED).first()
        if gestor is None:
            resultados.append(f"{FAIL} {nome}: {EMAIL_GESTOR_SEED} não existe -> rode scripts/seed_dev.py")
        else:
            central_gestor = db.get(CentralProducao, gestor.central_producao_id)
            try:
                status_obtido, resultado = _chamar_dependency(
                    db, criar_access_token(usuario_id=gestor.id, negocio_id=gestor.negocio_id, porta=PORTA_WEB)
                )
                esperado = (gestor.id, gestor.negocio_id, gestor.central_producao_id)
                obtido = (
                    (resultado.usuario_id, resultado.negocio_id, resultado.central_producao_id)
                    if status_obtido == 200 else None
                )
                if status_obtido != 200:
                    resultados.append(f"{FAIL} {nome}: esperado 200, obtido {status_obtido} -> {resultado}")
                elif obtido != esperado or central_gestor.negocio_id != resultado.negocio_id:
                    resultados.append(f"{FAIL} {nome}: dados errados -> esperado {esperado}, obtido {obtido}")
                else:
                    resultados.append(
                        f"{PASS} {nome}: 200 -> usuario_id={resultado.usuario_id}, "
                        f"negocio_id={resultado.negocio_id}, central_producao_id={resultado.central_producao_id}"
                    )
            except Exception as e:
                resultados.append(f"{FAIL} {nome}: erro inesperado -> {type(e).__name__}: {e}")

        # ---- CASO 2: sem token ----
        _verificar_recusa(resultados, "CASO 2 (sem token)", db, None, 401)

        # ---- CASO 3: token inválido, expirado, ou refresh no lugar de access ----
        _verificar_recusa(resultados, "CASO 3a (token invalido)", db, "abc.def.ghi", 401)
        if gestor is not None:
            token_expirado = _criar_token(
                {"sub": str(gestor.id), "negocio_id": gestor.negocio_id, "porta": PORTA_WEB},
                expira_em=timedelta(minutes=-1),
                tipo="access",
            )
            _verificar_recusa(resultados, "CASO 3b (token expirado)", db, token_expirado, 401)
            token_refresh = criar_refresh_token(usuario_id=gestor.id, negocio_id=gestor.negocio_id, porta=PORTA_WEB)
            _verificar_recusa(resultados, "CASO 3c (refresh token como access)", db, token_refresh, 401)
            token_app = criar_access_token(usuario_id=gestor.id, negocio_id=gestor.negocio_id)
            _verificar_recusa(resultados, "CASO 9 (token do app, sem porta web)", db, token_app, 401)
        else:
            resultados.append(f"{FAIL} CASO 3b/3c/9: sem o gestor do seed para gerar o token")

        # ---- CASOS 4 a 7: usuários sem permissão ----
        def token_de(u):
            return criar_access_token(usuario_id=u.id, negocio_id=u.negocio_id, porta=PORTA_WEB)

        _verificar_recusa(
            resultados, "CASO 4 (operador de loja com tem_acesso_web)", db,
            token_de(operador), 403, "restrito a gestores",
        )
        _verificar_recusa(
            resultados, "CASO 5 (gestor sem tem_acesso_web)", db,
            token_de(gestor_sem_web), 403, "sistema web",
        )
        _verificar_recusa(
            resultados, "CASO 6 (gestor bloqueado)", db,
            token_de(gestor_bloqueado), 403, "bloqueado",
        )
        _verificar_recusa(
            resultados, "CASO 7 (gestor com central de outro negocio)", db,
            token_de(gestor_cruzado), 403, "central de produção válida",
        )
        _verificar_recusa(
            resultados, "CASO 8 (gestor com central inativa)", db,
            token_de(gestor_central_inativa), 403, "está inativa",
        )

    finally:
        try:
            print("\n=== Resultado do teste de obter_gestor_central ===")
            for r in resultados:
                print(r)
            falhas = [r for r in resultados if r.startswith(FAIL)]
            if len(resultados) < TOTAL_CASOS:
                print(f"\nTESTE INCOMPLETO: só {len(resultados)} de {TOTAL_CASOS} casos rodaram")
            else:
                print(f"\n{'TODOS OS CASOS PASSARAM' if not falhas else f'{len(falhas)} CASO(S) FALHARAM'}")
        finally:
            # Roda mesmo que a impressão acima falhe.
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
