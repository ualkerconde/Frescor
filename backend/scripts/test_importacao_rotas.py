"""
Testa as rotas POST /vendas/importar e POST /perdas/importar (Fase 2 / P5)
por HTTP, com o TestClient.

Cenário: negócio A com central A1 (loja T01, produto P-UN habilitado e P-NH
sem habilitação) e central A2 (com o próprio gestor). Usuários: gestor
válido de A1, gestor de A2, gestor sem tem_acesso_web, operador de loja.
Tokens gerados direto (porta web para o SaaS, sem porta para o app).

Casos:
  R1  sem token -> 401
  R2  token do app (operador) -> 401
  R3  gestor sem tem_acesso_web -> 403
  R4  importação válida de vendas -> 200, relatório com inseridas
  R5  reimportação -> 200, substituídas
  R6  importação de perdas -> 200, grava em perdas_diarias
  R7  produto não habilitado -> 200 com aviso
  R8  arquivo com erros -> 422, relatório com erros por linha, nada gravado
  R9  gestor de outra central tenta importar na loja T01 -> 422, nada gravado
  R10 arquivo maior que o limite -> 413, nada gravado
  R11 arquivo exatamente no limite -> não é 413 (é processado)
  R12 sem o campo "arquivo" no formulário -> 422 da validação do FastAPI
  R13 /perdas/importar também exige autenticação -> 401 sem token

Uso: python scripts/test_importacao_rotas.py
"""

import re
import sys
import uuid
from datetime import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.importacao import LIMITE_ARQUIVO_BYTES  # noqa: E402
from app.core.security import PORTA_WEB, criar_access_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.perda_diaria import PerdaDiaria  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402
from app.models.venda_diaria import VendaDiaria  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
PREFIXO_NEGOCIO_TESTE = "_Teste Rotas Importacao"
EMAIL_TESTE = re.compile(r"^tri_[a-z_0-9]+_[0-9a-f]{8}@teste[.]com$")
CAB = "data;codigo_loja;codigo_produto;quantidade"

cliente = TestClient(app)
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def csv_bytes(linhas):
    return ("\r\n".join([CAB] + linhas) + "\r\n").encode("utf-8")


def enviar(rota, conteudo, token=None, campo="arquivo"):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    files = {campo: ("vendas.csv", conteudo, "text/csv")}
    return cliente.post(rota, files=files, headers=headers)


def contar(db, negocio_id):
    db.expire_all()
    return (
        db.query(VendaDiaria).filter(VendaDiaria.negocio_id == negocio_id).count(),
        db.query(PerdaDiaria).filter(PerdaDiaria.negocio_id == negocio_id).count(),
    )


def corpo(r):
    try:
        return r.json()
    except ValueError:
        return r.text


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    db.query(VendaDiaria).filter(VendaDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(PerdaDiaria).filter(PerdaDiaria.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
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
        avulsos = [u for u in db.query(Usuario).filter(Usuario.email.like("tri_%@teste.com")).all()
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
        neg = Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run_id}", ativo=True)
        db.add(neg)
        db.flush()
        negocio_ids = [neg.id]
        c1 = CentralProducao(negocio_id=neg.id, nome="_Central A1", ativa=True)
        c2 = CentralProducao(negocio_id=neg.id, nome="_Central A2", ativa=True)
        db.add_all([c1, c2])
        db.flush()
        t01 = Loja(negocio_id=neg.id, central_producao_id=c1.id, nome="_Loja T01", codigo="T01",
                   horario_zeragem=time(6, 0), ativo=True)
        db.add(t01)
        p_un = Produto(negocio_id=neg.id, nome="_P-UN", codigo="P-UN", unidade_medida=UnidadeMedida.UN, ativo=True)
        p_nh = Produto(negocio_id=neg.id, nome="_P-NH", codigo="P-NH", unidade_medida=UnidadeMedida.UN, ativo=True)
        db.add_all([p_un, p_nh])
        db.flush()
        db.add(ProdutoLoja(produto_id=p_un.id, loja_id=t01.id))

        def usuario(rotulo, **campos):
            u = Usuario(negocio_id=neg.id, nome=f"Teste {rotulo}", email=f"tri_{rotulo}_{run_id}@teste.com",
                        senha_hash=hash_senha("x"), status=StatusUsuario.ATIVO, **campos)
            db.add(u)
            db.flush()
            return u

        gestor = usuario("gestor_a1", tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=c1.id,
                         tem_acesso_web=True, tem_acesso_app=False)
        gestor_a2 = usuario("gestor_a2", tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=c2.id,
                            tem_acesso_web=True, tem_acesso_app=False)
        gestor_sem_web = usuario("gestor_sem_web", tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=c1.id,
                                 tem_acesso_web=False, tem_acesso_app=False)
        operador = usuario("operador", tipo_usuario=TipoUsuario.OPERADOR_LOJA, loja_id=t01.id,
                           tem_acesso_web=False, tem_acesso_app=True)
        db.commit()

        tk = lambda u: criar_access_token(u.id, u.negocio_id, porta=PORTA_WEB)  # noqa: E731
        tk_gestor = tk(gestor)
        valido = csv_bytes(["01/09/2026;T01;P-UN;10", "02/09/2026;T01;P-UN;12"])

        # ---- autenticação ----
        r = enviar("/vendas/importar", valido)
        registrar("R1 sem token", r.status_code == 401, f"{r.status_code} -> {corpo(r)}")
        r = enviar("/vendas/importar", valido, criar_access_token(operador.id, operador.negocio_id))
        registrar("R2 token do app (operador)", r.status_code == 401, f"{r.status_code} -> {corpo(r)}")
        r = enviar("/vendas/importar", valido, tk(gestor_sem_web))
        registrar("R3 gestor sem tem_acesso_web", r.status_code == 403, f"{r.status_code} -> {corpo(r)}")
        registrar("R1-R3b nada gravado", contar(db, neg.id) == (0, 0), f"(vendas, perdas)={contar(db, neg.id)}")

        # ---- sucesso ----
        r = enviar("/vendas/importar", valido, tk_gestor)
        b = corpo(r)
        registrar("R4 importacao valida de vendas",
                  r.status_code == 200 and b["sucesso"] and b["inseridas"] == 2 and b["erros"] == [] and b["avisos"] == [],
                  f"{r.status_code} -> {b}")
        r = enviar("/vendas/importar", csv_bytes(["01/09/2026;T01;P-UN;11"]), tk_gestor)
        b = corpo(r)
        registrar("R5 reimportacao substitui", r.status_code == 200 and b["substituidas"] == 1 and b["inseridas"] == 0,
                  f"{r.status_code} -> inseridas={b.get('inseridas')}, substituidas={b.get('substituidas')}")
        r = enviar("/perdas/importar", csv_bytes(["01/09/2026;T01;P-UN;1"]), tk_gestor)
        b = corpo(r)
        registrar("R6 importacao de perdas", r.status_code == 200 and b["inseridas"] == 1 and contar(db, neg.id) == (2, 1),
                  f"{r.status_code} -> inseridas={b.get('inseridas')}; (vendas, perdas)={contar(db, neg.id)}")
        r = enviar("/vendas/importar", csv_bytes(["03/09/2026;T01;P-NH;2"]), tk_gestor)
        b = corpo(r)
        registrar("R7 produto nao habilitado: 200 com aviso",
                  r.status_code == 200 and len(b["avisos"]) == 1 and "não está habilitado" in b["avisos"][0]["mensagem"],
                  f"{r.status_code} -> avisos={b.get('avisos')}")

        # ---- erros ----
        antes = contar(db, neg.id)
        r = enviar("/vendas/importar", csv_bytes(["04/09/2026;T01;P-UN;5", "31/02/2026;T01;P-UN;1", "04/09/2026;T01;X;1"]), tk_gestor)
        b = corpo(r)
        ok = (r.status_code == 422 and b["sucesso"] is False and [e["linha"] for e in b["erros"]] == [3, 4]
              and contar(db, neg.id) == antes)
        registrar("R8 arquivo com erros -> 422 com relatorio", ok,
                  f"{r.status_code} -> erros={b.get('erros') if isinstance(b, dict) else b}; gravado? {contar(db, neg.id) != antes}")

        r = enviar("/vendas/importar", csv_bytes(["05/09/2026;T01;P-UN;5"]), tk(gestor_a2))
        b = corpo(r)
        ok = (r.status_code == 422 and "não encontrada entre as lojas da sua central" in b["erros"][0]["mensagem"]
              and contar(db, neg.id) == antes)
        registrar("R9 gestor de outra central na loja T01", ok, f"{r.status_code} -> {b.get('erros') if isinstance(b, dict) else b}")

        grande = csv_bytes(["01/09/2026;T01;P-UN;1"]) + b"x" * LIMITE_ARQUIVO_BYTES
        r = enviar("/vendas/importar", grande, tk_gestor)
        registrar("R10 arquivo maior que o limite -> 413", r.status_code == 413 and contar(db, neg.id) == antes,
                  f"{r.status_code} -> {corpo(r)} ({len(grande)} bytes; limite {LIMITE_ARQUIVO_BYTES})")

        no_limite = csv_bytes(["01/09/2026;T01;P-UN;1"])
        no_limite = no_limite + b" " * (LIMITE_ARQUIVO_BYTES - len(no_limite))
        # No limite exato o arquivo é processado (não é 413). Os espaços de
        # enchimento formam um campo enorme, que o serviço recusa com o
        # relatório em português (422) -- prova de que passou pelo serviço.
        r = enviar("/vendas/importar", no_limite, tk_gestor)
        b = corpo(r)
        ok = (r.status_code == 422 and isinstance(b, dict) and b.get("sucesso") is False
              and "não pôde ser lido como CSV" in b["erros"][0]["mensagem"])
        registrar("R11 arquivo exatamente no limite e processado (nao e 413)", ok,
                  f"{r.status_code} ({len(no_limite)} bytes) -> {b['erros'][0]['mensagem'][:90] if isinstance(b, dict) and b.get('erros') else b}")

        r = enviar("/vendas/importar", valido, tk_gestor, campo="outro_nome")
        b = corpo(r)
        registrar("R12 sem o campo 'arquivo' -> 422 do FastAPI",
                  r.status_code == 422 and isinstance(b, dict) and "detail" in b and "sucesso" not in b,
                  f"{r.status_code} -> {str(b)[:120]}")

        r = enviar("/perdas/importar", valido)
        registrar("R13 /perdas/importar sem token", r.status_code == 401, f"{r.status_code} -> {corpo(r)}")

    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            print("\n=== Resultado do teste das rotas de importação ===")
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
