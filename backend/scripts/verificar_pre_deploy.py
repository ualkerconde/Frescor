"""
Conferência antes do deploy de produção (só LEITURA: não grava nada).

Junta num lugar as verificações que o STATUS foi acumulando como "antes do
deploy, conferir no banco de produção". Rodar com o .env de produção, na
pasta backend/, ANTES de `alembic upgrade head`:

    python scripts/verificar_pre_deploy.py

Cada item sai como [OK], [ATENÇÃO] (pode seguir, mas leia) ou [BLOQUEIA]
(resolver antes do upgrade). Nunca mostra a SECRET_KEY nem a URL do banco.

Itens:
  1. Versão do banco (alembic) e quantas migrations faltam
  2. Extensão unaccent disponível (migration 0017; a busca sem acento depende dela)
  3. Códigos de produto repetidos no mesmo negócio (a 0016 para se houver)
  4. Vínculos produto × loja desativados (D100: somem da contagem no app)
  5. SECRET_KEY curta (menos de 32 caracteres)
  6. CORS_ORIGINS vazio em produção (o SaaS e o app em outro domínio não conseguem chamar a API)
  7. Lojas sem código (a integração de vendas e o CSV casam a loja pelo código)
  8. Centrais ativas sem gestor com acesso ao SaaS
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
itens: list[tuple[str, str, str]] = []


def item(nivel: str, nome: str, detalhe: str) -> None:
    itens.append((nivel, nome, detalhe))


def tabela_existe(nome: str) -> bool:
    return inspect(engine).has_table(nome)


def coluna_existe(tabela: str, coluna: str) -> bool:
    return tabela_existe(tabela) and coluna in {c["name"] for c in inspect(engine).get_columns(tabela)}


def main() -> int:
    script = ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini")))
    head = script.get_current_head()
    db = SessionLocal()
    try:
        atual = None
        if tabela_existe("alembic_version"):
            atual = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        faltam = [r.revision for r in script.iterate_revisions(head, atual)] if atual != head else []
        item("OK" if atual == head else "ATENÇÃO", "1 versão do banco",
             f"banco em {atual or 'nenhuma'}, código em {head}; faltam {len(faltam)} migration(s)"
             + (f": {', '.join(reversed(faltam))}" if faltam else ""))

        disponivel = db.execute(text("SELECT count(*) FROM pg_available_extensions WHERE name = 'unaccent'")).scalar()
        instalada = db.execute(text("SELECT count(*) FROM pg_extension WHERE extname = 'unaccent'")).scalar()
        item("OK" if disponivel else "BLOQUEIA", "2 extensão unaccent",
             "instalada" if instalada else ("disponível (a 0017 instala)" if disponivel
                                            else "NÃO disponível no servidor PostgreSQL: instalar o pacote contrib"))

        if coluna_existe("produtos", "codigo"):
            rep = db.execute(text(
                "SELECT negocio_id, codigo, count(*) FROM produtos WHERE codigo IS NOT NULL "
                "GROUP BY 1, 2 HAVING count(*) > 1 ORDER BY 1, 2 LIMIT 20")).all()
            item("BLOQUEIA" if rep else "OK", "3 códigos de produto repetidos",
                 "; ".join(f"negócio {n} código {c!r} ({q}x)" for n, c, q in rep) or "nenhum")

        if coluna_existe("produtos_lojas", "ativo"):
            n = db.execute(text("SELECT count(*) FROM produtos_lojas WHERE ativo = false")).scalar()
            item("ATENÇÃO" if n else "OK", "4 vínculos produto × loja desativados",
                 f"{n} vínculo(s) somem da contagem do app depois do deploy (D100)" if n else "nenhum")
        else:
            item("OK", "4 vínculos produto × loja desativados", "coluna ainda não existe (vem numa migration)")

        tamanho = len(settings.SECRET_KEY or "")
        item("OK" if tamanho >= 32 else "ATENÇÃO", "5 SECRET_KEY",
             f"{tamanho} caracteres" + ("" if tamanho >= 32 else "; use pelo menos 32 (trocar derruba as sessões abertas)"))

        cors = [o for o in settings.CORS_ORIGINS.split(",") if o.strip()]
        producao = settings.ENVIRONMENT.lower() in {"production", "producao", "produção"}
        item("ATENÇÃO" if producao and not cors else "OK", "6 CORS_ORIGINS",
             f"{len(cors)} origem(ns) configurada(s)" if cors else
             ("vazio: só as origens de desenvolvimento são aceitas" if producao else "vazio (ok fora de produção)"))

        if coluna_existe("lojas", "codigo"):
            n = db.execute(text("SELECT count(*) FROM lojas WHERE ativo AND codigo IS NULL")).scalar()
            item("ATENÇÃO" if n else "OK", "7 lojas ativas sem código", f"{n} loja(s)" if n else "nenhuma")

        if coluna_existe("usuarios", "tem_acesso_web") and tabela_existe("centrais_producao"):
            sem = db.execute(text(
                "SELECT c.negocio_id, c.id, c.nome FROM centrais_producao c WHERE c.ativa AND NOT EXISTS ("
                " SELECT 1 FROM usuarios u WHERE u.central_producao_id = c.id AND u.tem_acesso_web"
                " AND u.tipo_usuario = 'gestor_central') ORDER BY 1, 2 LIMIT 20")).all()
            item("ATENÇÃO" if sem else "OK", "8 centrais sem gestor no SaaS",
                 "; ".join(f"negócio {n} central {i} {nome!r}" for n, i, nome in sem) or "nenhuma")
    finally:
        db.close()

    print()
    for nivel, nome, detalhe in itens:
        print(f"[{nivel}] {nome}: {detalhe}")
    bloqueios = sum(1 for nivel, _, _ in itens if nivel == "BLOQUEIA")
    print()
    print(f"{bloqueios} ITEM(NS) BLOQUEIAM O DEPLOY" if bloqueios else "NADA BLOQUEIA O DEPLOY (leia as atenções)")
    return 1 if bloqueios else 0


if __name__ == "__main__":
    sys.exit(main())
