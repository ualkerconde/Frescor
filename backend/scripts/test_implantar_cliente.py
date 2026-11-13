"""
Testa o script de implantação de cliente (scripts/implantar_cliente.py).

Casos:
  I1 simulação (sem --aplicar): nada gravado
  I2 --aplicar: negócio, central (seção, prazo), loja (código, horários),
     gestor (sem loja, só SaaS) e operador (loja, só app) criados; a senha
     provisória mostrada confere com o hash
  I3 rodar de novo: nada criado, nenhuma senha nova, nada alterado
  I4 e-mail já usado em outro negócio: erro e NADA gravado (nem a loja nova
     que vinha antes no arquivo)
  I5 loja com código já ligada a outra central: erro
  I6 arquivo inválido: seção, código repetido, e-mail inválido, hora, central
     sem gestor, e-mail repetido -> erro antes de tocar no banco
  I7 o exemplo do repositório (exemplo_implantacao.json) é válido

Uso: python scripts/test_implantar_cliente.py
"""

import contextlib
import io
import json
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent))

import implantar_cliente as ic  # noqa: E402
from app.core.security import verificar_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402

PREFIXO = "TESTE_IMPLANTACAO"
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{'[OK]' if ok else '[FALHA]'} {nome}: {detalhe}")


def config(run, negocio=None, codigo="001", gestor=None, operador=None, central="Padaria"):
    return {
        "negocio": negocio or f"{PREFIXO} {run}",
        "centrais": [{
            "nome": central, "secao": "padaria", "prazo_entrega_dias": 1,
            "gestores": [{"nome": "Gestora", "email": gestor or f"gestora.{run}@teste.com"}],
            "lojas": [{"nome": "Loja Centro", "codigo": codigo, "horario_fechamento": "20:30",
                       "operadores": [{"nome": "Operador", "email": operador or f"op.{run}@teste.com"}]}],
        }],
    }


def rodar(cfg, aplicar):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(cfg, f)
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        codigo = ic.main([f.name] + (["--aplicar"] if aplicar else []))
    Path(f.name).unlink()
    return codigo, saida.getvalue()


def limpar(db):
    ids = [n.id for n in db.query(Negocio).filter(Negocio.nome.like(f"{PREFIXO} %"))]
    if ids:
        db.query(Usuario).filter(Usuario.negocio_id.in_(ids)).delete(synchronize_session=False)
        db.query(Loja).filter(Loja.negocio_id.in_(ids)).delete(synchronize_session=False)
        db.query(CentralProducao).filter(CentralProducao.negocio_id.in_(ids)).delete(synchronize_session=False)
        db.query(Negocio).filter(Negocio.id.in_(ids)).delete(synchronize_session=False)
        db.commit()


def contar(db, run):
    neg = db.query(Negocio).filter(Negocio.nome == f"{PREFIXO} {run}").first()
    if neg is None:
        return (0, 0, 0, 0)
    return (1, db.query(CentralProducao).filter_by(negocio_id=neg.id).count(),
            db.query(Loja).filter_by(negocio_id=neg.id).count(), db.query(Usuario).filter_by(negocio_id=neg.id).count())


def main():
    db = SessionLocal()
    limpar(db)
    run = uuid.uuid4().hex[:8]
    try:
        cfg = config(run)
        codigo, saida = rodar(cfg, aplicar=False)
        db.expire_all()
        registrar("I1 simulacao nao grava", codigo == 0 and contar(db, run) == (0, 0, 0, 0) and "SIMULAÇÃO" in saida,
                  f"saida {codigo}, contagem {contar(db, run)}")

        codigo, saida = rodar(cfg, aplicar=True)
        db.expire_all()
        neg = db.query(Negocio).filter(Negocio.nome == f"{PREFIXO} {run}").one()
        central = db.query(CentralProducao).filter_by(negocio_id=neg.id).one()
        loja = db.query(Loja).filter_by(negocio_id=neg.id).one()
        gestora = db.query(Usuario).filter_by(email=f"gestora.{run}@teste.com").one()
        op = db.query(Usuario).filter_by(email=f"op.{run}@teste.com").one()
        senha_op = next(linha.split()[1] for linha in saida.splitlines() if linha.strip().startswith(f"op.{run}@"))
        ok = (codigo == 0 and central.secao.value == "padaria" and central.prazo_entrega_dias == 1
              and loja.codigo == "001" and loja.central_producao_id == central.id
              and f"{loja.horario_fechamento:%H:%M}" == "20:30" and f"{loja.horario_zeragem:%H:%M}" == "06:00"
              and gestora.tipo_usuario == TipoUsuario.GESTOR_CENTRAL and gestora.loja_id is None
              and gestora.central_producao_id == central.id and gestora.tem_acesso_web and not gestora.tem_acesso_app
              and op.tipo_usuario == TipoUsuario.OPERADOR_LOJA and op.loja_id == loja.id and op.tem_acesso_app
              and not op.tem_acesso_web and verificar_senha(senha_op, op.senha_hash))
        registrar("I2 aplicar cria tudo", ok, f"contagem {contar(db, run)}, senha confere {verificar_senha(senha_op, op.senha_hash)}")

        hash_antes = op.senha_hash
        codigo, saida = rodar(cfg, aplicar=True)
        db.expire_all()
        op = db.query(Usuario).filter_by(email=f"op.{run}@teste.com").one()
        registrar("I3 idempotente", codigo == 0 and contar(db, run) == (1, 1, 1, 2) and "[criad" not in saida
                  and "Senhas" not in saida and op.senha_hash == hash_antes, f"contagem {contar(db, run)}")

        run2 = uuid.uuid4().hex[:8]
        codigo, saida = rodar(config(run2, operador=f"op.{run}@teste.com"), aplicar=True)
        db.expire_all()
        registrar("I4 e-mail de outro negocio: erro e nada gravado",
                  codigo == 1 and "já existe" in saida and contar(db, run2) == (0, 0, 0, 0), saida.strip()[:120])

        cfg5 = config(run, central="Outra central", gestor=f"g2.{run}@teste.com", operador=f"op2.{run}@teste.com")
        codigo, saida = rodar(cfg5, aplicar=True)
        db.expire_all()
        registrar("I5 loja em outra central: erro", codigo == 1 and "outra central" in saida
                  and contar(db, run) == (1, 1, 1, 2), saida.strip()[:120])

        invalidos = []
        for nome, mexer in [
            ("secao", lambda c: c["centrais"][0].update(secao="confeitaria")),
            ("codigo repetido", lambda c: c["centrais"][0]["lojas"].append(dict(c["centrais"][0]["lojas"][0], operadores=[]))),
            ("email", lambda c: c["centrais"][0]["gestores"][0].update(email="sem-arroba")),
            ("hora", lambda c: c["centrais"][0]["lojas"][0].update(horario_fechamento="25:00")),
            ("sem gestor", lambda c: c["centrais"][0].update(gestores=[])),
            ("email repetido", lambda c: c["centrais"][0]["lojas"][0]["operadores"][0].update(
                email=c["centrais"][0]["gestores"][0]["email"])),
        ]:
            c = config(uuid.uuid4().hex[:8])
            mexer(c)
            try:
                ic.validar(c)
                invalidos.append(nome)
            except ic.ErroImplantacao:
                pass
        registrar("I6 arquivo invalido recusado", not invalidos, f"aceitos indevidamente: {invalidos}")

        exemplo = json.loads((Path(__file__).parent / "exemplo_implantacao.json").read_text(encoding="utf-8"))
        try:
            ic.validar(exemplo)
            registrar("I7 exemplo valido", True, exemplo["negocio"])
        except ic.ErroImplantacao as e:
            registrar("I7 exemplo valido", False, str(e))
    except Exception as e:  # noqa: BLE001
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        db.rollback()
        limpar(db)
        db.close()

    print()
    for r in resultados:
        print(r)
    falhas = [r for r in resultados if r.startswith("[FALHA]")]
    print()
    print(f"{len(falhas)} CASO(S) FALHARAM" if falhas else "TODOS OS CASOS PASSARAM")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
