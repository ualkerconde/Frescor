"""
Testa os seeds da Fase 4 / N2: `seed_produtos.py` (tipo de abastecimento,
margem, calendário sincronizado) e `seed_demo_producao.py` (negócio de
demonstração com vendas, perdas e contagens de estoque; operadores do app
desde a Fase 5 / E2).

Rode os dois seeds antes (o teste confere o estado e roda os dois de novo).

Casos:
  M1  seed principal: calendário de cada produto INT-001..INT-011 como esperado
  M2  seed principal: margem 15% (INT-007), 5% (INT-002), os outros sem margem
  M3  seed principal: INT-011 distribuído, os outros produzidos
  M4  seed principal: o calendário é sincronizado (dia a mais é removido,
      dia que falta volta)
  D1  demo: central padaria, prazo 0, ativa; lojas P01 e P02 da central;
      gestor da central só com acesso web
  D2  demo: os 7 produtos com tipo, unidade, peso, validade, margem e calendário
  D3  demo: vendas de 56 dias por loja + produto (PRD-06: 14), até ontem,
      sem data futura, UN inteiro, P02 entre 50% e 70% da P01
  D4  demo: perda em todo dia de venda, UN inteira, perda do Pão Francês
      entre 6% e 12% da venda
  D5  demo: 13 contagens; P02 + PRD-03 sem linha; P02 + PRD-04 com contagem
      de 3 dias antes; as outras no fechamento de hoje (21h de São Paulo em
      UTC; a ordem de amanhã é gerada à noite, N9);
      KG = peças × peso médio; UN = peças; sobra ~15% da venda de ontem
  D6  demo: setores da central (D67) "Pães" (PRD-01, PRD-04), "Bolos e doces"
      (PRD-02, PRD-07), "Salgados" (PRD-03), nessa ordem; PRD-05 e PRD-06
      sem setor
  D7  demo (Fase 5 / E2): operadores operador.p01 e operador.p02, um por loja,
      só com acesso ao app, ativos, sem central; cada um entra no app
      (POST /auth/login, 200) e vê os 7 produtos da própria loja (GET /produtos)
  I1  rodar os dois seeds de novo não muda nada (contagens e somas iguais),
      e duas contagens alteradas antes voltam ao valor e à hora esperados:
      P01 + PRD-02 (quantidade e hora, como se fosse de outro dia) e
      P02 + PRD-04 (só a quantidade; a hora já era a esperada)
  I2  o seed principal continua com 11 produtos e as lojas 001 e 002

Saída ASCII ([OK]/[FALHA]), exit 1 se algo falhar. O M4 altera o
calendário do seed principal e o próprio seed o devolve ao esperado.

Uso: python scripts/test_seeds_fase4.py
"""

import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

PASTA_BACKEND = Path(__file__).resolve().parent.parent
sys.path.append(str(PASTA_BACKEND))

from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 13

NEGOCIO_PRINCIPAL = "Rede Padaria Teste"
NEGOCIO_DEMO = "Rede Demo Produção"
TODOS = "segunda,terca,quarta,quinta,sexta,sabado,domingo"
SEG_QUI = "segunda,quinta"
CALENDARIO_PRINCIPAL = {
    "INT-001": "terca,quinta,sabado", "INT-002": "segunda,quarta,sexta", "INT-003": TODOS,
    "INT-004": TODOS, "INT-005": SEG_QUI, "INT-006": TODOS, "INT-007": TODOS, "INT-008": SEG_QUI,
    "INT-009": TODOS, "INT-010": SEG_QUI, "INT-011": "terca,sexta",
}
# codigo: (unidade, peso, validade, margem, tipo, calendário)
PRODUTOS_DEMO = {
    "PRD-01": ("KG", Decimal("0.0500"), 1, None, "produzido", TODOS),
    "PRD-02": ("UN", None, 3, Decimal("5.00"), "produzido", "segunda,quarta,sexta"),
    "PRD-03": ("UN", None, 2, None, "produzido", SEG_QUI),
    "PRD-04": ("KG", Decimal("0.5000"), 5, None, "produzido", SEG_QUI),
    "PRD-05": ("UN", None, 30, None, "distribuido", "terca,sexta"),
    "PRD-06": ("UN", None, 2, None, "produzido", TODOS),
    "PRD-07": ("UN", None, 1, None, "produzido", None),
}

resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def rodar_seed(nome):
    proc = subprocess.run([sys.executable, str(PASTA_BACKEND / "scripts" / nome)],
                          cwd=PASTA_BACKEND, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"{nome} terminou com exit {proc.returncode}: {proc.stderr.strip()[-500:]}")


def utc_sem_fuso(dia, hora):
    """Hora de São Paulo (fuso padrão da loja, D44) -> UTC sem fuso."""
    return datetime.combine(dia, hora, tzinfo=ZoneInfo("America/Sao_Paulo")).astimezone(timezone.utc).replace(tzinfo=None)


def calendario(db, negocio):
    return dict(db.execute(text("""
        SELECT p.codigo, string_agg(c.dia_semana::text, ',' ORDER BY c.dia_semana)
        FROM produtos p JOIN negocios n ON n.id = p.negocio_id
        LEFT JOIN calendario_producao c ON c.produto_id = p.id AND c.negocio_id = p.negocio_id
        WHERE n.nome = :n GROUP BY p.codigo"""), {"n": negocio}).all())


def foto(db):
    """Contagens e somas dos dois negócios, para o teste de idempotência."""
    return db.execute(text("""
        SELECT n.nome,
          (SELECT count(*) FROM produtos p WHERE p.negocio_id = n.id),
          (SELECT count(*) FROM lojas l WHERE l.negocio_id = n.id),
          (SELECT count(*) FROM centrais_producao c WHERE c.negocio_id = n.id),
          (SELECT count(*) FROM usuarios u WHERE u.negocio_id = n.id),
          (SELECT count(*) FROM calendario_producao c WHERE c.negocio_id = n.id),
          (SELECT count(*) FROM produtos_lojas pl JOIN lojas l ON l.id = pl.loja_id WHERE l.negocio_id = n.id),
          (SELECT count(*) || '/' || coalesce(sum(quantidade), 0) FROM vendas_diarias v WHERE v.negocio_id = n.id),
          (SELECT count(*) || '/' || coalesce(sum(quantidade), 0) FROM perdas_diarias v WHERE v.negocio_id = n.id),
          (SELECT count(*) || '/' || coalesce(sum(estoque_atual_calculado), 0) || '/' ||
                  coalesce(string_agg(atualizado_em::text, ',' ORDER BY id), '')
             FROM estoque_atual e WHERE e.negocio_id = n.id),
          (SELECT string_agg(codigo || ':' || coalesce(margem_maxima_percentual::text, '-') || ':' ||
                             tipo_abastecimento::text, ',' ORDER BY codigo) FROM produtos p WHERE p.negocio_id = n.id)
        FROM negocios n WHERE n.nome IN (:a, :b) ORDER BY n.nome"""),
        {"a": NEGOCIO_PRINCIPAL, "b": NEGOCIO_DEMO}).all()


def casos_principal(db):
    cal = calendario(db, NEGOCIO_PRINCIPAL)
    diferentes = {c: cal.get(c) for c, esperado in CALENDARIO_PRINCIPAL.items() if cal.get(c) != esperado}
    registrar("M1 calendario do seed principal", not diferentes,
              "igual ao esperado" if not diferentes else f"diferentes: {diferentes}")

    linhas = db.execute(text("""
        SELECT p.codigo, p.margem_maxima_percentual, p.tipo_abastecimento::text FROM produtos p
        JOIN negocios n ON n.id = p.negocio_id WHERE n.nome = :n AND p.codigo LIKE 'INT-%'"""),
        {"n": NEGOCIO_PRINCIPAL}).all()
    margens = {c: m for c, m, _ in linhas if m is not None}
    registrar("M2 margens do seed principal",
              margens == {"INT-007": Decimal("15.00"), "INT-002": Decimal("5.00")} and len(linhas) == 11,
              f"com margem: {margens}; produtos INT: {len(linhas)}")
    distribuidos = sorted(c for c, _, t in linhas if t == "distribuido")
    registrar("M3 tipos do seed principal", distribuidos == ["INT-011"], f"distribuidos: {distribuidos}")


def caso_sincronizacao(db):
    db.execute(text("""
        INSERT INTO calendario_producao (negocio_id, produto_id, dia_semana)
        SELECT p.negocio_id, p.id, 'terca' FROM produtos p JOIN negocios n ON n.id = p.negocio_id
        WHERE n.nome = :n AND p.codigo = 'INT-005'"""), {"n": NEGOCIO_PRINCIPAL})
    db.execute(text("""
        DELETE FROM calendario_producao c USING produtos p, negocios n
        WHERE c.produto_id = p.id AND n.id = p.negocio_id AND n.nome = :n
          AND p.codigo = 'INT-007' AND c.dia_semana = 'domingo'"""), {"n": NEGOCIO_PRINCIPAL})
    db.commit()
    alterado = calendario(db, NEGOCIO_PRINCIPAL)
    rodar_seed("seed_produtos.py")
    db.expire_all()
    depois = calendario(db, NEGOCIO_PRINCIPAL)
    ok = (alterado["INT-005"] == "segunda,terca,quinta" and depois["INT-005"] == SEG_QUI
          and depois["INT-007"] == TODOS)
    registrar("M4 calendario sincronizado", ok,
              f"INT-005 {alterado['INT-005']} -> {depois['INT-005']}; INT-007 volta a {depois['INT-007'][-7:]}")


def caso_setores(db):
    setores = db.execute(text("""
        SELECT s.nome, s.ordem, s.ativo, s.central_producao_id = c.id,
               coalesce(string_agg(p.codigo, ',' ORDER BY p.codigo), '')
        FROM setores_producao s JOIN negocios n ON n.id = s.negocio_id
        JOIN centrais_producao c ON c.negocio_id = n.id
        LEFT JOIN produtos p ON p.setor_producao_id = s.id
        WHERE n.nome = :n GROUP BY s.nome, s.ordem, s.ativo, s.central_producao_id, c.id
        ORDER BY s.ordem"""), {"n": NEGOCIO_DEMO}).all()
    sem_setor = [c for (c,) in db.execute(text("""
        SELECT p.codigo FROM produtos p JOIN negocios n ON n.id = p.negocio_id
        WHERE n.nome = :n AND p.setor_producao_id IS NULL ORDER BY p.codigo"""), {"n": NEGOCIO_DEMO})]
    esperado = [("Pães", 1, True, True, "PRD-01,PRD-04"), ("Bolos e doces", 2, True, True, "PRD-02,PRD-07"),
                ("Salgados", 3, True, True, "PRD-03")]
    ok = [tuple(s) for s in setores] == esperado and sem_setor == ["PRD-05", "PRD-06"]
    registrar("D6 setores da demo", ok, f"{[(s[0], s[4]) for s in setores]}; sem setor: {sem_setor}")


def caso_operadores(db):
    # Importado aqui: o TestClient só é preciso neste caso (sem "with", o
    # lifespan da API não roda e o agendador de zeragem não inicia).
    from fastapi.testclient import TestClient

    from app.main import app

    operadores = db.execute(text("""
        SELECT u.email, u.tipo_usuario::text, l.codigo, u.central_producao_id, u.tem_acesso_app, u.tem_acesso_web,
               u.status::text, n.nome
        FROM usuarios u LEFT JOIN lojas l ON l.id = u.loja_id JOIN negocios n ON n.id = u.negocio_id
        WHERE u.email IN ('operador.p01@teste.com', 'operador.p02@teste.com') ORDER BY u.email""")).all()
    esperado = [("operador.p01@teste.com", "operador_loja", "P01", None, True, False, "ativo", NEGOCIO_DEMO),
                ("operador.p02@teste.com", "operador_loja", "P02", None, True, False, "ativo", NEGOCIO_DEMO)]
    perfis_ok = [tuple(o) for o in operadores] == esperado

    cliente = TestClient(app)
    acessos = []
    for email in ("operador.p01@teste.com", "operador.p02@teste.com"):
        r = cliente.post("/auth/login", json={"email": email, "senha": "senha123"})
        if r.status_code != 200:
            acessos.append((email, f"login {r.status_code}"))
            continue
        produtos = cliente.get("/produtos", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
        codigos = sorted(p.get("codigo") for p in produtos.json()) if produtos.status_code == 200 else []
        acessos.append((email, f"login 200, /produtos {produtos.status_code} com {len(codigos)}"))
        perfis_ok = perfis_ok and produtos.status_code == 200 and codigos == sorted(PRODUTOS_DEMO)
    registrar("D7 operadores da demo entram no app", perfis_ok,
              f"perfis={[(o[0].split('@')[0], o[2], o[4], o[5]) for o in operadores]}; {acessos}")


def casos_demo(db, ontem):
    central = db.execute(text("""
        SELECT c.id, c.secao::text, c.prazo_entrega_dias, c.ativa FROM centrais_producao c
        JOIN negocios n ON n.id = c.negocio_id WHERE n.nome = :n"""), {"n": NEGOCIO_DEMO}).all()
    lojas = db.execute(text("""
        SELECT l.codigo, l.central_producao_id, l.ativo FROM lojas l
        JOIN negocios n ON n.id = l.negocio_id WHERE n.nome = :n ORDER BY l.codigo"""), {"n": NEGOCIO_DEMO}).all()
    gestor = db.execute(text("""
        SELECT tipo_usuario::text, central_producao_id, loja_id, tem_acesso_web, tem_acesso_app
        FROM usuarios WHERE email = 'gestor.producao@teste.com'""")).all()
    ok = (len(central) == 1 and tuple(central[0][1:]) == ("padaria", 0, True)
          and [(c, cid, a) for c, cid, a in lojas] == [("P01", central[0][0], True), ("P02", central[0][0], True)]
          and len(gestor) == 1 and tuple(gestor[0]) == ("gestor_central", central[0][0], None, True, False))
    registrar("D1 central, lojas e gestor da demo", ok,
              f"central={[tuple(c[1:]) for c in central]} lojas={[l[0] for l in lojas]} gestor={gestor}")

    linhas = db.execute(text("""
        SELECT p.codigo, p.unidade_medida::text, p.peso_medio_kg, p.dias_validade, p.margem_maxima_percentual,
               p.tipo_abastecimento::text FROM produtos p JOIN negocios n ON n.id = p.negocio_id
        WHERE n.nome = :n"""), {"n": NEGOCIO_DEMO}).all()
    cal = calendario(db, NEGOCIO_DEMO)
    obtido = {c: (u, peso, val, m, t, cal.get(c)) for c, u, peso, val, m, t in linhas}
    diferentes = {c: obtido.get(c) for c, esp in PRODUTOS_DEMO.items() if obtido.get(c) != esp}
    registrar("D2 produtos da demo", not diferentes and len(obtido) == 7,
              f"{len(obtido)} produtos" + (f"; diferentes: {diferentes}" if diferentes else ", todos como esperado"))

    por_par = db.execute(text("""
        SELECT l.codigo, p.codigo, p.unidade_medida::text, count(*), min(v.data), max(v.data), sum(v.quantidade),
               bool_and(p.unidade_medida::text <> 'UN' OR v.quantidade = trunc(v.quantidade))
        FROM vendas_diarias v JOIN lojas l ON l.id = v.loja_id JOIN produtos p ON p.id = v.produto_id
        JOIN negocios n ON n.id = v.negocio_id WHERE n.nome = :n GROUP BY 1, 2, 3"""), {"n": NEGOCIO_DEMO}).all()
    erros = []
    soma = {}
    for loja, prod, _u, qtd, inicio, fim, total, inteiro in por_par:
        dias_esperados = 14 if prod == "PRD-06" else 56
        if qtd != dias_esperados or fim != ontem or inicio != ontem - timedelta(days=dias_esperados - 1) or not inteiro:
            erros.append((loja, prod, qtd, str(inicio), str(fim), inteiro))
        soma.setdefault(prod, {})[loja] = total
    razoes = {p: float(s["P02"] / s["P01"]) for p, s in soma.items() if "P01" in s and "P02" in s}
    fora = {p: round(r, 3) for p, r in razoes.items() if not 0.5 <= r <= 0.7}
    registrar("D3 vendas da demo", len(por_par) == 14 and not erros and not fora,
              f"{len(por_par)} pares; P02/P01 de {min(razoes.values()):.2f} a {max(razoes.values()):.2f}"
              + (f"; erros: {erros}" if erros else "") + (f"; razao fora: {fora}" if fora else ""))

    perdas = db.execute(text("""
        SELECT count(*) FILTER (WHERE pe.id IS NULL),
               count(*) FILTER (WHERE p.unidade_medida::text = 'UN' AND pe.quantidade <> trunc(pe.quantidade)),
               sum(pe.quantidade) FILTER (WHERE p.codigo = 'PRD-01') / sum(v.quantidade) FILTER (WHERE p.codigo = 'PRD-01')
        FROM vendas_diarias v JOIN produtos p ON p.id = v.produto_id JOIN negocios n ON n.id = v.negocio_id
        LEFT JOIN perdas_diarias pe ON pe.loja_id = v.loja_id AND pe.produto_id = v.produto_id
             AND pe.data = v.data AND pe.origem::text = 'manual'
        WHERE n.nome = :n"""), {"n": NEGOCIO_DEMO}).one()
    sem_perda, perda_fracionada, taxa_pao = perdas
    registrar("D4 perdas da demo", sem_perda == 0 and perda_fracionada == 0 and 0.06 <= float(taxa_pao) <= 0.12,
              f"dias sem perda {sem_perda}; UN fracionada {perda_fracionada}; Pao Frances {float(taxa_pao):.1%}")

    estoque = db.execute(text("""
        SELECT l.codigo, p.codigo, p.peso_medio_kg, e.quantidade_inventariada, e.estoque_atual_calculado,
               e.atualizado_em, v.quantidade
        FROM estoque_atual e JOIN lojas l ON l.id = e.loja_id JOIN produtos p ON p.id = e.produto_id
        JOIN negocios n ON n.id = e.negocio_id
        LEFT JOIN vendas_diarias v ON v.loja_id = e.loja_id AND v.produto_id = e.produto_id AND v.data = :ontem
        WHERE n.nome = :n"""), {"n": NEGOCIO_DEMO, "ontem": ontem}).all()
    hoje = ontem + timedelta(days=1)
    hora_ontem = utc_sem_fuso(hoje, time(21, 0))  # fechamento de hoje (seed desde 2026-10-15, N9)
    hora_antiga = utc_sem_fuso(hoje - timedelta(days=3), time(21, 0))
    erros = []
    pares = set()
    for loja, prod, peso, pecas, calculado, quando, venda_ontem in estoque:
        pares.add((loja, prod))
        esperado_quando = hora_antiga if (loja, prod) == ("P02", "PRD-04") else hora_ontem
        esperado_calc = Decimal(pecas) * peso if peso else Decimal(pecas)
        sobra_em_pecas = float(venda_ontem) * 0.15 / (float(peso) if peso else 1)
        if quando != esperado_quando or calculado != esperado_calc or abs(pecas - sobra_em_pecas) > 0.5:
            erros.append((loja, prod, pecas, str(calculado), str(quando)))
    ok = len(estoque) == 13 and ("P02", "PRD-03") not in pares and not erros
    registrar("D5 contagens de estoque da demo", ok,
              f"{len(estoque)} contagens; P02/PRD-03 {'ausente' if ('P02', 'PRD-03') not in pares else 'PRESENTE'}; "
              f"fechamento de hoje = {hora_ontem} UTC" + (f"; erros: {erros}" if erros else ""))


def main():
    db = SessionLocal()
    try:
        ontem = date.today() - timedelta(days=1)
        casos_principal(db)
        caso_sincronizacao(db)
        casos_demo(db, ontem)
        caso_setores(db)
        caso_operadores(db)

        antes = foto(db)
        # Altera uma contagem (como se fosse de outro dia) para obrigar o seed a
        # regravá-la: sem isso, valores iguais não geram UPDATE e um seed que
        # esquece a hora da contagem (onupdate = "agora") passaria no mesmo dia.
        db.execute(text("""
            UPDATE estoque_atual e SET quantidade_inventariada = e.quantidade_inventariada + 5,
                   estoque_atual_calculado = e.estoque_atual_calculado + 5,
                   atualizado_em = e.atualizado_em - interval '10 days'
            FROM lojas l, produtos p, negocios n
            WHERE l.id = e.loja_id AND p.id = e.produto_id AND n.id = e.negocio_id
              AND n.nome = :n AND l.codigo = 'P01' AND p.codigo = 'PRD-02'"""), {"n": NEGOCIO_DEMO})
        # Só a quantidade muda (a hora continua a esperada): o seed tem de
        # mandar a hora no UPDATE mesmo assim (atribuir o mesmo valor não basta).
        db.execute(text("""
            UPDATE estoque_atual e SET quantidade_inventariada = e.quantidade_inventariada + 5,
                   estoque_atual_calculado = e.estoque_atual_calculado + 5
            FROM lojas l, produtos p, negocios n
            WHERE l.id = e.loja_id AND p.id = e.produto_id AND n.id = e.negocio_id
              AND n.nome = :n AND l.codigo = 'P02' AND p.codigo = 'PRD-04'"""), {"n": NEGOCIO_DEMO})
        db.commit()
        rodar_seed("seed_produtos.py")
        rodar_seed("seed_demo_producao.py")
        db.expire_all()
        depois = foto(db)
        db.commit()
        diferencas = [(a[0], b) for a, b in zip(antes, depois) if a != b]
        registrar("I1 seeds rodados de novo nao mudam nada", len(antes) == 2 and not diferencas,
                  "contagens e somas iguais nos 2 negocios" if not diferencas else f"mudou: {diferencas}")

        principal = db.execute(text("""
            SELECT (SELECT count(*) FROM produtos p WHERE p.negocio_id = n.id),
                   (SELECT string_agg(codigo, ',' ORDER BY codigo) FROM lojas l WHERE l.negocio_id = n.id)
            FROM negocios n WHERE n.nome = :n"""), {"n": NEGOCIO_PRINCIPAL}).one()
        registrar("I2 seed principal intacto", tuple(principal) == (11, "001,002"),
                  f"produtos={principal[0]} lojas={principal[1]}")
    except Exception as e:
        db.rollback()
        registrar("ERRO INESPERADO", False, f"{type(e).__name__}: {e}")
    finally:
        db.close()

    print("\n=== Resultado do teste dos seeds da Fase 4 (N2) ===")
    for r in resultados:
        print(r)
    falhas = [r for r in resultados if r.startswith(FAIL)]
    if len(resultados) < TOTAL_CASOS:
        print(f"\nTESTE INCOMPLETO: só {len(resultados)} de {TOTAL_CASOS} casos rodaram")
    else:
        print(f"\n{'TODOS OS CASOS PASSARAM' if not falhas else f'{len(falhas)} CASO(S) FALHARAM'}")
    if len(resultados) < TOTAL_CASOS or falhas:
        sys.exit(1)


if __name__ == "__main__":
    main()
