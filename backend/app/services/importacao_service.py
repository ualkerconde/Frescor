"""
Importação de vendas e perdas diárias por arquivo CSV (Fase 2 / P4).

É a porta de entrada do dado de venda/perda enquanto a integração com o PDV
não existe (D3 em aberto). Sem esse dado não há previsão (Fase 3), por isso
a importação precisa ser à prova de erro de digitação e de arquivo trocado:
um número errado aqui vira produção errada lá na frente.

Regras (docs/STATUS.md):
- D7 (provisória): CSV com `;`, vírgula decimal, data `dd/mm/aaaa`,
  cabeçalho `data;codigo_loja;codigo_produto;quantidade`, loja por
  `lojas.codigo` e produto por `produtos.codigo`. Aceita UTF-8 (com ou sem
  BOM) e Windows-1252 (o "CSV" do Excel em português).
- D9: tudo ou nada. Qualquer linha inválida -> nada é gravado e o
  resultado traz o erro de cada linha.
- D5: linha de loja + produto + data já importada (mesma origem, `manual`)
  tem a quantidade SUBSTITUÍDA.
- D6: quantidade na unidade do produto, até 3 casas decimais, não negativa.
  Mais de 3 casas é recusado (o banco arredondaria sem avisar).
- D8: só lojas da central do gestor. D12: loja inativa é recusada.
- D13: quantidade fracionária em produto UN é recusada; data futura é
  recusada; produto inativo é aceito; produto não habilitado (ou
  desabilitado) naquela loja é aceito com AVISO (lista separada, não
  bloqueia o arquivo).
- Coerência de negócio: loja e produto são procurados só no negócio do
  gestor, com mensagem clara. O banco também garante (FKs compostas da
  migration 0015), mas a mensagem do banco não serve para o usuário.

Escolhas conservadoras não cobertas por decisão (revisáveis, ver STATUS):
- quantidade com ponto ("1.234") é recusada: ambíguo entre milhar e decimal;
- loja + produto + data repetidos no MESMO arquivo é erro (qual vale?);
- linhas totalmente vazias são ignoradas (o Excel costuma deixá-las no fim).
O código de produto é único no negócio (migration 0016), então não há linha
ambígua.
"""

import csv
import enum
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado
from app.models.loja import Loja
from app.models.perda_diaria import OrigemPerda, PerdaDiaria
from app.models.produto import Produto, UnidadeMedida
from app.models.produto_loja import ProdutoLoja
from app.models.venda_diaria import OrigemVenda, VendaDiaria
from app.services.escopo_service import consulta_lojas_do_gestor

CABECALHO = ["data", "codigo_loja", "codigo_produto", "quantidade"]
SEPARADOR = ";"
MAX_LINHAS = 100_000
MAX_ERROS_LISTADOS = 200
CASAS_DECIMAIS = 3

_RE_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_RE_QUANTIDADE = re.compile(r"^-?\d+(,\d+)?$")


class TipoImportacao(str, enum.Enum):
    VENDA = "venda"
    PERDA = "perda"


@dataclass
class ErroLinha:
    linha: int  # número da linha no arquivo (o cabeçalho é a linha 1)
    mensagem: str


@dataclass
class AvisoLinha:
    """Algo que merece atenção, mas não impede a importação (D13)."""
    linha: int
    mensagem: str


@dataclass
class ResultadoImportacao:
    sucesso: bool
    linhas_lidas: int = 0
    inseridas: int = 0
    substituidas: int = 0
    erros: list[ErroLinha] = field(default_factory=list)
    erros_omitidos: int = 0
    avisos: list[AvisoLinha] = field(default_factory=list)
    avisos_omitidos: int = 0
    codificacao: str = ""


@dataclass
class _LinhaValida:
    linha: int
    data: date
    loja_id: int
    produto_id: int
    quantidade: Decimal
    cod_loja: str
    cod_produto: str


def _decodificar(conteudo: bytes) -> tuple[str, str]:
    """
    UTF-8 (com BOM ou não) primeiro; se não for UTF-8 válido, Windows-1252.
    Levanta ValueError se não for nenhum dos dois (o Windows-1252 não
    define alguns bytes, ex.: 0x81) ou se tiver byte nulo: não é um CSV.
    """
    if b"\x00" in conteudo:
        raise ValueError("o arquivo não é um CSV de texto (contém bytes nulos)")
    try:
        return conteudo.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return conteudo.decode("cp1252"), "windows-1252"
    except UnicodeDecodeError:
        raise ValueError("o arquivo não é um CSV de texto em UTF-8 nem em Windows-1252")


def _ler_data(texto: str) -> date:
    if not _RE_DATA.match(texto):
        raise ValueError(f"data inválida '{texto}' (use dd/mm/aaaa, ex.: 05/10/2026)")
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        raise ValueError(f"data inexistente '{texto}'")


def _ler_quantidade(texto: str) -> Decimal:
    if texto == "":
        raise ValueError("quantidade vazia")
    if "." in texto:
        raise ValueError(
            f"quantidade '{texto}' com ponto: use vírgula como separador decimal e não use separador de milhar"
        )
    if not _RE_QUANTIDADE.match(texto):
        raise ValueError(f"quantidade inválida '{texto}' (use números, ex.: 12 ou 1,250)")
    if texto.startswith("-"):
        raise ValueError(f"quantidade negativa '{texto}'")
    if "," in texto and len(texto.split(",")[1]) > CASAS_DECIMAIS:
        raise ValueError(f"quantidade '{texto}' com mais de {CASAS_DECIMAIS} casas decimais")
    try:
        return Decimal(texto.replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"quantidade inválida '{texto}'")


def _resultado_erro(resultado: ResultadoImportacao, erros: list[ErroLinha]) -> ResultadoImportacao:
    resultado.sucesso = False
    resultado.erros = erros[:MAX_ERROS_LISTADOS]
    resultado.erros_omitidos = max(0, len(erros) - MAX_ERROS_LISTADOS)
    return resultado


def _avisos_habilitacao(db: Session, validas: list[_LinhaValida]) -> list[AvisoLinha]:
    """
    D13 (c): produto sem habilitação naquela loja (sem linha em
    produtos_lojas) ou desabilitado temporariamente (ativo = false) gera
    aviso, não erro.
    """
    pares = list({(v.loja_id, v.produto_id) for v in validas})
    habilitacoes: dict[tuple[int, int], bool] = {}
    for i in range(0, len(pares), 1000):
        for pl in db.query(ProdutoLoja).filter(
            tuple_(ProdutoLoja.loja_id, ProdutoLoja.produto_id).in_(pares[i:i + 1000])
        ):
            habilitacoes[(pl.loja_id, pl.produto_id)] = pl.ativo
    avisos = []
    for v in validas:
        situacao = habilitacoes.get((v.loja_id, v.produto_id))
        if situacao is None:
            avisos.append(AvisoLinha(v.linha, f"produto '{v.cod_produto}' não está habilitado na loja '{v.cod_loja}'"))
        elif situacao is False:
            avisos.append(AvisoLinha(v.linha, f"produto '{v.cod_produto}' está desabilitado na loja '{v.cod_loja}'"))
    return avisos


def importar_csv(
    db: Session,
    gestor: GestorCentralAutenticado,
    conteudo: bytes,
    tipo: TipoImportacao,
    hoje: Optional[date] = None,
) -> ResultadoImportacao:
    """
    Valida o arquivo inteiro e, só se não houver nenhum erro, grava todas
    as linhas numa transação (origem `manual`). Devolve o resultado com
    contagens ou com a lista de erros por linha, e os avisos em ambos os
    casos.

    `hoje`: data de referência para recusar datas futuras (D13). Padrão:
    a data atual do servidor. O parâmetro existe para os testes.
    """
    hoje = hoje or date.today()
    resultado = ResultadoImportacao(sucesso=False)

    if not conteudo or not conteudo.strip():
        return _resultado_erro(resultado, [ErroLinha(0, "arquivo vazio")])

    try:
        texto, resultado.codificacao = _decodificar(conteudo)
        linhas = list(csv.reader(io.StringIO(texto, newline=""), delimiter=SEPARADOR))
    except (ValueError, csv.Error) as e:
        return _resultado_erro(resultado, [ErroLinha(0, str(e))])

    # Cabeçalho: comparação sem diferenciar maiúsculas e ignorando espaços.
    cabecalho = [c.strip().lower() for c in linhas[0]] if linhas else []
    if cabecalho != CABECALHO:
        return _resultado_erro(resultado, [ErroLinha(1, (
            f"cabeçalho inválido: esperado '{SEPARADOR.join(CABECALHO)}', encontrado '{SEPARADOR.join(linhas[0]) if linhas else ''}'"
            " (confira também se o separador é ponto e vírgula)"
        ))])

    # (número da linha no arquivo, campos) das linhas com conteúdo.
    dados = [(i, campos) for i, campos in enumerate(linhas[1:], start=2) if any(c.strip() for c in campos)]
    if not dados:
        return _resultado_erro(resultado, [ErroLinha(2, "o arquivo não tem nenhuma linha de dados")])
    if len(dados) > MAX_LINHAS:
        return _resultado_erro(resultado, [ErroLinha(0, f"o arquivo tem {len(dados)} linhas; o máximo é {MAX_LINHAS}")])
    resultado.linhas_lidas = len(dados)

    # Lojas da central do gestor (D8), por código. Lojas sem código não
    # podem ser referenciadas pelo CSV.
    lojas = {lj.codigo: lj for lj in consulta_lojas_do_gestor(db, gestor).filter(Loja.codigo.isnot(None))}

    # Produtos do negócio do gestor, por código (único no negócio, 0016).
    # Produto inativo é aceito (D13 b).
    produtos = {
        p.codigo: p
        for p in db.query(Produto).filter(Produto.negocio_id == gestor.negocio_id, Produto.codigo.isnot(None))
    }

    erros: list[ErroLinha] = []
    validas: list[_LinhaValida] = []
    vistas: dict[tuple[int, int, date], int] = {}

    for numero, campos in dados:
        campos = [c.strip() for c in campos]
        if len(campos) != len(CABECALHO):
            erros.append(ErroLinha(numero, f"esperadas {len(CABECALHO)} colunas, encontradas {len(campos)}"))
            continue
        txt_data, cod_loja, cod_produto, txt_qtd = campos
        problemas = []

        try:
            dia = _ler_data(txt_data)
            if dia > hoje:
                problemas.append(f"data futura {txt_data} (confira se dia e mês não estão trocados)")
        except ValueError as e:
            problemas.append(str(e))
            dia = None

        loja = lojas.get(cod_loja)
        if not cod_loja:
            problemas.append("código da loja vazio")
        elif loja is None:
            problemas.append(f"loja '{cod_loja}' não encontrada entre as lojas da sua central")
        elif not loja.ativo:
            problemas.append(f"loja '{cod_loja}' está inativa; reative a loja para importar dados dela")

        produto = produtos.get(cod_produto)
        if not cod_produto:
            problemas.append("código do produto vazio")
        elif produto is None:
            problemas.append(f"produto '{cod_produto}' não encontrado no seu negócio")

        try:
            quantidade = _ler_quantidade(txt_qtd)
        except ValueError as e:
            problemas.append(str(e))
            quantidade = None

        # D13 (a): produto contado por unidade não aceita fração ("2,0" vale).
        if (
            produto is not None and quantidade is not None
            and produto.unidade_medida == UnidadeMedida.UN
            and quantidade != quantidade.to_integral_value()
        ):
            problemas.append(
                f"produto '{cod_produto}' é contado por unidade (UN): a quantidade '{txt_qtd}' tem de ser inteira"
            )

        # Coerência de negócio, explícita (o banco também garante).
        if loja is not None and produto is not None and not (
            loja.negocio_id == produto.negocio_id == gestor.negocio_id
        ):
            problemas.append("loja e produto não pertencem ao mesmo negócio do seu usuário")

        if not problemas and dia is not None and loja is not None and produto is not None:
            chave = (loja.id, produto.id, dia)
            if chave in vistas:
                problemas.append(
                    f"loja '{cod_loja}', produto '{cod_produto}' e data {txt_data} repetidos (já aparecem na linha {vistas[chave]})"
                )
            else:
                vistas[chave] = numero

        if problemas:
            erros.append(ErroLinha(numero, "; ".join(problemas)))
        else:
            validas.append(_LinhaValida(numero, dia, loja.id, produto.id, quantidade, cod_loja, cod_produto))

    avisos = _avisos_habilitacao(db, validas)
    resultado.avisos = avisos[:MAX_ERROS_LISTADOS]
    resultado.avisos_omitidos = max(0, len(avisos) - MAX_ERROS_LISTADOS)

    if erros:
        return _resultado_erro(resultado, erros)

    # ---- gravação (tudo numa transação) ----
    modelo, origem = (
        (VendaDiaria, OrigemVenda.MANUAL) if tipo == TipoImportacao.VENDA else (PerdaDiaria, OrigemPerda.MANUAL)
    )
    chaves = [(v.loja_id, v.produto_id, v.data) for v in validas]
    existentes = 0
    for i in range(0, len(chaves), 1000):
        bloco = chaves[i:i + 1000]
        existentes += (
            db.query(func.count(modelo.id))
            .filter(
                modelo.negocio_id == gestor.negocio_id,
                modelo.origem == origem,
                tuple_(modelo.loja_id, modelo.produto_id, modelo.data).in_(bloco),
            )
            .scalar()
        )

    constraint = "uq_venda_loja_produto_data_origem" if tipo == TipoImportacao.VENDA else "uq_perda_loja_produto_data_origem"
    try:
        for i in range(0, len(validas), 1000):
            stmt = pg_insert(modelo).values([
                dict(negocio_id=gestor.negocio_id, loja_id=v.loja_id, produto_id=v.produto_id,
                     data=v.data, quantidade=v.quantidade, origem=origem)
                for v in validas[i:i + 1000]
            ])
            stmt = stmt.on_conflict_do_update(
                constraint=constraint,
                set_={"quantidade": stmt.excluded.quantidade, "atualizado_em": func.now()},
            )
            db.execute(stmt)
        db.commit()
    except Exception:
        db.rollback()
        raise

    resultado.sucesso = True
    resultado.substituidas = existentes
    resultado.inseridas = len(validas) - existentes
    return resultado
