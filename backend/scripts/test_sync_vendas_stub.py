"""
Testa o stub do sync_vendas_service (Fase 2 / P7).

Casos:
  S1 a chamada direta devolve "integração não configurada", com zero gravadas
  S2 a chamada não grava nada em vendas_diarias nem em perdas_diarias
  S3 o agendador registra só o job de zeragem (nenhum job de sync)
  S4 nenhum job do agendador aponta para o módulo de sync
  S5 nenhum módulo da aplicação importa o sync_vendas_service (fora dele mesmo)

S3/S4: o agendador é montado de verdade (iniciar_agendador), mas com o
start() trocado por um que não faz nada -- os jobs são registrados e
listados sem nenhuma execução real (a zeragem automática NÃO roda).

Uso: python scripts/test_sync_vendas_stub.py
"""

import re
import sys
from datetime import date
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core import scheduler as modulo_agendador  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.perda_diaria import PerdaDiaria  # noqa: E402
from app.models.venda_diaria import VendaDiaria  # noqa: E402
from app.services.sync_vendas_service import SituacaoSync, sincronizar_vendas  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 5
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def main():
    db = SessionLocal()
    try:
        negocio = db.query(Negocio).order_by(Negocio.id).first()
        negocio_id = negocio.id if negocio else 1
        antes = (db.query(VendaDiaria).count(), db.query(PerdaDiaria).count())

        res = sincronizar_vendas(db, negocio_id, date(2026, 10, 1))
        registrar("S1 chamada direta",
                  res.situacao == SituacaoSync.NAO_CONFIGURADA and res.vendas_gravadas == 0 and res.perdas_gravadas == 0
                  and "não configurada" in res.mensagem and res.negocio_id == negocio_id,
                  f"situacao={res.situacao.value}, gravadas={res.vendas_gravadas}/{res.perdas_gravadas}, mensagem={res.mensagem!r}")

        db.expire_all()
        depois = (db.query(VendaDiaria).count(), db.query(PerdaDiaria).count())
        registrar("S2 nada gravado", antes == depois, f"(vendas, perdas) antes={antes}, depois={depois}")

        # Agendador real, mas sem iniciar a thread (nenhum job executa).
        ag = modulo_agendador.scheduler
        start_original = ag.start
        ag.start = lambda *a, **k: None
        try:
            modulo_agendador.iniciar_agendador()
            jobs = ag.get_jobs()
            ids = [j.id for j in jobs]
            registrar("S3 agendador so tem o job de zeragem", ids == ["verificar_zeragem"], f"jobs={ids}")
            modulos = [getattr(j.func, "__module__", "?") for j in jobs]
            registrar("S4 nenhum job aponta para o sync", all("sync_vendas" not in m for m in modulos), f"modulos={modulos}")
        finally:
            ag.remove_all_jobs()
            ag.start = start_original

        # Ninguém da aplicação importa o stub (ele só será usado quando a
        # integração existir). Procura imports, não menções em comentários.
        app_dir = Path(__file__).resolve().parent.parent / "app"
        padrao_import = re.compile(r"^\s*(from\s+\S*sync_vendas_service\s+import|import\s+\S*sync_vendas_service)", re.M)
        importadores = [
            str(p.relative_to(app_dir.parent)) for p in app_dir.rglob("*.py")
            if p.name != "sync_vendas_service.py" and padrao_import.search(p.read_text(encoding="utf-8"))
        ]
        registrar("S5 nenhum modulo da aplicacao usa o stub", importadores == [], f"importadores={importadores}")
    except Exception as e:
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        db.close()
        print("\n=== Resultado do teste do stub de sincronização ===")
        for r in resultados:
            print(r)
        falhas = [r for r in resultados if r.startswith(FAIL)]
        if len(resultados) < TOTAL_CASOS:
            print(f"\nTESTE INCOMPLETO: só {len(resultados)} de {TOTAL_CASOS} casos rodaram")
        else:
            print(f"\n{'TODOS OS CASOS PASSARAM' if not falhas else f'{len(falhas)} CASO(S) FALHARAM'}")

    if len(resultados) < TOTAL_CASOS or any(r.startswith(FAIL) for r in resultados):
        sys.exit(1)


if __name__ == "__main__":
    main()
