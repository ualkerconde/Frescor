"""
Lógica de negócio para atualização e sincronização de estoque.

Mantida separada dos endpoints (app/api/produtos.py) para deixar a regra
de concorrência e o cálculo de estoque testáveis isoladamente, e para o
endpoint ficar focado só em validar a requisição e devolver a resposta.

Toda operação de estoque é sempre relativa a uma LOJA específica (não
apenas a um negócio) — o mesmo produto tem uma contagem independente em
cada loja onde está habilitado.

Cálculo do estoque real — 3 cenários (ver especificação atualizada):
- quantidade_inventariada: contagem de peças feita pelo usuário no app
  (sempre inteiro). É o RASCUNHO, zerado pela rotina diária de zeragem.
- estoque_atual_calculado: valor real de estoque, recalculado a cada
  lançamento. NUNCA é zerado pela rotina de zeragem.
    UN                  -> estoque_atual_calculado = quantidade_inventariada
    KG com peso médio   -> estoque_atual_calculado = peso_medio_kg * quantidade_inventariada
    KG sem peso médio   -> estoque_atual_calculado = peso_informado_kg
      (ex.: bolo vendido por fatia — o responsável pesa o item inteiro na
      hora da contagem e informa esse peso em vez de um peso médio fixo;
      quantidade_inventariada continua sendo registrada, mas não entra
      nessa conta.)
- peso_informado_kg: só é aceito (e só é obrigatório) no terceiro
  cenário. Enviá-lo para um produto UN ou KG-com-peso-médio é um erro de
  uso do cliente e é rejeitado.
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.estoque_atual import EstoqueAtual
from app.models.produto import Produto, UnidadeMedida
from app.models.produto_loja import ProdutoLoja
from app.schemas.estoque import ContagemOffline


def calcular_estoque_atual(
    produto: Produto,
    quantidade_inventariada: int,
    peso_informado_kg: Optional[Decimal] = None,
) -> tuple[Decimal, Optional[Decimal]]:
    """
    Calcula o valor real de estoque a partir da contagem de peças, da
    unidade de medida/peso médio do produto e (quando aplicável) do peso
    informado manualmente na contagem.

    Esta é A função central do cálculo — usada tanto no lançamento
    individual (aplicar_contagem) quanto na sincronização em lote
    (sincronizar_contagens), garantindo que a regra nunca seja duplicada
    ou implementada de forma inconsistente em mais de um lugar.

    Retorna uma tupla (estoque_atual_calculado, peso_informado_kg_normalizado)
    — o segundo valor é o que deve ser persistido em
    EstoqueAtual.peso_informado_kg (sempre None fora do 3º cenário).

    Levanta ValueError quando o payload é inconsistente com o cenário do
    produto:
    - peso_informado_kg enviado para produto UN ou KG-com-peso-médio.
    - produto KG sem peso médio, com quantidade_inventariada > 0 e sem
      peso_informado_kg válido (> 0).
    """
    if produto.unidade_medida == UnidadeMedida.UN:
        if peso_informado_kg is not None:
            raise ValueError("Produto em UN não aceita peso informado (peso_informado_kg).")
        return Decimal(quantidade_inventariada), None

    # UnidadeMedida.KG
    peso_medio = produto.peso_medio_kg
    if peso_medio is not None:
        # Cenário 2: peso médio cadastrado — peso informado não se aplica.
        if peso_informado_kg is not None:
            raise ValueError(
                "Produto com peso médio cadastrado não aceita peso informado manualmente "
                "(peso_informado_kg)."
            )
        return Decimal(peso_medio) * Decimal(quantidade_inventariada), None

    # Cenário 3: KG sem peso médio cadastrado — o peso do próprio item
    # informado na contagem (ex.: bolo vendido por fatia) é o valor real.
    if quantidade_inventariada > 0:
        if peso_informado_kg is None or peso_informado_kg <= 0:
            raise ValueError(
                "Produto KG sem peso médio cadastrado exige peso_informado_kg maior que zero."
            )
        return Decimal(peso_informado_kg), Decimal(peso_informado_kg)

    # Sem contagem (quantidade zero): nada foi pesado ainda.
    return Decimal("0"), None


def _produto_habilitado_para_loja(db: Session, produto_id: int, loja_id: int, negocio_id: int) -> Optional[Produto]:
    """
    Confirma que o produto existe, pertence ao negócio informado, e está
    habilitado (tem uma linha em produtos_lojas) para a loja informada.

    Esta checagem central é o que impede, na prática, que uma loja conte
    ou enxergue um produto que não está habilitado para ela — mesmo que o
    produto exista no catálogo geral da rede.

    Retorna o próprio objeto Produto (necessário para o cálculo de
    estoque, que depende de unidade_medida/peso_medio_kg), ou None se a
    checagem falhar.
    """
    produto = (
        db.query(Produto)
        .join(ProdutoLoja, ProdutoLoja.produto_id == Produto.id)
        .filter(
            ProdutoLoja.produto_id == produto_id,
            ProdutoLoja.loja_id == loja_id,
            Produto.negocio_id == negocio_id,
            Produto.ativo.is_(True),
        )
        .first()
    )
    return produto


def aplicar_contagem(
    db: Session,
    negocio_id: int,
    loja_id: int,
    produto_id: int,
    quantidade_inventariada: int,
    peso_informado_kg: Optional[Decimal] = None,
) -> EstoqueAtual:
    """
    Aplica uma contagem a um único produto, NUMA LOJA específica, com a
    checagem de isolamento: o produto precisa pertencer ao mesmo
    negocio_id de quem está fazendo a chamada E estar habilitado para a
    loja_id informada (ambos extraídos do token, nunca do corpo da
    requisição).

    Atualiza o rascunho (quantidade_inventariada), o valor real
    recalculado (estoque_atual_calculado) e, quando aplicável, o peso
    informado manualmente (peso_informado_kg).

    Levanta ValueError se o produto não existir, não pertencer ao negócio,
    não estiver habilitado para esta loja, ou se o payload for
    inconsistente com o cenário de cálculo do produto (ver
    calcular_estoque_atual) — o endpoint que chama esta função deve
    traduzir isso para um HTTP 404 ou 422, respectivamente.
    """
    produto = _produto_habilitado_para_loja(db, produto_id, loja_id, negocio_id)
    if produto is None:
        raise ValueError("Produto não encontrado ou não habilitado para esta loja.")

    estoque_calculado, peso_a_persistir = calcular_estoque_atual(
        produto, quantidade_inventariada, peso_informado_kg
    )

    estoque = (
        db.query(EstoqueAtual)
        .filter(EstoqueAtual.produto_id == produto_id, EstoqueAtual.loja_id == loja_id)
        .first()
    )

    if estoque is None:
        # Primeira contagem deste produto NESTA LOJA: cria a linha.
        estoque = EstoqueAtual(
            produto_id=produto_id,
            loja_id=loja_id,
            negocio_id=negocio_id,
            quantidade_inventariada=quantidade_inventariada,
            estoque_atual_calculado=estoque_calculado,
            peso_informado_kg=peso_a_persistir,
        )
        db.add(estoque)
    else:
        # Regra de concorrência (ver especificação, seção 6.3): não há
        # necessidade de comparar timestamps aqui para o caso comum (PATCH
        # direto, online) — esta função sempre aplica o valor recebido.
        estoque.quantidade_inventariada = quantidade_inventariada
        estoque.estoque_atual_calculado = estoque_calculado
        estoque.peso_informado_kg = peso_a_persistir

    db.commit()
    db.refresh(estoque)
    return estoque


def sincronizar_contagens(
    db: Session,
    negocio_id: int,
    loja_id: int,
    contagens: list[ContagemOffline],
) -> list[int]:
    """
    Aplica um lote de contagens feitas offline, todas referentes à mesma
    loja (a do usuário autenticado).

    Regra de concorrência ("último a sincronizar prevalece", ver
    especificação seção 6.3): como múltiplos lançamentos para o mesmo
    produto podem chegar fora de ordem, usamos o timestamp local
    (`registrado_em_local`) de cada contagem para decidir qual delas é a
    mais recente, e descartamos as demais para o mesmo produto dentro
    deste mesmo lote.

    Produtos que não estão habilitados para esta loja (ou não pertencem
    ao negócio do usuário autenticado), assim como itens cujo payload é
    inconsistente com o cenário de cálculo do produto (ex.: peso
    informado faltando num produto KG sem peso médio), são
    silenciosamente ignorados — sincronização em lote não deve falhar por
    completo por causa de um item problemático.
    """
    # Primeiro, para cada produto_id, mantém só a contagem mais recente
    # (maior registrado_em_local) dentro do lote recebido.
    mais_recente_por_produto: dict[int, ContagemOffline] = {}
    for contagem in contagens:
        atual = mais_recente_por_produto.get(contagem.produto_id)
        if atual is None or contagem.registrado_em_local > atual.registrado_em_local:
            mais_recente_por_produto[contagem.produto_id] = contagem

    produtos_habilitados = {
        produto.id: produto
        for produto in (
            db.query(Produto)
            .join(ProdutoLoja, ProdutoLoja.produto_id == Produto.id)
            .filter(
                ProdutoLoja.produto_id.in_(mais_recente_por_produto.keys()),
                ProdutoLoja.loja_id == loja_id,
                Produto.negocio_id == negocio_id,
                Produto.ativo.is_(True),
            )
        )
    }

    produtos_sincronizados: list[int] = []

    for produto_id, contagem in mais_recente_por_produto.items():
        produto = produtos_habilitados.get(produto_id)
        if produto is None:
            continue  # produto não habilitado para esta loja: ignora silenciosamente

        try:
            estoque_calculado, peso_a_persistir = calcular_estoque_atual(
                produto, contagem.quantidade, contagem.peso_informado_kg
            )
        except ValueError:
            continue  # payload inconsistente com o cenário do produto: ignora silenciosamente

        estoque = (
            db.query(EstoqueAtual)
            .filter(EstoqueAtual.produto_id == produto_id, EstoqueAtual.loja_id == loja_id)
            .first()
        )
        if estoque is None:
            estoque = EstoqueAtual(
                produto_id=produto_id,
                loja_id=loja_id,
                negocio_id=negocio_id,
                quantidade_inventariada=contagem.quantidade,
                estoque_atual_calculado=estoque_calculado,
                peso_informado_kg=peso_a_persistir,
            )
            db.add(estoque)
        else:
            estoque.quantidade_inventariada = contagem.quantidade
            estoque.estoque_atual_calculado = estoque_calculado
            estoque.peso_informado_kg = peso_a_persistir

        produtos_sincronizados.append(produto_id)


    db.commit()
    return produtos_sincronizados
