"""
Testa a integração de vendas (D108): envio do sistema do cliente
(POST /integracao/vendas), busca (serviço, com buscador falso), job
agendado, tela do gestor e casamento de pendências.

Cenário: negócio A (modo envio), central A1 com lojas 001 e 002; produtos
PA (UN), PB (KG, código no PDV "PDV-PB") e PC (UN, sem código no PDV).
Negócio B (loja B1, sem integração). Negócio C (modo busca, loja C1,
produto CA).

Casos:
  E1 sem chave / chave errada -> 401
  E2 envio válido: 001/PA 5 + 3 (somam 8), 001/PDV-PB 1,25 kg -> 2 gravadas, sucesso
  E3 pendências: produto XYZ na 001 e loja 999 -> 2 pendentes, parcial, nada gravado delas
  E4 inválidas não travam o resto: data futura, fração em UN, negativa, data malformada
  E5 reenvio substitui (não soma): 001/PA = 10
  E6 código de loja de outro negócio (B1) vira pendência de A; nada grava em B
  E7 corpo sem lista -> 422; modo busca recusa envio -> 409
  W1 tela do gestor: modo envio, prefixo da chave, execuções, pendências agrupadas
  W2 gestor de B: sem integração e sem as pendências de A
  W3 casar XYZ -> PC: grava a venda pendente na hora e a pendência some
  W4 casar inválido: código já de outro produto, sem pendência, produto de outro negócio -> 422
  W5 "Buscar agora" no modo envio -> 409
  W6 cadastro do produto: código no PDV único no negócio; vazio volta a usar o código
  B1 busca com buscador falso: grava o período, linha fora do período é inválida
  B2 busca que falha (erro de rede) vira execução "falhou" com a mensagem
  B3 credencial configurada mas ausente no servidor -> falhou, sem chamar o buscador
  J1 job: antes do horário não busca; depois busca ontem + dias de rebusca; 2ª vez no dia não busca

Saída ASCII ([OK]/[FALHA]), limpeza no início e no fim, exit 1 se falhar.

Uso: python scripts/test_integracao_vendas.py
"""

import sys
import uuid
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import PORTA_WEB, criar_access_token, hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.central_producao import CentralProducao  # noqa: E402
from app.models.execucao_sync_vendas import ExecucaoSyncVendas, OrigemExecucaoSync  # noqa: E402
from app.models.integracao_vendas import IntegracaoVendas, ModoIntegracaoVendas  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.pendencia_sync_vendas import PendenciaSyncVendas  # noqa: E402
from app.models.produto import Produto, TipoAbastecimento, UnidadeMedida  # noqa: E402
from app.models.usuario import TipoUsuario, Usuario  # noqa: E402
from app.models.venda_diaria import OrigemVenda, VendaDiaria  # noqa: E402
from app.services import sync_vendas_service as svc  # noqa: E402

PASS = "[OK]"
FAIL = "[FALHA]"
TOTAL_CASOS = 18
PREFIXO_NEGOCIO_TESTE = "_Teste Integracao Vendas"
DEC = Decimal
HOJE = svc.hoje_local()
D1 = HOJE - timedelta(days=1)

cliente = TestClient(app, raise_server_exceptions=False)
resultados = []


def registrar(nome, ok, detalhe):
    resultados.append(f"{PASS if ok else FAIL} {nome}: {detalhe}")


def corpo(r):
    try:
        return r.json()
    except ValueError:
        return r.text


def _limpar(db, negocio_ids):
    if not negocio_ids:
        return
    for modelo in (PendenciaSyncVendas, ExecucaoSyncVendas, IntegracaoVendas, VendaDiaria, Usuario, Produto, Loja,
                   CentralProducao):
        db.query(modelo).filter(modelo.negocio_id.in_(negocio_ids)).delete(synchronize_session=False)
    db.query(Negocio).filter(Negocio.id.in_(negocio_ids)).delete(synchronize_session=False)
    db.commit()


def _limpar_residuos():
    db = SessionLocal()
    try:
        negocios = [x for x in db.query(Negocio).all() if x.nome.startswith(PREFIXO_NEGOCIO_TESTE + " ")]
        if not negocios:
            print("[limpeza inicial] Nenhum resíduo de teste encontrado.")
            return
        print(f"[limpeza inicial] Apagando {len(negocios)} negócio(s) de execuções anteriores.")
        _limpar(db, [x.id for x in negocios])
    finally:
        db.close()


def main():
    _limpar_residuos()
    db = SessionLocal()
    negocio_ids = []
    try:
        run = uuid.uuid4().hex[:8]

        def add(obj):
            db.add(obj)
            db.flush()
            return obj

        neg = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} A", ativo=True))
        neg_b = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} B", ativo=True))
        neg_c = add(Negocio(nome=f"{PREFIXO_NEGOCIO_TESTE} {run} C", ativo=True))
        negocio_ids = [neg.id, neg_b.id, neg_c.id]
        a1 = add(CentralProducao(negocio_id=neg.id, nome="_A1", ativa=True))
        cb = add(CentralProducao(negocio_id=neg_b.id, nome="_B", ativa=True))
        cc = add(CentralProducao(negocio_id=neg_c.id, nome="_C", ativa=True))

        def loja(codigo, ng, central):
            return add(Loja(negocio_id=ng.id, central_producao_id=central.id, nome=f"_Loja {codigo}", codigo=codigo,
                            horario_zeragem=time(6, 0), ativo=True))

        l1, l2, lb, lc = loja("001", neg, a1), loja("002", neg, a1), loja("B1", neg_b, cb), loja("C1", neg_c, cc)

        def gestor(rotulo, ng, central):
            return add(Usuario(negocio_id=ng.id, nome=f"_G {rotulo}", email=f"tiv_{rotulo}_{run}@teste.com",
                               senha_hash=hash_senha("x"), tipo_usuario=TipoUsuario.GESTOR_CENTRAL,
                               central_producao_id=central.id, tem_acesso_app=False, tem_acesso_web=True))

        g, gb, gc = gestor("a", neg, a1), gestor("b", neg_b, cb), gestor("c", neg_c, cc)

        def produto(ng, codigo, unidade, pdv=None):
            return add(Produto(negocio_id=ng.id, nome=f"_Produto {codigo}", codigo=codigo, codigo_pdv=pdv,
                               unidade_medida=unidade, ativo=True, tipo_abastecimento=TipoAbastecimento.PRODUZIDO))

        pa, pb, pc = produto(neg, "PA", UnidadeMedida.UN), produto(neg, "PB", UnidadeMedida.KG, "PDV-PB"), \
            produto(neg, "PC", UnidadeMedida.UN)
        pz = produto(neg_b, "PZ", UnidadeMedida.UN)
        ca = produto(neg_c, "CA", UnidadeMedida.UN)
        chave, chave_hash, prefixo = svc.gerar_chave()
        add(IntegracaoVendas(negocio_id=neg.id, modo=ModoIntegracaoVendas.ENVIO, chave_hash=chave_hash,
                             chave_prefixo=prefixo, sistema="Teste"))
        chave_c, hash_c, prefixo_c = svc.gerar_chave()
        integ_c = add(IntegracaoVendas(negocio_id=neg_c.id, modo=ModoIntegracaoVendas.BUSCA, url_busca="http://x",
                                       horario_busca=time(5, 0), dias_rebusca=2, chave_hash=hash_c,
                                       chave_prefixo=prefixo_c))
        db.commit()

        tg, tgb = (criar_access_token(u.id, u.negocio_id, porta=PORTA_WEB) for u in (g, gb))

        def enviar(vendas, k=chave):
            return cliente.post("/integracao/vendas", json={"vendas": vendas},
                                headers={"X-Chave-Frescor": k} if k else {})

        def venda(lj, p, dia=D1):
            db.expire_all()
            v = db.query(VendaDiaria).filter(VendaDiaria.loja_id == lj.id, VendaDiaria.produto_id == p.id,
                                             VendaDiaria.data == dia, VendaDiaria.origem == OrigemVenda.API).first()
            return None if v is None else v.quantidade.normalize()

        def l(dia, lj, pr, q):
            return {"data": str(dia), "loja": lj, "produto": pr, "quantidade": q}

        # ---- E ----
        s = (enviar([l(D1, "001", "PA", 1)], None).status_code, enviar([l(D1, "001", "PA", 1)], "frv_errada").status_code)
        registrar("E1 sem chave / chave errada -> 401", s == (401, 401) and venda(l1, pa) is None, f"{s}")

        r = enviar([l(D1, "001", "PA", 5), l(D1, "001", "PA", "3"), l(D1, "001", "PDV-PB", "1.25")])
        b = corpo(r)
        registrar("E2 envio valido soma repetidas e casa pelo codigo no PDV",
                  r.status_code == 200 and b["linhas_gravadas"] == 2 and b["situacao"] == "sucesso"
                  and venda(l1, pa) == 8 and venda(l1, pb) == DEC("1.25"), f"{r.status_code} {b} PA={venda(l1, pa)}")

        r = enviar([l(D1, "001", "XYZ", 4), l(D1, "999", "PA", 2)])
        b = corpo(r)
        db.expire_all()
        pend = {(p.codigo_loja, p.codigo_produto, p.motivo.value)
                for p in db.query(PendenciaSyncVendas).filter(PendenciaSyncVendas.negocio_id == neg.id)}
        registrar("E3 pendencias", r.status_code == 200 and b["linhas_pendentes"] == 2 and b["situacao"] == "parcial"
                  and pend == {("001", "XYZ", "produto_desconhecido"), ("999", "PA", "loja_desconhecida")},
                  f"{b.get('linhas_pendentes')} {pend}")

        r = enviar([l(HOJE + timedelta(days=1), "002", "PA", 1), l(D1, "002", "PA", "1.5"), l(D1, "002", "PA", -2),
                    {"data": "10/11/2026", "loja": "002", "produto": "PA", "quantidade": 1}, l(D1, "002", "PC", 7)])
        b = corpo(r)
        registrar("E4 invalidas nao travam o resto",
                  r.status_code == 200 and b["linhas_invalidas"] == 4 and b["linhas_gravadas"] == 1
                  and venda(l2, pc) == 7 and venda(l2, pa) is None and "data futura" in (b["mensagem"] or ""),
                  f"{b.get('linhas_invalidas')} {b.get('linhas_gravadas')} {b.get('mensagem')}")

        r = enviar([l(D1, "001", "PA", 10)])
        registrar("E5 reenvio substitui", venda(l1, pa) == 10, f"PA={venda(l1, pa)}")

        r = enviar([l(D1, "B1", "PA", 3)])
        db.expire_all()
        em_b = db.query(VendaDiaria).filter(VendaDiaria.negocio_id == neg_b.id).count()
        registrar("E6 loja de outro negocio vira pendencia, nada em B",
                  corpo(r).get("linhas_pendentes") == 1 and em_b == 0, f"{corpo(r).get('linhas_pendentes')} em_b={em_b}")

        s1 = cliente.post("/integracao/vendas", json={"vendas": "x"}, headers={"X-Chave-Frescor": chave}).status_code
        s2 = enviar([l(D1, "C1", "CA", 1)], chave_c).status_code
        registrar("E7 corpo sem lista 422; modo busca recusa envio 409", (s1, s2) == (422, 409), f"{s1} {s2}")

        # ---- W ----
        r = cliente.get("/web/integracao/vendas", headers={"Authorization": f"Bearer {tg}"})
        b = corpo(r)
        pend_w = {(p["motivo"], p["codigo"], tuple(p["lojas"]), p["linhas"]) for p in b.get("pendencias", [])}
        registrar("W1 tela do gestor",
                  r.status_code == 200 and b["modo"] == "envio" and b["chave_prefixo"] == prefixo
                  and len(b["execucoes"]) == 5 and ("produto_desconhecido", "XYZ", ("001",), 1) in pend_w
                  and ("loja_desconhecida", "999", ("999",), 1) in pend_w and "B1" in {p[1] for p in pend_w},
                  f"{r.status_code} execucoes={len(b.get('execucoes', []))} {pend_w}")
        r = cliente.get("/web/integracao/vendas", headers={"Authorization": f"Bearer {tgb}"})
        registrar("W2 gestor de B nao ve A", corpo(r) == {**corpo(r), "configurada": False, "pendencias": []},
                  f"{corpo(r)}")

        def casar(codigo, pid, token=tg):
            return cliente.post("/web/integracao/vendas/pendencias/casar", json={"codigo_produto": codigo,
                                                                                 "produto_id": pid},
                                headers={"Authorization": f"Bearer {token}"})

        r = casar("XYZ", pc.id)
        db.expire_all()
        restou = db.query(PendenciaSyncVendas).filter(PendenciaSyncVendas.negocio_id == neg.id,
                                                      PendenciaSyncVendas.codigo_produto == "XYZ").count()
        registrar("W3 casar XYZ -> PC grava na hora", r.status_code == 200 and corpo(r)["gravadas"] == 1
                  and venda(l1, pc) == 4 and restou == 0 and db.get(Produto, pc.id).codigo_pdv == "XYZ",
                  f"{r.status_code} {corpo(r)} PC={venda(l1, pc)} restou={restou}")

        db.add(PendenciaSyncVendas(negocio_id=neg.id, motivo="produto_desconhecido", data=D1, codigo_loja="001",
                                   codigo_produto="NOVO", quantidade=DEC(1)))
        db.commit()
        s = (casar("PDV-PB", pa.id).status_code, casar("SEM", pa.id).status_code, casar("NOVO", pz.id).status_code,
             casar("NOVO", pc.id).status_code)
        registrar("W4 casar invalido -> 422", s == (422, 422, 422, 422), f"{s}")

        def patch(pid, pdv):
            return cliente.patch(f"/web/produtos/{pid}", json={"codigo_pdv": pdv},
                                 headers={"Authorization": f"Bearer {tg}"})

        r1, r2, r3 = patch(pa.id, "PDV-PB"), patch(pa.id, "PDV-PA"), patch(pa.id, None)
        registrar("W6 cadastro: codigo no PDV unico no negocio; vazio volta ao codigo",
                  (r1.status_code, r2.status_code, r3.status_code) == (422, 200, 200)
                  and corpo(r2).get("codigo_pdv") == "PDV-PA" and corpo(r3).get("codigo_pdv") is None,
                  f"{r1.status_code} {r2.status_code} {r3.status_code} {corpo(r1).get('detail')}")

        r = cliente.post("/web/integracao/vendas/buscar", json={}, headers={"Authorization": f"Bearer {tg}"})
        registrar("W5 buscar agora no modo envio -> 409", r.status_code == 409, f"{r.status_code} {corpo(r)}")

        # ---- B ----
        pedidos = []

        def falso(url, cab, inicio, fim):
            pedidos.append((url, inicio, fim))
            return {"vendas": [l(D1, "C1", "CA", 6), l(D1 - timedelta(days=30), "C1", "CA", 1)]}

        ex = svc.buscar(db, neg_c.id, D1, D1, OrigemExecucaoSync.MANUAL, buscador=falso)
        registrar("B1 busca grava o periodo; fora do periodo e invalida",
                  ex.situacao.value == "parcial" and ex.linhas_gravadas == 1 and ex.linhas_invalidas == 1
                  and venda(lc, ca) == 6 and pedidos == [("http://x", D1, D1)], f"{ex.situacao} {ex.mensagem}")

        def quebra(*_):
            raise OSError("conexão recusada")

        ex = svc.buscar(db, neg_c.id, D1, D1, OrigemExecucaoSync.MANUAL, buscador=quebra)
        registrar("B2 falha de rede vira execucao falhou", ex.situacao.value == "falhou"
                  and "conexão recusada" in (ex.mensagem or ""), f"{ex.situacao} {ex.mensagem}")

        integ_c.variavel_credencial = f"FRESCOR_TESTE_INEXISTENTE_{run}"
        db.commit()
        chamado = []
        ex = svc.buscar(db, neg_c.id, D1, D1, OrigemExecucaoSync.MANUAL,
                        buscador=lambda *a: chamado.append(a) or [])
        registrar("B3 credencial ausente -> falhou sem chamar", ex.situacao.value == "falhou" and not chamado
                  and "credencial ausente" in (ex.mensagem or ""), f"{ex.mensagem}")
        integ_c.variavel_credencial = None
        db.commit()

        # ---- J ----
        fuso = ZoneInfo("America/Sao_Paulo")

        def utc(h, m):
            return datetime.combine(HOJE, time(h, m), fuso).astimezone(timezone.utc).replace(tzinfo=None)

        pedidos.clear()
        antes = [e for e in svc.executar_agendadas(db, utc(4, 50), buscador=falso) if e.negocio_id == neg_c.id]
        depois = [e for e in svc.executar_agendadas(db, utc(5, 10), buscador=falso) if e.negocio_id == neg_c.id]
        de_novo = [e for e in svc.executar_agendadas(db, utc(9, 0), buscador=falso) if e.negocio_id == neg_c.id]
        registrar("J1 job no horario, uma vez por dia, ontem + 2 dias",
                  not antes and len(depois) == 1 and not de_novo
                  and (depois[0].data_inicio, depois[0].data_fim) == (D1 - timedelta(days=2), D1),
                  f"antes={len(antes)} depois={[(e.data_inicio, e.data_fim) for e in depois]} de_novo={len(de_novo)}")
        registrar("J2 job nao busca negocio em modo envio",
                  all(e.negocio_id != neg.id for e in depois + de_novo), "ok")
    finally:
        try:
            _limpar(db, negocio_ids)
        finally:
            db.close()

    for linha in resultados:
        print(linha)
    falhas = [x for x in resultados if x.startswith(FAIL)]
    print()
    if len(resultados) != TOTAL_CASOS:
        print(f"ATENCAO: {len(resultados)} casos registrados, esperados {TOTAL_CASOS}.")
        sys.exit(1)
    if falhas:
        print(f"{len(falhas)}/{TOTAL_CASOS} casos FALHARAM")
        sys.exit(1)
    print(f"{TOTAL_CASOS}/{TOTAL_CASOS} casos OK")


if __name__ == "__main__":
    main()
