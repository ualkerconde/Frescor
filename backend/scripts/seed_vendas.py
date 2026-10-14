"""
Cria ~8 semanas de vendas e perdas diárias de teste para as lojas do seed
(Fase 2 / P8), para alimentar o motor de previsão da Fase 3.

Padrões de padaria simulados:
- Dia da semana: mais venda no fim de semana (sábado e domingo), menos no
  início da semana (FATOR_DIA_SEMANA).
- Loja: a Loja Bairro (002) vende menos que a Loja Centro (001) (FATOR_LOJA).
- Volume base por produto (BASE_DIARIA, na unidade do produto: UN em
  peças, KG em quilos -- D6).
- Perda pela validade do produto (alta rotatividade perde mais): produto de
  1 dia perde ~9% do que vende; de 5 dias, ~1,5% (TAXA_PERDA_POR_VALIDADE).
- Variação aleatória de cada dia, com semente fixa por loja + produto + dia:
  o valor de um dia é sempre o mesmo, em qualquer execução.
- Produtos UN são arredondados de forma probabilística (ver _arredondar),
  senão perdas pequenas (ex.: 0,18 bolo/dia) virariam sempre zero.

Período: as SEMANAS semanas que terminam ONTEM. A janela acompanha a data em
que o seed roda (a Fase 3 precisa de dado recente); os valores de cada dia
não mudam entre execuções.

Idempotente: grava com origem `manual` e substitui o que já existir para a
mesma loja + produto + dia (mesma regra da importação, D5). Rodar de novo
no mesmo dia não cria nenhuma linha nova.

Só usa produtos habilitados e ativos em cada loja (produtos_lojas).

Pré-requisitos: python scripts/seed_dev.py e python scripts/seed_produtos.py.

Como rodar (na pasta backend/, com o venv ativo):
    python scripts/seed_vendas.py
"""

import random
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, tuple_  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.perda_diaria import OrigemPerda, PerdaDiaria  # noqa: E402
from app.models.produto import Produto, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402

NOME_NEGOCIO = "Rede Padaria Teste"
SEMANAS = 8
SEMENTE = "bakery-seed-vendas-v1"

# segunda=0 ... domingo=6
FATOR_DIA_SEMANA = {0: 0.85, 1: 0.85, 2: 0.90, 3: 0.95, 4: 1.10, 5: 1.35, 6: 1.25}
FATOR_LOJA = {"001": 1.00, "002": 0.65}

# Venda média diária na Loja Centro, na unidade do produto.
BASE_DIARIA = {
    "INT-001": 40,    # Croissant (UN)
    "INT-002": 6,     # Bolo de Chocolate (UN)
    "INT-003": 15,    # Rosca de Canela (UN)
    "INT-004": 30,    # Sonho (UN)
    "INT-005": 10,    # Torta de Frango (UN)
    "INT-006": 50,    # Coxinha (UN)
    "INT-007": 30.0,  # Pão Francês (kg)
    "INT-008": 6.0,   # Pão de Forma (kg)
    "INT-009": 8.0,   # Baguete (kg)
    "INT-010": 4.0,   # Pão Integral (kg)
    "INT-011": 3.0,   # Bolo de Chocolate em fatia (kg)
}

# Fração da venda que vira perda, pela validade (dias). None: sem validade cadastrada.
TAXA_PERDA_POR_VALIDADE = {1: 0.09, 2: 0.05, 3: 0.03, None: 0.04}
TAXA_PERDA_LONGA = 0.015  # validade de 4 dias ou mais


def _taxa_perda(dias_validade):
    if dias_validade is None or dias_validade in TAXA_PERDA_POR_VALIDADE:
        return TAXA_PERDA_POR_VALIDADE.get(dias_validade)
    return TAXA_PERDA_LONGA


def _arredondar(valor: float, unidade: UnidadeMedida, rng: random.Random) -> Decimal:
    """
    KG: 3 casas. UN: inteiro com arredondamento probabilístico (0,18 vira 1
    em ~18% dos dias e 0 nos demais), para não zerar sempre volumes
    pequenos -- ex.: a perda de um bolo que vende 6 por dia.
    """
    valor = max(valor, 0.0)
    if unidade == UnidadeMedida.UN:
        inteiro = int(valor)
        return Decimal(inteiro + (1 if rng.random() < valor - inteiro else 0))
    return Decimal(str(valor)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def gerar(codigo_loja: str, produto: Produto, dia: date) -> tuple[Decimal, Decimal]:
    """(venda, perda) de um produto numa loja num dia. Determinístico."""
    rng = random.Random(f"{SEMENTE}|{codigo_loja}|{produto.codigo}|{dia.isoformat()}")
    base = BASE_DIARIA[produto.codigo] * FATOR_LOJA[codigo_loja] * FATOR_DIA_SEMANA[dia.weekday()]
    venda = base * min(max(rng.gauss(1.0, 0.10), 0.70), 1.30)
    perda = venda * _taxa_perda(produto.dias_validade) * min(max(rng.gauss(1.0, 0.35), 0.0), 2.5)
    return _arredondar(venda, produto.unidade_medida, rng), _arredondar(perda, produto.unidade_medida, rng)


def _gravar(db, modelo, origem, constraint, linhas) -> tuple[int, int]:
    """Upsert em blocos; devolve (inseridas, substituídas)."""
    chaves = [(lin["loja_id"], lin["produto_id"], lin["data"]) for lin in linhas]
    existentes = 0
    for i in range(0, len(chaves), 1000):
        existentes += (
            db.query(func.count(modelo.id))
            .filter(modelo.origem == origem, tuple_(modelo.loja_id, modelo.produto_id, modelo.data).in_(chaves[i:i + 1000]))
            .scalar()
        )
    for i in range(0, len(linhas), 1000):
        stmt = pg_insert(modelo).values([dict(lin, origem=origem) for lin in linhas[i:i + 1000]])
        stmt = stmt.on_conflict_do_update(
            constraint=constraint, set_={"quantidade": stmt.excluded.quantidade, "atualizado_em": func.now()}
        )
        db.execute(stmt)
    return len(linhas) - existentes, existentes


def main():
    db = SessionLocal()
    try:
        negocio = db.query(Negocio).filter(Negocio.nome == NOME_NEGOCIO).order_by(Negocio.id).first()
        if negocio is None:
            print(f"Negócio '{NOME_NEGOCIO}' não encontrado. Rode 'python scripts/seed_dev.py' primeiro.")
            return
        lojas = (
            db.query(Loja)
            .filter(Loja.negocio_id == negocio.id, Loja.codigo.in_(list(FATOR_LOJA)), Loja.ativo.is_(True))
            .order_by(Loja.codigo)
            .all()
        )
        if len(lojas) != len(FATOR_LOJA):
            print(f"Esperadas as lojas {sorted(FATOR_LOJA)} ativas; encontradas {[lj.codigo for lj in lojas]}. "
                  "Rode 'python scripts/seed_dev.py' primeiro.")
            return

        fim = date.today() - timedelta(days=1)
        inicio = fim - timedelta(days=7 * SEMANAS - 1)
        dias = [inicio + timedelta(days=n) for n in range(7 * SEMANAS)]

        vendas, perdas = [], []
        for loja in lojas:
            produtos = (
                db.query(Produto)
                .join(ProdutoLoja, ProdutoLoja.produto_id == Produto.id)
                .filter(ProdutoLoja.loja_id == loja.id, ProdutoLoja.ativo.is_(True), Produto.ativo.is_(True),
                        Produto.negocio_id == negocio.id, Produto.codigo.in_(list(BASE_DIARIA)))
                .order_by(Produto.codigo)
                .all()
            )
            if not produtos:
                print(f"Loja {loja.codigo} sem produtos habilitados. Rode 'python scripts/seed_produtos.py' primeiro.")
                return
            for produto in produtos:
                for dia in dias:
                    v, p = gerar(loja.codigo, produto, dia)
                    comum = dict(negocio_id=negocio.id, loja_id=loja.id, produto_id=produto.id, data=dia)
                    vendas.append(dict(comum, quantidade=v))
                    perdas.append(dict(comum, quantidade=p))

        v_ins, v_sub = _gravar(db, VendaDiaria, OrigemVenda.MANUAL, "uq_venda_loja_produto_data_origem", vendas)
        p_ins, p_sub = _gravar(db, PerdaDiaria, OrigemPerda.MANUAL, "uq_perda_loja_produto_data_origem", perdas)
        db.commit()

        print(f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} ({len(dias)} dias, {SEMANAS} semanas)")
        print(f"Lojas: {', '.join(f'{lj.codigo} ({lj.nome})' for lj in lojas)}")
        print(f"Vendas: {len(vendas)} linhas -> {v_ins} inseridas, {v_sub} substituídas")
        print(f"Perdas: {len(perdas)} linhas -> {p_ins} inseridas, {p_sub} substituídas")
        soma_v = sum(lin["quantidade"] for lin in vendas)
        soma_p = sum(lin["quantidade"] for lin in perdas)
        print(f"Conferência (soma de todas as quantidades): vendas={soma_v} perdas={soma_p}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
