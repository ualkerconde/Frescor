"""
Script para criar produtos de teste com codigo, codigo_barras,
unidade de medida, peso médio e classificação (categoria/subcategoria).
Também define o tipo de abastecimento (produzido/distribuído), a margem de
2 produtos e o calendário de produção de todos (sincronizado: dias fora da
lista são removidos), para a Fase 4 (necessidade e ordem de produção).

Habilita cada produto em TODAS as lojas do negócio (produtos_lojas), para
que o operador de qualquer loja do seed veja o catálogo no app e para que
as fases de necessidade e distribuição tenham mais de uma loja com dados.

Idempotente: pode rodar quantas vezes quiser. Produto, habilitação,
classificação e calendário são procurados antes de serem criados (o banco
também impede habilitação duplicada: uq_produto_loja).

Como rodar:
    python scripts/seed_produtos.py
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models.calendario_producao import CalendarioProducao, DiaSemana
from app.models.loja import Loja
from app.models.negocio import Negocio
from app.models.nivel_classificacao import NivelClassificacao
from app.models.produto import CicloPrevisao, Produto, TipoAbastecimento, UnidadeMedida
from app.models.produto_classificacao import ProdutoClassificacao
from app.models.produto_loja import ProdutoLoja

# Exemplo de configuração de níveis deste negócio de teste: 2 níveis
# (Categoria -> Subcategoria). Outros negócios podem usar de 1 a 4 níveis,
# com nomes totalmente diferentes (ex.: "Departamento", "Setor", "Linha").
NIVEIS_TESTE = [
    {"ordem": 1, "nome": "Categoria"},
    {"ordem": 2, "nome": "Subcategoria"},
]

PRODUTOS_TESTE = [
    # Produtos em UN — produzidos na central (tipo_abastecimento = produzido)
    {"nome": "Croissant",         "codigo": "INT-001", "codigo_barras": None,            "unidade_medida": UnidadeMedida.UN, "peso_medio_kg": None,     "categoria": "Panificados",  "subcategoria": "Folhados",  "tipo_abastecimento": TipoAbastecimento.PRODUZIDO, "dias_validade": 2,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Bolo de Chocolate", "codigo": "INT-002", "codigo_barras": "7891000100104", "unidade_medida": UnidadeMedida.UN, "peso_medio_kg": None,     "categoria": "Confeitaria",  "subcategoria": "Bolos",     "tipo_abastecimento": TipoAbastecimento.PRODUZIDO, "dias_validade": 3,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Rosca de Canela",   "codigo": "INT-003", "codigo_barras": None,            "unidade_medida": UnidadeMedida.UN, "peso_medio_kg": None,     "categoria": "Panificados",  "subcategoria": "Doces",     "tipo_abastecimento": TipoAbastecimento.PRODUZIDO, "dias_validade": 2,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Sonho",             "codigo": "INT-004", "codigo_barras": None,            "unidade_medida": UnidadeMedida.UN, "peso_medio_kg": None,     "categoria": "Confeitaria",  "subcategoria": "Doces",     "tipo_abastecimento": TipoAbastecimento.PRODUZIDO, "dias_validade": 1,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Torta de Frango",   "codigo": "INT-005", "codigo_barras": "7891000100109", "unidade_medida": UnidadeMedida.UN, "peso_medio_kg": None,     "categoria": "Salgados",     "subcategoria": "Tortas",    "tipo_abastecimento": TipoAbastecimento.PRODUZIDO, "dias_validade": 2,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Coxinha",           "codigo": "INT-006", "codigo_barras": None,            "unidade_medida": UnidadeMedida.UN, "peso_medio_kg": None,     "categoria": "Salgados",     "subcategoria": "Fritos",    "tipo_abastecimento": TipoAbastecimento.PRODUZIDO, "dias_validade": 1,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    # Produtos em KG — produzidos na central
    {"nome": "Pão Francês",  "codigo": "INT-007", "codigo_barras": "7891000100101", "unidade_medida": UnidadeMedida.KG, "peso_medio_kg": "0.0500", "categoria": "Panificados", "subcategoria": "Pães",  "tipo_abastecimento": TipoAbastecimento.PRODUZIDO, "dias_validade": 1,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Pão de Forma", "codigo": "INT-008", "codigo_barras": "7891000100102", "unidade_medida": UnidadeMedida.KG, "peso_medio_kg": "0.5000", "categoria": "Panificados", "subcategoria": "Pães",  "tipo_abastecimento": TipoAbastecimento.PRODUZIDO, "dias_validade": 5,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Baguete",      "codigo": "INT-009", "codigo_barras": "7891000100106", "unidade_medida": UnidadeMedida.KG, "peso_medio_kg": "0.2500", "categoria": "Panificados", "subcategoria": "Pães",  "tipo_abastecimento": TipoAbastecimento.PRODUZIDO, "dias_validade": 1,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Pão Integral", "codigo": "INT-010", "codigo_barras": "7891000100107", "unidade_medida": UnidadeMedida.KG, "peso_medio_kg": "0.4500", "categoria": "Panificados", "subcategoria": "Pães",  "tipo_abastecimento": TipoAbastecimento.PRODUZIDO, "dias_validade": 5,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    # Produto KG SEM peso médio: peso varia por peça, pesado na hora da
    # contagem (cenário 3 — ex.: bolo vendido por fatia). Não produzido
    # na central — apenas distribuído.
    {"nome": "Bolo de Chocolate (fatia)", "codigo": "INT-011", "codigo_barras": None, "unidade_medida": UnidadeMedida.KG, "peso_medio_kg": None, "categoria": "Confeitaria", "subcategoria": "Bolos", "tipo_abastecimento": TipoAbastecimento.DISTRIBUIDO,"dias_validade": None, "ciclo_previsao": CicloPrevisao.SEMANAL},
]

# Calendário de produção (Fase 4 / N2), mapeado pelo código interno. Casos
# para a necessidade: diário; seg/qua/sex (cobertura de 2 e 3 dias dentro da
# validade); cobertura maior que a validade (D36: Torta seg/qui com validade
# 2; Croissant no sábado, que cobre sáb–seg com validade 2); produto
# distribuído com dias de envio (D39). O seed SINCRONIZA o calendário destes
# produtos: tira os dias que não estão na lista (até 2026-10-15 o Pão Francês
# era seg/qua/sex).
_TODOS_OS_DIAS = list(DiaSemana)
_SEG_QUI = [DiaSemana.SEGUNDA, DiaSemana.QUINTA]
CALENDARIO_TESTE = {
    "INT-001": [DiaSemana.TERCA, DiaSemana.QUINTA, DiaSemana.SABADO],
    "INT-002": [DiaSemana.SEGUNDA, DiaSemana.QUARTA, DiaSemana.SEXTA],
    "INT-003": _TODOS_OS_DIAS,
    "INT-004": _TODOS_OS_DIAS,
    "INT-005": _SEG_QUI,
    "INT-006": _TODOS_OS_DIAS,
    "INT-007": _TODOS_OS_DIAS,
    "INT-008": _SEG_QUI,
    "INT-009": _TODOS_OS_DIAS,
    "INT-010": _SEG_QUI,
    "INT-011": [DiaSemana.TERCA, DiaSemana.SEXTA],
}

# Margem do produto (D34). Os demais ficam sem margem e usam o padrão (10%).
MARGEM_TESTE = {"INT-007": Decimal("15.00"), "INT-002": Decimal("5.00")}


def main():
    db = SessionLocal()
    try:
        negocio = db.query(Negocio).order_by(Negocio.id).first()
        if negocio is None:
            print("Nenhum negócio encontrado. Rode 'python scripts/seed_dev.py' primeiro.")
            return

        lojas = db.query(Loja).filter(Loja.negocio_id == negocio.id).order_by(Loja.id).all()
        if not lojas:
            print("Nenhuma loja encontrada. Rode 'python scripts/seed_dev.py' primeiro.")
            return

        # ---- Níveis de classificação (Categoria -> Subcategoria) ----
        niveis_por_nome: dict[str, NivelClassificacao] = {}
        for item in NIVEIS_TESTE:
            nivel = (
                db.query(NivelClassificacao)
                .filter(NivelClassificacao.negocio_id == negocio.id, NivelClassificacao.ordem == item["ordem"])
                .first()
            )
            if nivel is None:
                nivel = NivelClassificacao(negocio_id=negocio.id, ordem=item["ordem"], nome=item["nome"])
                db.add(nivel)
                db.flush()
            niveis_por_nome[item["nome"].lower()] = nivel

        nivel_categoria = niveis_por_nome["categoria"]
        nivel_subcategoria = niveis_por_nome["subcategoria"]

        criados = 0
        habilitados = {loja.id: 0 for loja in lojas}
        classificados = 0
        for item in PRODUTOS_TESTE:
            produto = (
                db.query(Produto)
                .filter(Produto.negocio_id == negocio.id, Produto.nome == item["nome"])
                .first()
            )
            if produto is None:
                produto = Produto(
                    negocio_id=negocio.id,
                    nome=item["nome"],
                    codigo=item["codigo"],
                    codigo_barras=item["codigo_barras"],
                    unidade_medida=item["unidade_medida"],
                    peso_medio_kg=item["peso_medio_kg"],
                    ativo=True,
                    tipo_abastecimento=item["tipo_abastecimento"],
                    dias_validade=item["dias_validade"],
                    margem_maxima_percentual=MARGEM_TESTE.get(item["codigo"]),
                    ciclo_previsao=item["ciclo_previsao"],
                )
                db.add(produto)
                db.flush()
                criados += 1
            else:
                # Atualiza campos nos produtos que já existem
                if produto.codigo != item["codigo"]:
                    produto.codigo = item["codigo"]
                produto.tipo_abastecimento = item["tipo_abastecimento"]
                produto.dias_validade = item["dias_validade"]
                produto.margem_maxima_percentual = MARGEM_TESTE.get(item["codigo"])
                produto.ciclo_previsao = item["ciclo_previsao"]

            for loja in lojas:
                hab = (
                    db.query(ProdutoLoja)
                    .filter(ProdutoLoja.produto_id == produto.id, ProdutoLoja.loja_id == loja.id)
                    .first()
                )
                if hab is None:
                    db.add(ProdutoLoja(produto_id=produto.id, loja_id=loja.id))
                    habilitados[loja.id] += 1

            # ---- Classificação (Categoria / Subcategoria) ----
            for nivel, valor in ((nivel_categoria, item["categoria"]), (nivel_subcategoria, item["subcategoria"])):
                classificacao = (
                    db.query(ProdutoClassificacao)
                    .filter(ProdutoClassificacao.produto_id == produto.id, ProdutoClassificacao.nivel_id == nivel.id)
                    .first()
                )
                if classificacao is None:
                    db.add(ProdutoClassificacao(produto_id=produto.id, nivel_id=nivel.id, valor=valor))
                    classificados += 1
                elif classificacao.valor != valor:
                    classificacao.valor = valor

        db.commit()

        # ---- Calendário de produção (sincronizado com CALENDARIO_TESTE) ----
        cal_criados = 0
        cal_removidos = 0
        for codigo, dias in CALENDARIO_TESTE.items():
            produto = (
                db.query(Produto)
                .filter(Produto.negocio_id == negocio.id, Produto.codigo == codigo)
                .first()
            )
            if produto is None:
                continue
            existentes = (
                db.query(CalendarioProducao)
                .filter(CalendarioProducao.negocio_id == negocio.id, CalendarioProducao.produto_id == produto.id)
                .all()
            )
            for registro in existentes:
                if registro.dia_semana not in dias:
                    db.delete(registro)
                    cal_removidos += 1
            dias_existentes = {registro.dia_semana for registro in existentes}
            for dia in dias:
                if dia not in dias_existentes:
                    db.add(CalendarioProducao(negocio_id=negocio.id, produto_id=produto.id, dia_semana=dia))
                    cal_criados += 1
        db.commit()

        print(f"{criados} produto(s) criado(s) no catálogo de '{negocio.nome}'.")
        for loja in lojas:
            print(f"{habilitados[loja.id]} habilitação(ões) criada(s) para '{loja.nome}' (id={loja.id}).")
        print(f"{classificados} classificação(ões) criada(s) (Categoria/Subcategoria).")
        print(f"{cal_criados} entrada(s) de calendário de produção criada(s), {cal_removidos} removida(s).")
        if (criados == 0 and sum(habilitados.values()) == 0 and classificados == 0
                and cal_criados == 0 and cal_removidos == 0):
            print("(Produtos já existiam — codigos internos e classificação atualizados se necessário.)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
