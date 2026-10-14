"""
Erros de validação da requisição em português (handler único).

Sem isto, um corpo ou parâmetro com tipo errado (data inválida, texto onde
vai número, valor fora da lista) volta do FastAPI com a mensagem do
Pydantic em inglês, numa lista técnica. As telas mostram `detail` quando é
texto (frontend-saas: `mensagemDeErro`; app mobile: `data.detail` no
login), então o handler devolve:

    422 {"detail": "<frase para o usuário>",
         "erros": [{"campo": "valor_ajuste", "mensagem": "..."}]}

`detail` junta as mensagens; `erros` mantém o detalhe por campo para quem
precisar (ex.: marcar o campo no formulário).

Vale só para erros de validação da ENTRADA (RequestValidationError). Erros
de regra de negócio (HTTPException com detail próprio, inclusive o
relatório de importação de CSV) não passam por aqui.
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_ORIGENS = {"body", "query", "path", "header", "cookie"}


def _campo(loc) -> str:
    partes = [str(p) for p in loc if str(p) not in _ORIGENS]
    return ".".join(partes)


def _formatar(valor) -> str:
    return str(valor).replace(".", ",") if isinstance(valor, float) else str(valor)


def mensagem_do_erro(erro: dict) -> str:
    """Frase em português para um erro do Pydantic."""
    campo = _campo(erro.get("loc", ()))
    tipo = erro.get("type", "")
    ctx = erro.get("ctx") or {}
    o_campo = f"O campo '{campo}'" if campo else "A requisição"
    em = f"em '{campo}'" if campo else "na requisição"

    if tipo == "missing":
        return f"{o_campo} é obrigatório."
    if tipo == "json_invalid":
        return "O corpo da requisição não é um JSON válido."
    if tipo in ("enum", "literal_error"):
        opcoes = str(ctx.get("expected", "")).replace(" or ", " ou ")
        return f"Valor inválido {em}. Use um destes: {opcoes}."
    if tipo.startswith("date") or tipo.startswith("datetime"):
        return f"Data inválida {em}. Use o formato AAAA-MM-DD."
    if tipo in ("int_parsing", "int_type", "int_from_float"):
        return f"{o_campo} precisa ser um número inteiro."
    if tipo.startswith("decimal") or tipo.startswith("float"):
        return f"{o_campo} precisa ser um número."
    if tipo in ("bool_parsing", "bool_type"):
        return f"{o_campo} precisa ser verdadeiro ou falso."
    if tipo == "greater_than_equal":
        return f"{o_campo} precisa ser no mínimo {_formatar(ctx.get('ge'))}."
    if tipo == "greater_than":
        return f"{o_campo} precisa ser maior que {_formatar(ctx.get('gt'))}."
    if tipo == "less_than_equal":
        return f"{o_campo} pode ser no máximo {_formatar(ctx.get('le'))}."
    if tipo == "less_than":
        return f"{o_campo} precisa ser menor que {_formatar(ctx.get('lt'))}."
    if tipo == "string_too_long":
        return f"{o_campo} pode ter no máximo {ctx.get('max_length')} caracteres."
    if tipo == "string_too_short":
        return f"{o_campo} precisa ter pelo menos {ctx.get('min_length')} caractere(s)."
    if tipo in ("string_type", "list_type", "dict_type", "model_type", "model_attributes_type"):
        return f"Formato inválido {em}."
    return f"Valor inválido {em}."


async def tratar_erro_de_validacao(request: Request, exc: RequestValidationError) -> JSONResponse:
    erros = [{"campo": _campo(e.get("loc", ())), "mensagem": mensagem_do_erro(e)} for e in exc.errors()]
    mensagens = list(dict.fromkeys(e["mensagem"] for e in erros))
    return JSONResponse(status_code=422, content={"detail": " ".join(mensagens), "erros": erros})
