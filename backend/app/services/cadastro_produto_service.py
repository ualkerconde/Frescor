"""
Cadastro de produto pelo gestor no SaaS web (Fase 6 / C2 e C3).

O catálogo é do NEGÓCIO (doc §3.1, D96): qualquer gestor de central do
negócio cria e edita os produtos dele. A habilitação por loja, ao
contrário, só vale para as lojas da central do gestor (D8, D100).

Regras (docs/STATUS.md, "Fase 6 — plano"):
- D97: código obrigatório no produto novo (a importação de CSV acha o
  produto pelo código, D7); um código existente não pode ser apagado.
  Código e código de barras são únicos no negócio (o código também no
  banco: `uq_produto_negocio_codigo`).
- D98: a unidade (UN/KG) não muda depois que o produto tem histórico
  (venda, perda, contagem, previsão ou item de ordem): o histórico
  ficaria numa unidade e o produto em outra. Peso médio só em KG.
- D99: não há apagar; desativar é `ativo = false`.
- D101: o produto novo já nasce habilitado nas lojas ativas da central
  (o gestor pode pedir que não).
- D102: setor só da central do gestor e ativo; vazio = sem setor.
- D105: vigência permanente (sem datas), temporária (início e/ou fim) ou
  sazonal (`ciclo sazonal` + `vigencia_recorrente` + as duas datas).
- Calendário (`calendario_producao`): os dias da semana em que a central
  produz (ou envia, no distribuído, D39); vazio = todos os dias, como a
  necessidade já trata. Gravar substitui o calendário inteiro.
- D100: desativar na loja = `produtos_lojas.ativo = false`, mantendo a
  linha (a data de habilitação é o início do histórico no cold start);
  habilitar uma loja sem linha cria a linha.

Mudanças no cadastro valem para a próxima previsão e a próxima ordem; as
ordens aprovadas guardam o que foi calculado (D73).

Produto de outro negócio ou inexistente -> `ProdutoNaoEncontrado`; loja
fora da central do gestor -> `LojaNaoEncontrada` (404 iguais na rota).
Validação -> `CadastroInvalido` (422). Este serviço não conhece HTTP.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import exists, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado
from app.models.calendario_producao import CalendarioProducao, DiaSemana
from app.models.estoque_atual import EstoqueAtual
from app.models.historico_contagem import HistoricoContagem
from app.models.loja import Loja
from app.models.ordem_producao_item import OrdemProducaoItem
from app.models.perda_diaria import PerdaDiaria
from app.models.previsao_diaria import PrevisaoDiaria
from app.models.produto import CicloPrevisao, Produto, TipoAbastecimento, UnidadeMedida
from app.models.produto_loja import ProdutoLoja
from app.models.setor_producao import SetorProducao
from app.models.venda_diaria import VendaDiaria
from app.services.cadastro_central_service import CadastroInvalido
from app.services.escopo_service import consulta_lojas_do_gestor

TAMANHO_MAXIMO_NOME = 255
TAMANHO_MAXIMO_CODIGO = 64
VALIDADE_MAXIMA_DIAS = 365
MARGEM_MAXIMA = Decimal("500")
PESO_MAXIMO = Decimal("999999.9999")  # Numeric(10, 4)

# Ordem de exibição dos dias (segunda primeiro, como o calendário brasileiro).
ORDEM_DIAS = list(DiaSemana)

# Campos que a criação e a edição aceitam (os nomes do model).
CAMPOS = (
    "nome", "codigo", "codigo_barras", "unidade_medida", "peso_medio_kg", "ativo", "tipo_abastecimento",
    "dias_validade", "margem_maxima_percentual", "data_inicio_vigencia", "data_fim_vigencia",
    "vigencia_recorrente", "ciclo_previsao", "setor_producao_id", "dias_producao",
)
_VIGENCIA = {"data_inicio_vigencia", "data_fim_vigencia", "vigencia_recorrente", "ciclo_previsao"}


class ProdutoNaoEncontrado(LookupError):
    pass


class LojaNaoEncontrada(LookupError):
    pass


@dataclass(frozen=True)
class ProdutoDetalhe:
    produto: Produto
    dias_producao: list[DiaSemana]
    setor_nome: str | None
    tem_historico: bool


@dataclass(frozen=True)
class LojaDoProduto:
    loja_id: int
    codigo: str | None
    nome: str
    loja_ativa: bool
    # Sem linha em produtos_lojas: não habilitado (habilitado = False, ativo = False).
    habilitado: bool
    ativo: bool


# ---------------------------------------------------------------- leitura


def _produto(db: Session, gestor: GestorCentralAutenticado, produto_id: int) -> Produto:
    p = db.query(Produto).filter(Produto.id == produto_id, Produto.negocio_id == gestor.negocio_id).one_or_none()
    if p is None:
        raise ProdutoNaoEncontrado("Produto não encontrado.")
    return p


def tem_historico(db: Session, negocio_id: int, produto_id: int) -> bool:
    """Venda, perda, contagem, previsão ou item de ordem do produto (D98)."""
    for modelo in (VendaDiaria, PerdaDiaria, EstoqueAtual, HistoricoContagem, PrevisaoDiaria, OrdemProducaoItem):
        if db.query(exists().where(modelo.negocio_id == negocio_id, modelo.produto_id == produto_id)).scalar():
            return True
    return False


def _dias(db: Session, negocio_id: int, produto_id: int) -> list[DiaSemana]:
    gravados = {
        d for (d,) in db.query(CalendarioProducao.dia_semana).filter(
            CalendarioProducao.negocio_id == negocio_id, CalendarioProducao.produto_id == produto_id
        )
    }
    return [d for d in ORDEM_DIAS if d in gravados]


def detalhar_produto(db: Session, gestor: GestorCentralAutenticado, produto_id: int) -> ProdutoDetalhe:
    p = _produto(db, gestor, produto_id)
    setor_nome = None
    if p.setor_producao_id is not None:
        setor_nome = db.query(SetorProducao.nome).filter(
            SetorProducao.id == p.setor_producao_id, SetorProducao.negocio_id == gestor.negocio_id
        ).scalar()
    return ProdutoDetalhe(
        produto=p,
        dias_producao=_dias(db, gestor.negocio_id, p.id),
        setor_nome=setor_nome,
        tem_historico=tem_historico(db, gestor.negocio_id, p.id),
    )


# ---------------------------------------------------------------- validação


def _texto(valor, rotulo: str, tamanho: int, obrigatorio: bool) -> str | None:
    texto = (valor or "").strip()
    if not texto:
        if obrigatorio:
            raise CadastroInvalido(f"Informe {rotulo}.")
        return None
    if len(texto) > tamanho:
        raise CadastroInvalido(f"{rotulo[0].upper()}{rotulo[1:]} pode ter no máximo {tamanho} caracteres.")
    return texto


def _casas(valor: Decimal) -> int:
    expoente = valor.as_tuple().exponent
    return -expoente if isinstance(expoente, int) and expoente < 0 else 0


def _validar(db: Session, gestor: GestorCentralAutenticado, p: Produto, dados: dict, novo: bool,
             historico: bool) -> dict:
    """Confere os campos informados contra o estado final do produto; devolve os valores limpos."""
    limpo: dict = {}
    if "nome" in dados or novo:
        limpo["nome"] = _texto(dados.get("nome"), "o nome do produto", TAMANHO_MAXIMO_NOME, True)

    if "codigo" in dados or novo:
        codigo = _texto(dados.get("codigo"), "o código do produto", TAMANHO_MAXIMO_CODIGO, False)
        if codigo is None and (novo or p.codigo is not None):
            raise CadastroInvalido(
                "Informe o código do produto. É por ele que a importação de vendas e perdas acha o produto."
            )
        if codigo is not None and codigo != p.codigo:
            outro = db.query(Produto.nome).filter(
                Produto.negocio_id == gestor.negocio_id, Produto.codigo == codigo, Produto.id != (p.id or 0)
            ).scalar()
            if outro is not None:
                raise CadastroInvalido(f"O código \"{codigo}\" já é do produto \"{outro}\".")
        limpo["codigo"] = codigo

    if "codigo_barras" in dados:
        barras = _texto(dados.get("codigo_barras"), "o código de barras", TAMANHO_MAXIMO_CODIGO, False)
        if barras is not None and barras != p.codigo_barras:
            outro = db.query(Produto.nome).filter(
                Produto.negocio_id == gestor.negocio_id, Produto.codigo_barras == barras, Produto.id != (p.id or 0)
            ).scalar()
            if outro is not None:
                raise CadastroInvalido(f"O código de barras \"{barras}\" já é do produto \"{outro}\".")
        limpo["codigo_barras"] = barras

    unidade = dados.get("unidade_medida", p.unidade_medida) or UnidadeMedida.UN
    if "unidade_medida" in dados:
        if dados["unidade_medida"] is None:
            raise CadastroInvalido("Informe a unidade do produto (UN ou KG).")
        if not novo and historico and unidade != p.unidade_medida:
            raise CadastroInvalido(
                "A unidade não pode mudar: o produto já tem vendas, perdas, contagens ou previsões em "
                f"{p.unidade_medida.value}. Para vender em {unidade.value}, cadastre outro produto."
            )
        limpo["unidade_medida"] = unidade

    peso = dados.get("peso_medio_kg", p.peso_medio_kg)
    if unidade == UnidadeMedida.UN:
        if "peso_medio_kg" in dados and dados["peso_medio_kg"] is not None:
            raise CadastroInvalido("Peso médio só vale para produto em KG.")
        if p.peso_medio_kg is not None or "peso_medio_kg" in dados:
            limpo["peso_medio_kg"] = None
    elif "peso_medio_kg" in dados:
        if peso is not None:
            peso = Decimal(peso)
            if peso <= 0 or peso > PESO_MAXIMO:
                raise CadastroInvalido("O peso médio deve ser maior que zero (em kg).")
            if _casas(peso) > 4:
                raise CadastroInvalido("O peso médio aceita no máximo 4 casas decimais.")
        limpo["peso_medio_kg"] = peso

    for campo, rotulo in (("ativo", "se o produto está ativo"), ("vigencia_recorrente", "se a vigência se repete")):
        if campo in dados:
            if not isinstance(dados[campo], bool):
                raise CadastroInvalido(f"Informe {rotulo} (sim ou não).")
            limpo[campo] = dados[campo]

    if "tipo_abastecimento" in dados:
        if dados["tipo_abastecimento"] is None:
            raise CadastroInvalido("Informe o tipo de abastecimento (produzido ou distribuído).")
        limpo["tipo_abastecimento"] = dados["tipo_abastecimento"]

    if "dias_validade" in dados:
        v = dados["dias_validade"]
        if v is not None and (v < 1 or v > VALIDADE_MAXIMA_DIAS):
            raise CadastroInvalido(f"A validade deve ficar entre 1 e {VALIDADE_MAXIMA_DIAS} dias (ou vazia).")
        limpo["dias_validade"] = v

    if "margem_maxima_percentual" in dados:
        m = dados["margem_maxima_percentual"]
        if m is not None:
            m = Decimal(m)
            if m < 0 or m > MARGEM_MAXIMA:
                raise CadastroInvalido("A margem deve ficar entre 0% e 500% (ou vazia, para usar 10%).")
            if _casas(m) > 2:
                raise CadastroInvalido("A margem aceita no máximo 2 casas decimais.")
        limpo["margem_maxima_percentual"] = m

    if _VIGENCIA & dados.keys() or novo:
        inicio = dados.get("data_inicio_vigencia", p.data_inicio_vigencia)
        fim = dados.get("data_fim_vigencia", p.data_fim_vigencia)
        recorrente = dados.get("vigencia_recorrente", p.vigencia_recorrente) or False
        ciclo = dados.get("ciclo_previsao", p.ciclo_previsao) or CicloPrevisao.SEMANAL
        if dados.get("ciclo_previsao", 0) is None:
            raise CadastroInvalido("Informe o ciclo da previsão (semanal ou sazonal).")
        if inicio is not None and fim is not None and fim < inicio and not recorrente:
            raise CadastroInvalido("A data final da vigência não pode ser antes da inicial.")
        if recorrente and (inicio is None or fim is None):
            raise CadastroInvalido("Produto sazonal precisa das duas datas da temporada (início e fim).")
        if (ciclo == CicloPrevisao.SAZONAL) != recorrente:
            raise CadastroInvalido(
                "Produto sazonal repete a temporada todo ano: use o ciclo sazonal junto com a vigência recorrente."
            )
        for campo in _VIGENCIA & dados.keys():
            limpo[campo] = dados[campo]

    if "setor_producao_id" in dados:
        setor_id = dados["setor_producao_id"]
        if setor_id is not None:
            setor = db.query(SetorProducao).filter(
                SetorProducao.id == setor_id,
                SetorProducao.negocio_id == gestor.negocio_id,
                SetorProducao.central_producao_id == gestor.central_producao_id,
            ).one_or_none()
            if setor is None:
                raise CadastroInvalido("Setor não encontrado. Escolha um setor da sua central.")
            if not setor.ativo and setor_id != p.setor_producao_id:
                raise CadastroInvalido(f"O setor \"{setor.nome}\" está inativo. Reative o setor ou escolha outro.")
        limpo["setor_producao_id"] = setor_id

    if "dias_producao" in dados:
        dias = dados["dias_producao"] or []
        if len(set(dias)) != len(dias):
            raise CadastroInvalido("Um dia da semana foi informado mais de uma vez no calendário.")
        limpo["dias_producao"] = [d for d in ORDEM_DIAS if d in set(dias)]
    return limpo


# ---------------------------------------------------------------- escrita


def _aplicar(db: Session, gestor: GestorCentralAutenticado, p: Produto, limpo: dict) -> None:
    dias = limpo.pop("dias_producao", None)
    for campo, valor in limpo.items():
        setattr(p, campo, valor)
    try:
        db.flush()
    except IntegrityError as erro:
        db.rollback()
        if "uq_produto_negocio_codigo" in str(erro.orig):
            raise CadastroInvalido("Este código já é de outro produto.") from erro
        raise
    if dias is not None:
        db.query(CalendarioProducao).filter(
            CalendarioProducao.negocio_id == gestor.negocio_id, CalendarioProducao.produto_id == p.id
        ).delete(synchronize_session=False)
        db.add_all([CalendarioProducao(negocio_id=gestor.negocio_id, produto_id=p.id, dia_semana=d) for d in dias])


def criar_produto(
    db: Session, gestor: GestorCentralAutenticado, dados: dict, habilitar_lojas: bool = True
) -> ProdutoDetalhe:
    """Produto novo no negócio do gestor; com `habilitar_lojas`, já ativo nas lojas ativas da central (D101)."""
    rascunho = Produto(
        negocio_id=gestor.negocio_id, unidade_medida=UnidadeMedida.UN, ativo=True,
        tipo_abastecimento=TipoAbastecimento.PRODUZIDO, vigencia_recorrente=False, ciclo_previsao=CicloPrevisao.SEMANAL,
    )
    limpo = _validar(db, gestor, rascunho, dados, novo=True, historico=False)
    db.add(rascunho)
    _aplicar(db, gestor, rascunho, limpo)
    if habilitar_lojas:
        for loja in consulta_lojas_do_gestor(db, gestor).filter(Loja.ativo.is_(True)):
            db.add(ProdutoLoja(produto_id=rascunho.id, loja_id=loja.id, ativo=True))
    db.commit()
    return detalhar_produto(db, gestor, rascunho.id)


def editar_produto(db: Session, gestor: GestorCentralAutenticado, produto_id: int, dados: dict) -> ProdutoDetalhe:
    """Muda só os campos informados; confere o resultado final (vigência, unidade, peso)."""
    p = _produto(db, gestor, produto_id)
    historico = "unidade_medida" in dados and tem_historico(db, gestor.negocio_id, p.id)
    limpo = _validar(db, gestor, p, dados, novo=False, historico=historico)
    _aplicar(db, gestor, p, limpo)
    db.commit()
    return detalhar_produto(db, gestor, p.id)


# ---------------------------------------------------------------- lojas


def lojas_do_produto(db: Session, gestor: GestorCentralAutenticado, produto_id: int) -> list[LojaDoProduto]:
    """Lojas da central do gestor (ativas e inativas) e a situação do produto em cada uma."""
    p = _produto(db, gestor, produto_id)
    lojas = consulta_lojas_do_gestor(db, gestor).order_by(Loja.codigo.asc().nulls_last(), Loja.nome, Loja.id).all()
    habilitacoes = {
        pl.loja_id: pl.ativo
        for pl in db.query(ProdutoLoja).filter(
            ProdutoLoja.produto_id == p.id, ProdutoLoja.loja_id.in_([lj.id for lj in lojas] or [0])
        )
    }
    return [
        LojaDoProduto(
            loja_id=lj.id, codigo=lj.codigo, nome=lj.nome, loja_ativa=lj.ativo,
            habilitado=lj.id in habilitacoes, ativo=habilitacoes.get(lj.id, False),
        )
        for lj in lojas
    ]


def definir_loja(
    db: Session, gestor: GestorCentralAutenticado, produto_id: int, loja_id: int, ativo: bool
) -> LojaDoProduto:
    """Ativa (cria a habilitação, se não houver) ou desativa (mantém a linha) o produto na loja (D100)."""
    p = _produto(db, gestor, produto_id)
    loja = consulta_lojas_do_gestor(db, gestor).filter(Loja.id == loja_id).one_or_none()
    if loja is None:
        raise LojaNaoEncontrada("Loja não encontrada.")
    if not isinstance(ativo, bool):
        raise CadastroInvalido("Informe se o produto fica ativo na loja (sim ou não).")
    pl = db.query(ProdutoLoja).filter(ProdutoLoja.produto_id == p.id, ProdutoLoja.loja_id == loja.id).one_or_none()
    if pl is None and ativo:
        pl = ProdutoLoja(produto_id=p.id, loja_id=loja.id, ativo=True)
        db.add(pl)
    elif pl is not None:
        pl.ativo = ativo
    db.commit()
    return LojaDoProduto(
        loja_id=loja.id, codigo=loja.codigo, nome=loja.nome, loja_ativa=loja.ativo,
        habilitado=pl is not None, ativo=bool(pl and pl.ativo),
    )


def contar_lojas_ativas(db: Session, gestor: GestorCentralAutenticado, produto_ids: list[int]) -> dict[int, int]:
    """Por produto, em quantas lojas da central ele está ativo (para a lista da tela)."""
    if not produto_ids:
        return {}
    ids_lojas = [lj.id for lj in consulta_lojas_do_gestor(db, gestor)]
    if not ids_lojas:
        return {}
    return dict(
        db.query(ProdutoLoja.produto_id, func.count(ProdutoLoja.id))
        .filter(ProdutoLoja.produto_id.in_(produto_ids), ProdutoLoja.loja_id.in_(ids_lojas), ProdutoLoja.ativo.is_(True))
        .group_by(ProdutoLoja.produto_id)
    )
