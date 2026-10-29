"""
Cadastro da central e dos setores de produção pelo gestor (Fase 6 / C1).

Central (D103): o gestor lê e edita a PRÓPRIA central -- só o nome e o
prazo de entrega. A seção (D14) e o "ativa" (D4) ficam só para leitura:
desativar a própria central bloquearia o acesso do gestor, e trocar a
seção é trabalho futuro. Mudar o prazo vale para as ordens geradas depois
(a ordem guarda a data de entrega na geração, D32).

Setores (D67, D102): criar, renomear, mudar a ordem e desativar/reativar,
sempre na central do gestor. Não há apagar: um setor inativo some da
escolha e seus produtos saem na folha "Sem setor" (N9b). Nome único na
central (o banco garante: `uq_setor_central_nome`; aqui a mensagem é clara
e sem diferenciar maiúsculas).

`negocio_id` e `central_producao_id` vêm sempre do gestor autenticado
(regra de ouro 1). Setor de outra central, de outro negócio ou
inexistente -> `SetorNaoEncontrado`, sem distinguir os casos.

Este serviço não conhece HTTP: validação -> `CadastroInvalido` (422 na rota).
"""

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import GestorCentralAutenticado
from app.models.central_producao import CentralProducao
from app.models.loja import Loja
from app.models.setor_producao import SetorProducao

TAMANHO_MAXIMO_NOME_CENTRAL = 255
TAMANHO_MAXIMO_NOME_SETOR = 80
PRAZO_MAXIMO_DIAS = 7
ORDEM_MAXIMA = 9999


class CadastroInvalido(ValueError):
    pass


class SetorNaoEncontrado(LookupError):
    pass


_NAO_INFORMADO = object()


@dataclass(frozen=True)
class DadosCentral:
    id: int
    nome: str
    secao: str
    prazo_entrega_dias: int
    ativa: bool
    lojas: int


def _texto(valor, rotulo: str, tamanho: int) -> str:
    texto = (valor or "").strip() if isinstance(valor, str) or valor is None else None
    if texto is None:
        raise CadastroInvalido(f"Informe {rotulo} como texto.")
    if not texto:
        raise CadastroInvalido(f"Informe {rotulo}.")
    if len(texto) > tamanho:
        raise CadastroInvalido(f"{rotulo[0].upper()}{rotulo[1:]} pode ter no máximo {tamanho} caracteres.")
    return texto


def _inteiro(valor, rotulo: str, minimo: int, maximo: int) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise CadastroInvalido(f"{rotulo} deve ser um número inteiro.")
    if valor < minimo or valor > maximo:
        raise CadastroInvalido(f"{rotulo} deve ficar entre {minimo} e {maximo}.")
    return valor


# ---------------------------------------------------------------- central


def _central(db: Session, gestor: GestorCentralAutenticado) -> CentralProducao:
    return (
        db.query(CentralProducao)
        .filter(CentralProducao.id == gestor.central_producao_id, CentralProducao.negocio_id == gestor.negocio_id)
        .one()
    )


def _dados(db: Session, c: CentralProducao) -> DadosCentral:
    lojas = db.query(func.count(Loja.id)).filter(
        Loja.negocio_id == c.negocio_id, Loja.central_producao_id == c.id
    ).scalar()
    return DadosCentral(
        id=c.id, nome=c.nome, secao=c.secao.value, prazo_entrega_dias=c.prazo_entrega_dias, ativa=c.ativa, lojas=lojas
    )


def ler_central(db: Session, gestor: GestorCentralAutenticado) -> DadosCentral:
    """A central do gestor, com a contagem de lojas (ativas e inativas)."""
    return _dados(db, _central(db, gestor))


def editar_central(
    db: Session, gestor: GestorCentralAutenticado, nome=_NAO_INFORMADO, prazo_entrega_dias=_NAO_INFORMADO
) -> DadosCentral:
    """Muda o nome e/ou o prazo de entrega da central do gestor (só o que foi informado)."""
    c = _central(db, gestor)
    if nome is not _NAO_INFORMADO:
        c.nome = _texto(nome, "o nome da central", TAMANHO_MAXIMO_NOME_CENTRAL)
    if prazo_entrega_dias is not _NAO_INFORMADO:
        c.prazo_entrega_dias = _inteiro(prazo_entrega_dias, "O prazo de entrega", 0, PRAZO_MAXIMO_DIAS)
    db.commit()
    db.refresh(c)
    return _dados(db, c)


# ---------------------------------------------------------------- setores


def _setores(db: Session, gestor: GestorCentralAutenticado):
    return db.query(SetorProducao).filter(
        SetorProducao.negocio_id == gestor.negocio_id,
        SetorProducao.central_producao_id == gestor.central_producao_id,
    )


def _nome_livre(db: Session, gestor: GestorCentralAutenticado, nome: str, exceto_id: int | None = None) -> None:
    consulta = _setores(db, gestor).filter(func.lower(SetorProducao.nome) == nome.lower())
    if exceto_id is not None:
        consulta = consulta.filter(SetorProducao.id != exceto_id)
    if db.query(consulta.exists()).scalar():
        raise CadastroInvalido(f"Já existe um setor chamado \"{nome}\" nesta central.")


def criar_setor(db: Session, gestor: GestorCentralAutenticado, nome, ordem=None) -> SetorProducao:
    """Setor novo na central do gestor, ativo. Sem ordem: vai para o fim da lista."""
    nome = _texto(nome, "o nome do setor", TAMANHO_MAXIMO_NOME_SETOR)
    _nome_livre(db, gestor, nome)
    if ordem is None:
        maior = _setores(db, gestor).with_entities(func.max(SetorProducao.ordem)).scalar()
        ordem = min((maior or 0) + 1, ORDEM_MAXIMA)
    else:
        ordem = _inteiro(ordem, "A ordem", 0, ORDEM_MAXIMA)
    setor = SetorProducao(
        negocio_id=gestor.negocio_id, central_producao_id=gestor.central_producao_id, nome=nome, ordem=ordem, ativo=True
    )
    db.add(setor)
    db.commit()
    db.refresh(setor)
    return setor


def editar_setor(
    db: Session, gestor: GestorCentralAutenticado, setor_id: int,
    nome=_NAO_INFORMADO, ordem=_NAO_INFORMADO, ativo=_NAO_INFORMADO,
) -> SetorProducao:
    """Renomeia, muda a ordem e/ou ativa/desativa um setor da central do gestor."""
    setor = _setores(db, gestor).filter(SetorProducao.id == setor_id).one_or_none()
    if setor is None:
        raise SetorNaoEncontrado("Setor não encontrado.")
    if nome is not _NAO_INFORMADO:
        nome = _texto(nome, "o nome do setor", TAMANHO_MAXIMO_NOME_SETOR)
        _nome_livre(db, gestor, nome, exceto_id=setor.id)
        setor.nome = nome
    if ordem is not _NAO_INFORMADO:
        setor.ordem = _inteiro(ordem, "A ordem", 0, ORDEM_MAXIMA)
    if ativo is not _NAO_INFORMADO:
        if not isinstance(ativo, bool):
            raise CadastroInvalido("Informe se o setor está ativo (sim ou não).")
        setor.ativo = ativo
    db.commit()
    db.refresh(setor)
    return setor
