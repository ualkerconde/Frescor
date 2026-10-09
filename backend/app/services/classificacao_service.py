"""
Serviço de leitura da classificação de produtos.

Mantido separado dos endpoints (app/api/produtos.py), seguindo o mesmo
padrão de app/services/estoque_service.py: a regra de negócio (montar a
lista ordenada de níveis + valores de cada produto) fica isolada e
testável, e o endpoint só chama a função e devolve a resposta.

Este backend é somente leitura para classificação de produtos — assim
como o catálogo de produtos em si (ver docstring de app/models/produto.py),
os níveis e os valores atribuídos a cada produto são cadastrados e
gerenciados exclusivamente pelo software web.
"""

from sqlalchemy.orm import Session

from app.models.nivel_classificacao import NivelClassificacao
from app.models.produto_classificacao import ProdutoClassificacao
from app.schemas.estoque import ClassificacaoItem


def obter_classificacoes_por_produto(
    db: Session,
    produto_ids: list[int],
    negocio_id: int,
) -> dict[int, list[ClassificacaoItem]]:
    """
    Monta, para cada produto_id informado, a lista ordenada (por
    nivel.ordem) de classificações atribuídas a ele.

    Filtra sempre por negocio_id (nunca confiar apenas na FK produto->
    nivel): impede que a classificação de um produto exiba, por engano,
    um nível que pertença a outro negócio. Níveis desativados
    (NivelClassificacao.ativo == False) são omitidos do resultado, mas o
    registro em produto_classificacoes não é apagado (histórico
    preservado).

    Retorna um dicionário {produto_id: [ClassificacaoItem, ...]}. Produtos
    sem nenhuma classificação atribuída simplesmente não aparecem como
    chave — o chamador deve tratar isso com .get(produto_id, []).
    """
    if not produto_ids:
        return {}

    resultados = (
        db.query(ProdutoClassificacao, NivelClassificacao)
        .join(NivelClassificacao, NivelClassificacao.id == ProdutoClassificacao.nivel_id)
        .filter(
            ProdutoClassificacao.produto_id.in_(produto_ids),
            NivelClassificacao.negocio_id == negocio_id,
            NivelClassificacao.ativo.is_(True),
        )
        .order_by(NivelClassificacao.ordem)
        .all()
    )

    classificacoes_por_produto: dict[int, list[ClassificacaoItem]] = {}
    for classificacao, nivel in resultados:
        classificacoes_por_produto.setdefault(classificacao.produto_id, []).append(
            ClassificacaoItem(nivel=nivel.nome, ordem=nivel.ordem, valor=classificacao.valor)
        )

    return classificacoes_por_produto
