"""
Dados de demonstração da Fase 4 (necessidade e ordem de produção): um
negócio separado, "Rede Demo Produção", com contagens de estoque.

Por que um negócio separado, e não contagens nas lojas do seed principal:
- a Loja 001 da "Rede Padaria Teste" tem contagens reais feitas no app
  (testes do Ualker no iPhone, de julho a outubro de 2026), que seriam
  sobrescritas;
- os testes de regressão contam o seed principal (11 produtos, lojas 001 e
  002); produtos e lojas a mais os quebrariam.

O que é criado (gestor `gestor.producao@teste.com`, senha `senha123`):
- central "Central Demo Produção" (seção padaria, prazo de entrega 0, D32);
- lojas P01 e P02 (P02 vende 60% da P01);
- 7 produtos, cada um com um caso da necessidade:
    PRD-01 Pão Francês (KG, validade 1, diário): a sobra contada ontem vence
           antes da chegada e conta 0 (D35);
    PRD-02 Bolo de Cenoura (UN, validade 3, seg/qua/sex, margem 5%): estoque
           contado entra na conta;
    PRD-03 Torta de Frango (UN, validade 2, seg/qui): cobertura maior que a
           validade (D36); na P02 **nunca foi contada** (sem linha de estoque);
    PRD-04 Pão de Forma (KG, validade 5, seg/qui): na P02 a contagem é de
           3 dias atrás, mais antiga que o fechamento da véspera (D33);
    PRD-05 Manteiga 200 g (UN, validade 30, ter/sex): **distribuído** (D39);
    PRD-06 Empada de Frango (UN, validade 2, diário): só 2 semanas de venda,
           "pouco histórico", margem de 20% (D34);
    PRD-07 Sonho (UN, validade 1): **sem calendário** (D42).
- setores de produção da central (D67): "Pães" (PRD-01, PRD-04), "Bolos e
  doces" (PRD-02, PRD-07) e "Salgados" (PRD-03); a Empada (PRD-06) fica
  **sem setor** (sai na folha "Sem setor" da impressão). A Manteiga é
  distribuída e não entra na folha de produção.
- 8 semanas de vendas e perdas até ontem (PRD-06: só 2 semanas), origem
  `manual`, gravadas com a regra da importação (substitui, D5). Perda pela
  validade (1 dia ~9%, 2 dias ~5%, 3 dias ~3%, 5 dias ~1,5%, 30 dias ~1%).
- contagens de estoque (`estoque_atual`) feitas "no fechamento de hoje":
  sobra de ~15% da venda de ontem, em peças (KG: peças × peso médio).

Hora da contagem: hoje às 21h (o horário de fechamento padrão da loja,
D44), em São Paulo, gravada em UTC sem fuso, como o app grava
(`atualizado_em` usa `datetime.utcnow`). É o cenário da tela de produção:
à noite, depois que as lojas fecham e contam, o gestor gera a ordem de
AMANHÃ, e a contagem vale (feita desde o fechamento da véspera de D menos
2 h). Até 2026-10-15 a contagem era "de ontem", o que só servia para a
ordem de hoje.

Idempotente: tudo é procurado antes de ser criado; vendas e perdas são
substituídas; o estoque é regravado. A janela acompanha a data de hoje
(vendas antigas do PRD-06 apagadas; contagens sempre "de hoje"), para a
demonstração valer em qualquer dia.

Não gera previsão nem ordem: entre com o gestor e use as telas (ou a API).

Como rodar (na pasta backend/, com o venv ativo):
    python scripts/seed_demo_producao.py
"""

import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from zoneinfo import ZoneInfo  # noqa: E402

from app.core.security import hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.calendario_producao import CalendarioProducao, DiaSemana  # noqa: E402
from app.models.central_producao import CentralProducao, SecaoCentral  # noqa: E402
from app.models.estoque_atual import EstoqueAtual  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.perda_diaria import OrigemPerda, PerdaDiaria  # noqa: E402
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida  # noqa: E402
from app.models.produto_loja import ProdutoLoja  # noqa: E402
from app.models.setor_producao import SetorProducao  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402

NOME_NEGOCIO = "Rede Demo Produção"
NOME_CENTRAL = "Central Demo Produção"
LOJAS = {"P01": ("Loja Demo Norte", 1.0), "P02": ("Loja Demo Sul", 0.6)}
GESTOR = {"email": "gestor.producao@teste.com", "nome": "Gestor Demo Produção"}
SENHA = "senha123"
SEMENTE = "frescor-demo-producao-v1"

SEMANAS_HISTORICO = 8
SEMANAS_POUCO_HISTORICO = 2
SOBRA_CONTADA = 0.15
HORA_CONTAGEM = time(21, 0)
FUSO_PADRAO = ZoneInfo("America/Sao_Paulo")
DIAS_CONTAGEM_ANTIGA = 3

_TODOS = list(DiaSemana)
_SEG_QUI = [DiaSemana.SEGUNDA, DiaSemana.QUINTA]
PROD = TipoAbastecimento.PRODUZIDO
DIST = TipoAbastecimento.DISTRIBUIDO

# codigo: (nome, unidade, peso médio kg, validade, margem %, tipo, calendário, venda/dia na P01, semanas)
PRODUTOS = {
    "PRD-01": ("Pão Francês", UnidadeMedida.KG, "0.0500", 1, None, PROD, _TODOS, 30, SEMANAS_HISTORICO),
    "PRD-02": ("Bolo de Cenoura", UnidadeMedida.UN, None, 3, "5.00", PROD,
               [DiaSemana.SEGUNDA, DiaSemana.QUARTA, DiaSemana.SEXTA], 12, SEMANAS_HISTORICO),
    "PRD-03": ("Torta de Frango", UnidadeMedida.UN, None, 2, None, PROD, _SEG_QUI, 15, SEMANAS_HISTORICO),
    "PRD-04": ("Pão de Forma", UnidadeMedida.KG, "0.5000", 5, None, PROD, _SEG_QUI, 8, SEMANAS_HISTORICO),
    "PRD-05": ("Manteiga 200 g", UnidadeMedida.UN, None, 30, None, DIST,
               [DiaSemana.TERCA, DiaSemana.SEXTA], 10, SEMANAS_HISTORICO),
    "PRD-06": ("Empada de Frango", UnidadeMedida.UN, None, 2, None, PROD, _TODOS, 20, SEMANAS_POUCO_HISTORICO),
    "PRD-07": ("Sonho", UnidadeMedida.UN, None, 1, None, PROD, [], 25, SEMANAS_HISTORICO),
}
CODIGO_POUCO_HISTORICO = "PRD-06"
# Setores de produção (D67): nome -> (ordem de exibição, produtos). PRD-06 sem setor.
SETORES = {
    "Pães": (1, ["PRD-01", "PRD-04"]),
    "Bolos e doces": (2, ["PRD-02", "PRD-07"]),
    "Salgados": (3, ["PRD-03"]),
}
SEM_CONTAGEM = {("P02", "PRD-03")}
CONTAGEM_ANTIGA = {("P02", "PRD-04")}

# segunda=0 ... domingo=6 (mesmo padrão do seed_vendas.py)
FATOR_DIA_SEMANA = {0: 0.85, 1: 0.85, 2: 0.90, 3: 0.95, 4: 1.10, 5: 1.35, 6: 1.25}
TAXA_PERDA_POR_VALIDADE = {1: 0.09, 2: 0.05, 3: 0.03, 5: 0.015, 30: 0.01}


def _obter_ou_criar(db, modelo, filtros: dict, valores: dict):
    """Devolve (registro, criado)."""
    registro = db.query(modelo).filter_by(**filtros).order_by(modelo.id).first()
    if registro is not None:
        return registro, False
    registro = modelo(**filtros, **valores)
    db.add(registro)
    db.flush()
    return registro, True


def _rng(*partes) -> random.Random:
    return random.Random("|".join([SEMENTE, *map(str, partes)]))


def _arredondar(valor: float, unidade: UnidadeMedida, rng: random.Random) -> Decimal:
    """UN: inteiro com arredondamento probabilístico (média preservada); KG: 3 casas."""
    if unidade == UnidadeMedida.UN:
        base = int(valor)
        return Decimal(base + (1 if rng.random() < valor - base else 0))
    return Decimal(str(valor)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _venda(codigo, loja_codigo, fator_loja, media, unidade, dia) -> Decimal:
    rng = _rng("venda", codigo, loja_codigo, dia.isoformat())
    valor = media * fator_loja * FATOR_DIA_SEMANA[dia.weekday()] * min(max(rng.gauss(1.0, 0.10), 0.7), 1.3)
    return _arredondar(valor, unidade, rng)


def _perda(codigo, loja_codigo, venda, validade, unidade, dia) -> Decimal:
    rng = _rng("perda", codigo, loja_codigo, dia.isoformat())
    valor = float(venda) * TAXA_PERDA_POR_VALIDADE[validade] * min(max(rng.gauss(1.0, 0.35), 0.0), 2.5)
    return _arredondar(valor, unidade, rng)


def _utc_sem_fuso(dia: date, hora: time) -> datetime:
    """Hora de São Paulo (fuso padrão da loja, D44) -> UTC sem fuso (como o app grava atualizado_em)."""
    return datetime.combine(dia, hora, tzinfo=FUSO_PADRAO).astimezone(timezone.utc).replace(tzinfo=None)


def _upsert(db, modelo, constraint, linhas):
    if not linhas:
        return
    stmt = pg_insert(modelo).values(linhas)
    stmt = stmt.on_conflict_do_update(
        constraint=constraint,
        set_={"quantidade": stmt.excluded.quantidade, "atualizado_em": func.now()},
    )
    db.execute(stmt)


def main():
    db = SessionLocal()
    try:
        negocio, criado = _obter_ou_criar(db, Negocio, {"nome": NOME_NEGOCIO}, {"ativo": True})
        print(f"Negócio: {negocio.nome} (id={negocio.id}) [{'criado' if criado else 'existente'}]")
        central, criado = _obter_ou_criar(
            db, CentralProducao, {"negocio_id": negocio.id, "nome": NOME_CENTRAL},
            {"ativa": True, "secao": SecaoCentral.PADARIA, "prazo_entrega_dias": 0},
        )
        print(f"Central: {central.nome} (id={central.id}, seção {central.secao.value}, "
              f"prazo {central.prazo_entrega_dias}) [{'criado' if criado else 'existente'}]")

        lojas = {}
        for codigo, (nome, _fator) in LOJAS.items():
            loja, criado = _obter_ou_criar(
                db, Loja, {"negocio_id": negocio.id, "codigo": codigo},
                {"nome": nome, "central_producao_id": central.id, "horario_zeragem": time(6, 0), "ativo": True},
            )
            lojas[codigo] = loja
            print(f"Loja:    {codigo} · {nome} (id={loja.id}) [{'criado' if criado else 'existente'}]")

        gestor = db.query(Usuario).filter(Usuario.email == GESTOR["email"]).first()
        if gestor is None:
            gestor = Usuario(
                negocio_id=negocio.id, tipo_usuario=TipoUsuario.GESTOR_CENTRAL, central_producao_id=central.id,
                nome=GESTOR["nome"], email=GESTOR["email"], senha_hash=hash_senha(SENHA),
                status=StatusUsuario.ATIVO, tem_acesso_app=False, tem_acesso_web=True,
            )
            db.add(gestor)
            db.flush()
            print(f"Gestor:  {gestor.email} (id={gestor.id}) [criado]")
        else:
            print(f"Gestor:  {gestor.email} (id={gestor.id}) [existente]")

        setor_ids = {}
        for nome_setor, (ordem_setor, _) in SETORES.items():
            setor, criado = _obter_ou_criar(
                db, SetorProducao, {"negocio_id": negocio.id, "central_producao_id": central.id, "nome": nome_setor},
                {"ordem": ordem_setor, "ativo": True},
            )
            setor.ordem, setor.ativo = ordem_setor, True
            setor_ids[nome_setor] = setor.id
            print(f"Setor:   {nome_setor} (id={setor.id}, ordem {ordem_setor}) [{'criado' if criado else 'existente'}]")

        ontem = date.today() - timedelta(days=1)
        hoje = ontem + timedelta(days=1)
        contagem_hoje = _utc_sem_fuso(hoje, HORA_CONTAGEM)  # fechamento de hoje
        contagem_antiga = _utc_sem_fuso(hoje - timedelta(days=DIAS_CONTAGEM_ANTIGA), HORA_CONTAGEM)
        vendas, perdas = [], []
        estoques_gravados = 0
        for codigo, (nome, unidade, peso, validade, margem, tipo, dias, media, semanas) in PRODUTOS.items():
            produto, criado = _obter_ou_criar(
                db, Produto, {"negocio_id": negocio.id, "codigo": codigo},
                {"nome": nome, "unidade_medida": unidade, "ativo": True},
            )
            produto.nome = nome
            produto.peso_medio_kg = Decimal(peso) if peso else None
            produto.dias_validade = validade
            produto.margem_maxima_percentual = Decimal(margem) if margem else None
            produto.tipo_abastecimento = tipo
            produto.setor_producao_id = next(
                (setor_ids[n] for n, (_, codigos) in SETORES.items() if codigo in codigos), None
            )

            existentes = (
                db.query(CalendarioProducao)
                .filter(CalendarioProducao.negocio_id == negocio.id, CalendarioProducao.produto_id == produto.id)
                .all()
            )
            for registro in existentes:
                if registro.dia_semana not in dias:
                    db.delete(registro)
            dias_existentes = {registro.dia_semana for registro in existentes}
            for dia_semana in dias:
                if dia_semana not in dias_existentes:
                    db.add(CalendarioProducao(negocio_id=negocio.id, produto_id=produto.id, dia_semana=dia_semana))

            inicio = ontem - timedelta(days=7 * semanas - 1)
            for loja_codigo, loja in lojas.items():
                fator = LOJAS[loja_codigo][1]
                _obter_ou_criar(db, ProdutoLoja, {"produto_id": produto.id, "loja_id": loja.id}, {"ativo": True})
                # A janela anda com a data de hoje: o que ficou antes dela sai (para
                # todos os produtos; o PRD-06 tem a janela curta de propósito).
                # Até 2026-10-16 só o PRD-06 era limpo, e rodar o seed num dia
                # seguinte deixava um dia de venda a mais nos outros.
                for modelo in (VendaDiaria, PerdaDiaria):
                    db.query(modelo).filter(
                        modelo.negocio_id == negocio.id, modelo.loja_id == loja.id,
                        modelo.produto_id == produto.id, modelo.data < inicio,
                    ).delete(synchronize_session=False)
                venda_ontem = Decimal(0)
                for n in range(7 * semanas):
                    dia = inicio + timedelta(days=n)
                    qtd = _venda(codigo, loja_codigo, fator, media, unidade, dia)
                    chave = dict(negocio_id=negocio.id, loja_id=loja.id, produto_id=produto.id, data=dia)
                    vendas.append({**chave, "quantidade": qtd, "origem": OrigemVenda.MANUAL})
                    perdas.append({**chave, "quantidade": _perda(codigo, loja_codigo, qtd, validade, unidade, dia),
                                   "origem": OrigemPerda.MANUAL})
                    if dia == ontem:
                        venda_ontem = qtd

                if (loja_codigo, codigo) in SEM_CONTAGEM:
                    db.query(EstoqueAtual).filter(
                        EstoqueAtual.negocio_id == negocio.id, EstoqueAtual.loja_id == loja.id,
                        EstoqueAtual.produto_id == produto.id,
                    ).delete(synchronize_session=False)
                    continue
                # Sobra em peças: em KG, kg ÷ peso médio de uma peça.
                sobra = float(venda_ontem) * SOBRA_CONTADA
                pecas = round(sobra / float(peso)) if peso else round(sobra)
                calculado = Decimal(pecas) * Decimal(peso) if peso else Decimal(pecas)
                estoque, _ = _obter_ou_criar(
                    db, EstoqueAtual, {"negocio_id": negocio.id, "loja_id": loja.id, "produto_id": produto.id}, {},
                )
                estoque.quantidade_inventariada = pecas
                estoque.estoque_atual_calculado = calculado
                estoque.peso_informado_kg = None
                # A hora da contagem vai sempre no UPDATE: sem isso, o onupdate da
                # coluna gravaria "agora". Atribuir não basta: se o valor já é o
                # mesmo, o SQLAlchemy não o inclui no UPDATE (daí o flag_modified).
                estoque.atualizado_em = (
                    contagem_antiga if (loja_codigo, codigo) in CONTAGEM_ANTIGA else contagem_hoje
                )
                flag_modified(estoque, "atualizado_em")
                estoques_gravados += 1

            print(f"Produto: {codigo} · {nome} ({unidade.value}, {tipo.value}, validade {validade}, "
                  f"margem {margem or '-'}, calendário {','.join(d.value[:3] for d in dias) or 'nenhum'}) "
                  f"[{'criado' if criado else 'existente'}]")

        _upsert(db, VendaDiaria, "uq_venda_loja_produto_data_origem", vendas)
        _upsert(db, PerdaDiaria, "uq_perda_loja_produto_data_origem", perdas)
        db.commit()

        ids_lojas = [loja.id for loja in lojas.values()]
        total_vendas = db.query(func.count(VendaDiaria.id)).filter(VendaDiaria.loja_id.in_(ids_lojas)).scalar()
        total_perdas = db.query(func.count(PerdaDiaria.id)).filter(PerdaDiaria.loja_id.in_(ids_lojas)).scalar()
        print(f"Vendas gravadas: {len(vendas)} (total nas lojas: {total_vendas}); "
              f"perdas: {len(perdas)} (total: {total_perdas})")
        print(f"Contagens de estoque: {estoques_gravados}, fechamento de {hoje:%d/%m/%Y} às "
              f"{HORA_CONTAGEM:%H:%M} (São Paulo; {contagem_hoje:%d/%m %H:%M} UTC); "
              f"sem contagem: {sorted(SEM_CONTAGEM)}; antiga ({DIAS_CONTAGEM_ANTIGA} dias): {sorted(CONTAGEM_ANTIGA)}")
        print(f"Entre no SaaS com {GESTOR['email']} / {SENHA}.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
