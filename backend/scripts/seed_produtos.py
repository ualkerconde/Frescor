"""
Script para criar produtos de teste com codigo, codigo_barras,
unidade de medida, peso médio e classificação (categoria/subcategoria).
Também cria registros de exemplo em `calendario_producao` para alguns
produtos com tem_producao_propria = True.

Como rodar:
    python scripts/seed_produtos.py
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models.calendario_producao import CalendarioProducao, DiaSemana
from app.models.loja import Loja
from app.models.negocio import Negocio
from app.models.nivel_classificacao import NivelClassificacao
from app.models.produto import CicloPrevisao, Produto, UnidadeMedida
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
    # Produtos em UN — produzidos na central (tem_producao_propria=True)
    {"nome": "Croissant",         "codigo": "INT-001", "codigo_barras": None,            "unidade_medida": UnidadeMedida.UN, "peso_medio_kg": None,     "categoria": "Panificados",  "subcategoria": "Folhados",  "tem_producao_propria": True,  "dias_validade": 2,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Bolo de Chocolate", "codigo": "INT-002", "codigo_barras": "7891000100104", "unidade_medida": UnidadeMedida.UN, "peso_medio_kg": None,     "categoria": "Confeitaria",  "subcategoria": "Bolos",     "tem_producao_propria": True,  "dias_validade": 3,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Rosca de Canela",   "codigo": "INT-003", "codigo_barras": None,            "unidade_medida": UnidadeMedida.UN, "peso_medio_kg": None,     "categoria": "Panificados",  "subcategoria": "Doces",     "tem_producao_propria": True,  "dias_validade": 2,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Sonho",             "codigo": "INT-004", "codigo_barras": None,            "unidade_medida": UnidadeMedida.UN, "peso_medio_kg": None,     "categoria": "Confeitaria",  "subcategoria": "Doces",     "tem_producao_propria": True,  "dias_validade": 1,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Torta de Frango",   "codigo": "INT-005", "codigo_barras": "7891000100109", "unidade_medida": UnidadeMedida.UN, "peso_medio_kg": None,     "categoria": "Salgados",     "subcategoria": "Tortas",    "tem_producao_propria": True,  "dias_validade": 2,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Coxinha",           "codigo": "INT-006", "codigo_barras": None,            "unidade_medida": UnidadeMedida.UN, "peso_medio_kg": None,     "categoria": "Salgados",     "subcategoria": "Fritos",    "tem_producao_propria": True,  "dias_validade": 1,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    # Produtos em KG — produzidos na central
    {"nome": "Pão Francês",  "codigo": "INT-007", "codigo_barras": "7891000100101", "unidade_medida": UnidadeMedida.KG, "peso_medio_kg": "0.0500", "categoria": "Panificados", "subcategoria": "Pães",  "tem_producao_propria": True,  "dias_validade": 1,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Pão de Forma", "codigo": "INT-008", "codigo_barras": "7891000100102", "unidade_medida": UnidadeMedida.KG, "peso_medio_kg": "0.5000", "categoria": "Panificados", "subcategoria": "Pães",  "tem_producao_propria": True,  "dias_validade": 5,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Baguete",      "codigo": "INT-009", "codigo_barras": "7891000100106", "unidade_medida": UnidadeMedida.KG, "peso_medio_kg": "0.2500", "categoria": "Panificados", "subcategoria": "Pães",  "tem_producao_propria": True,  "dias_validade": 1,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    {"nome": "Pão Integral", "codigo": "INT-010", "codigo_barras": "7891000100107", "unidade_medida": UnidadeMedida.KG, "peso_medio_kg": "0.4500", "categoria": "Panificados", "subcategoria": "Pães",  "tem_producao_propria": True,  "dias_validade": 5,  "ciclo_previsao": CicloPrevisao.SEMANAL},
    # Produto KG SEM peso médio: peso varia por peça, pesado na hora da
    # contagem (cenário 3 — ex.: bolo vendido por fatia). Não produzido
    # na central — apenas distribuído.
    {"nome": "Bolo de Chocolate (fatia)", "codigo": "INT-011", "codigo_barras": None, "unidade_medida": UnidadeMedida.KG, "peso_medio_kg": None, "categoria": "Confeitaria", "subcategoria": "Bolos", "tem_producao_propria": False, "dias_validade": None, "ciclo_previsao": CicloPrevisao.SEMANAL},
]

# Calendário de produção de exemplo: Pão Francês (segunda, quarta, sexta)
# e Croissant (terca, quinta, sabado). Mapeados pelo codigo interno.
CALENDARIO_TESTE = {
    "INT-007": [DiaSemana.SEGUNDA, DiaSemana.QUARTA, DiaSemana.SEXTA],
    "INT-001": [DiaSemana.TERCA, DiaSemana.QUINTA, DiaSemana.SABADO],
}


def main():
    db = SessionLocal()
    try:
        negocio = db.query(Negocio).order_by(Negocio.id).first()
        if negocio is None:
            print("Nenhum negócio encontrado. Rode 'python scripts/seed_dev.py' primeiro.")
            return

        loja = db.query(Loja).filter(Loja.negocio_id == negocio.id).order_by(Loja.id).first()
        if loja is None:
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
        habilitados = 0
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
                    tem_producao_propria=item["tem_producao_propria"],
                    dias_validade=item["dias_validade"],
                    ciclo_previsao=item["ciclo_previsao"],
                )
                db.add(produto)
                db.flush()
                criados += 1
            else:
                # Atualiza campos nos produtos que já existem
                if produto.codigo != item["codigo"]:
                    produto.codigo = item["codigo"]
                produto.tem_producao_propria = item["tem_producao_propria"]
                produto.dias_validade = item["dias_validade"]
                produto.ciclo_previsao = item["ciclo_previsao"]

            hab = (
                db.query(ProdutoLoja)
                .filter(ProdutoLoja.produto_id == produto.id, ProdutoLoja.loja_id == loja.id)
                .first()
            )
            if hab is None:
                db.add(ProdutoLoja(produto_id=produto.id, loja_id=loja.id))
                habilitados += 1

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

        # ---- Calendário de produção de exemplo ----
        cal_criados = 0
        for codigo, dias in CALENDARIO_TESTE.items():
            produto = (
                db.query(Produto)
                .filter(Produto.negocio_id == negocio.id, Produto.codigo == codigo)
                .first()
            )
            if produto is None:
                continue
            for dia in dias:
                existe = (
                    db.query(CalendarioProducao)
                    .filter(
                        CalendarioProducao.produto_id == produto.id,
                        CalendarioProducao.dia_semana == dia,
                    )
                    .first()
                )
                if existe is None:
                    db.add(CalendarioProducao(produto_id=produto.id, dia_semana=dia))
                    cal_criados += 1
        db.commit()

        print(f"{criados} produto(s) criado(s) no catálogo de '{negocio.nome}'.")
        print(f"{habilitados} habilitação(ões) criada(s) para '{loja.nome}'.")
        print(f"{classificados} classificação(ões) criada(s) (Categoria/Subcategoria).")
        print(f"{cal_criados} entrada(s) de calendário de produção criada(s).")
        if criados == 0 and habilitados == 0 and classificados == 0 and cal_criados == 0:
            print("(Produtos já existiam — codigos internos e classificação atualizados se necessário.)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
