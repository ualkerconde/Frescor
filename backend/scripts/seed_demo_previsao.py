"""
Dados de demonstração para ver, na tela de previsão (F9), os dois estados
que o seed principal não tem: "Sem previsão" e "Pouco histórico".

Por que um negócio separado ("Rede Demo Previsão"), e não produtos novos na
"Rede Padaria Teste":
- os testes de regressão contam o seed principal (11 produtos, lojas 001 e
  002, 22 previsões sem cold start); produtos a mais quebrariam esses testes;
- "Sem previsão" só acontece quando não há nenhuma referência: nem histórico
  próprio, nem o mesmo produto em outra loja, nem produto da mesma unidade
  na loja (D20/D29). Nas lojas do seed principal sempre há produto da mesma
  unidade, então um produto novo ali ganharia previsão pelo proxy.

O que é criado (com o gestor `gestor.demo@teste.com`, senha `senha123`):
- loja D01 com 8 semanas de vendas de dois produtos em UN (DEMO-01, DEMO-02),
  que são a referência (histórico completo);
- DEMO-03 (UN), "Pouco histórico": vendas só nas últimas 2 semanas. Peso do
  histórico próprio 2/6; o resto vem da média dos produtos da mesma unidade;
- DEMO-04 (KG), "Sem previsão": habilitado na loja, sem nenhuma venda e sem
  nenhum produto em KG na loja para servir de referência.

Idempotente: tudo é procurado antes de ser criado; as vendas são gravadas
com a mesma regra da importação (substitui, D5). Para manter a demonstração
igual em qualquer dia em que rodar, a janela acompanha a data de hoje:
- as vendas do DEMO-03 de antes das últimas 2 semanas são apagadas (senão,
  semanas depois, ele teria histórico completo);
- a habilitação do DEMO-04 é atualizada para agora (senão, 6 semanas depois,
  ele teria "histórico zero" e previsão 0 em vez de "Sem previsão").

Não gera a previsão: entre com o gestor demo na tela e clique em "Gerar
previsão" (ou POST /previsoes/gerar).

Como rodar (na pasta backend/, com o venv ativo):
    python scripts/seed_demo_previsao.py
"""

import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.core.security import hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402

NOME_NEGOCIO = "Rede Demo Previsão"
NOME_CENTRAL = "Central Demo"
LOJA = {"nome": "Loja Demo", "codigo": "D01"}
GESTOR = {"email": "gestor.demo@teste.com", "nome": "Gestor Demo"}
SENHA = "senha123"
SEMENTE = "frescor-demo-previsao-v1"

SEMANAS_REFERENCIA = 8
SEMANAS_POUCO_HISTORICO = 2

# codigo: (nome, unidade, venda média por dia ou None = nunca vende, semanas de venda)
PRODUTOS = {
    "DEMO-01": ("Pão de Queijo", UnidadeMedida.UN, 60, SEMANAS_REFERENCIA),
    "DEMO-02": ("Biscoito de Polvilho", UnidadeMedida.UN, 25, SEMANAS_REFERENCIA),
    "DEMO-03": ("Empada de Palmito", UnidadeMedida.UN, 18, SEMANAS_POUCO_HISTORICO),
    "DEMO-04": ("Queijo Minas Frescal", UnidadeMedida.KG, None, 0),
}
CODIGO_SEM_VENDA = "DEMO-04"
CODIGO_POUCO_HISTORICO = "DEMO-03"

# segunda=0 ... domingo=6 (mesmo padrão do seed_vendas.py)
FATOR_DIA_SEMANA = {0: 0.85, 1: 0.85, 2: 0.90, 3: 0.95, 4: 1.10, 5: 1.35, 6: 1.25}


def _obter_ou_criar(db, modelo, filtros: dict, valores: dict):
    """Devolve (registro, criado)."""
    registro = db.query(modelo).filter_by(**filtros).order_by(modelo.id).first()
    if registro is not None:
        return registro, False
    registro = modelo(**filtros, **valores)
    db.add(registro)
    db.flush()
    return registro, True


def _venda(codigo: str, media: int, dia: date) -> Decimal:
    """Venda inteira (UN) de um dia, determinística (mesma semente, mesmo valor)."""
    rng = random.Random(f"{SEMENTE}|{codigo}|{dia.isoformat()}")
    valor = media * FATOR_DIA_SEMANA[dia.weekday()] * min(max(rng.gauss(1.0, 0.10), 0.7), 1.3)
    return Decimal(round(valor))


def main():
    db = SessionLocal()
    try:
        negocio, criado = _obter_ou_criar(db, Negocio, {"nome": NOME_NEGOCIO}, {"ativo": True})
        print(f"Negócio: {negocio.nome} (id={negocio.id}) [{'criado' if criado else 'existente'}]")
        central, criado = _obter_ou_criar(
            db, CentralProducao, {"negocio_id": negocio.id, "nome": NOME_CENTRAL}, {"ativa": True}
        )
        print(f"Central: {central.nome} (id={central.id}) [{'criado' if criado else 'existente'}]")
        loja, criado = _obter_ou_criar(
            db,
            Loja,
            {"negocio_id": negocio.id, "codigo": LOJA["codigo"]},
            {"nome": LOJA["nome"], "central_producao_id": central.id, "horario_zeragem": time(6, 0), "ativo": True},
        )
        print(f"Loja:    {loja.codigo} · {loja.nome} (id={loja.id}) [{'criado' if criado else 'existente'}]")

        gestor = db.query(Usuario).filter(Usuario.email == GESTOR["email"]).first()
        if gestor is None:
            gestor = Usuario(
                negocio_id=negocio.id,
                tipo_usuario=TipoUsuario.GESTOR_CENTRAL,
                central_producao_id=central.id,
                nome=GESTOR["nome"],
                email=GESTOR["email"],
                senha_hash=hash_senha(SENHA),
                status=StatusUsuario.ATIVO,
                tem_acesso_app=False,
                tem_acesso_web=True,
            )
            db.add(gestor)
            db.flush()
            print(f"Gestor:  {gestor.email} (id={gestor.id}) [criado]")
        else:
            print(f"Gestor:  {gestor.email} (id={gestor.id}) [existente]")

        ontem = date.today() - timedelta(days=1)
        linhas = []
        for codigo, (nome, unidade, media, semanas) in PRODUTOS.items():
            produto, criado = _obter_ou_criar(
                db,
                Produto,
                {"negocio_id": negocio.id, "codigo": codigo},
                {"nome": nome, "unidade_medida": unidade, "ativo": True,
                 "peso_medio_kg": Decimal("1") if unidade == UnidadeMedida.KG else None},
            )
            habilitacao, _ = _obter_ou_criar(
                db, ProdutoLoja, {"produto_id": produto.id, "loja_id": loja.id}, {"ativo": True}
            )
            if codigo == CODIGO_SEM_VENDA:
                # Habilitado "agora": histórico próprio ainda não começou (D28).
                # UTC sem fuso, como o default da coluna (datetime.utcnow).
                habilitacao.criado_em = datetime.now(timezone.utc).replace(tzinfo=None)
            inicio = ontem - timedelta(days=7 * semanas - 1)
            if codigo == CODIGO_POUCO_HISTORICO:
                apagadas = (
                    db.query(VendaDiaria)
                    .filter(VendaDiaria.loja_id == loja.id, VendaDiaria.produto_id == produto.id,
                            VendaDiaria.data < inicio)
                    .delete(synchronize_session=False)
                )
                if apagadas:
                    print(f"  {codigo}: {apagadas} vendas antigas apagadas (mantém só {semanas} semanas)")
            if media is not None:
                for n in range(7 * semanas):
                    dia = inicio + timedelta(days=n)
                    linhas.append(dict(negocio_id=negocio.id, loja_id=loja.id, produto_id=produto.id, data=dia,
                                       quantidade=_venda(codigo, media, dia), origem=OrigemVenda.MANUAL))
            print(f"Produto: {codigo} · {nome} ({unidade.value}) [{'criado' if criado else 'existente'}]"
                  f" -> {'sem vendas' if media is None else f'{7 * semanas} dias de venda até {ontem:%d/%m/%Y}'}")

        stmt = pg_insert(VendaDiaria).values(linhas)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_venda_loja_produto_data_origem",
            set_={"quantidade": stmt.excluded.quantidade, "atualizado_em": func.now()},
        )
        db.execute(stmt)
        db.commit()
        total = db.query(func.count(VendaDiaria.id)).filter(VendaDiaria.loja_id == loja.id).scalar()
        print(f"Vendas gravadas (substituindo as do mesmo dia): {len(linhas)}; total na loja D01: {total}")
        print(f"Entre no SaaS com {GESTOR['email']} / {SENHA} e gere a previsão.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
