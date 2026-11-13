"""
Configura a integração de vendas de um negócio (D108). Roda na implantação,
por quem administra o servidor; o gestor não vê chave nem credencial.

Modo envio (o sistema do cliente manda as vendas):
    python scripts/configurar_integracao_vendas.py --negocio-id 3 --modo envio --sistema "TOTVS" --nova-chave
  -> mostra a chave UMA vez. Entregue ao responsável pelo sistema do cliente,
     com o endereço POST https://<servidor>/integracao/vendas e o cabeçalho
     X-Chave-Frescor. Rodar de novo com --nova-chave troca a chave (a velha
     para de valer na hora).

Modo busca (o Frescor busca de madrugada):
    python scripts/configurar_integracao_vendas.py --negocio-id 3 --modo busca \
        --url https://erp.cliente.com.br/frescor/vendas --variavel FRESCOR_VENDAS_TOKEN_3 \
        --horario 05:00 --dias-rebusca 3
  -> a credencial fica na variável de ambiente do servidor (no .env), nunca
     no banco. Teste com --testar (busca ontem e mostra o resultado).

Outras opções: --desativar, --ativar, --mostrar.
"""

import argparse
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.execucao_sync_vendas import OrigemExecucaoSync  # noqa: E402
from app.models.integracao_vendas import IntegracaoVendas, ModoIntegracaoVendas  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.services import sync_vendas_service as svc  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Configura a integração de vendas de um negócio (D108).")
    ap.add_argument("--negocio-id", type=int, required=True)
    ap.add_argument("--modo", choices=["envio", "busca"])
    ap.add_argument("--sistema", help="Nome do sistema do cliente, só para mostrar (ex.: TOTVS).")
    ap.add_argument("--url", help="Endereço de busca (modo busca).")
    ap.add_argument("--variavel", help="Nome da variável de ambiente com a credencial (modo busca).")
    ap.add_argument("--horario", help="Hora da busca diária, HH:MM, hora de Brasília (padrão 05:00).")
    ap.add_argument("--dias-rebusca", type=int, help="Dias anteriores a ontem que são buscados de novo (0 a 14).")
    ap.add_argument("--nova-chave", action="store_true", help="Gera (ou troca) a chave do modo envio.")
    ap.add_argument("--desativar", action="store_true")
    ap.add_argument("--ativar", action="store_true")
    ap.add_argument("--testar", action="store_true", help="Modo busca: busca ontem agora e mostra o resultado.")
    ap.add_argument("--mostrar", action="store_true")
    a = ap.parse_args()

    db = SessionLocal()
    try:
        negocio = db.get(Negocio, a.negocio_id)
        if negocio is None:
            sys.exit(f"Negócio {a.negocio_id} não existe.")
        integ = db.query(IntegracaoVendas).filter(IntegracaoVendas.negocio_id == negocio.id).first()
        if integ is None:
            if not a.modo:
                sys.exit("Este negócio ainda não tem integração: informe --modo envio ou --modo busca.")
            integ = IntegracaoVendas(negocio_id=negocio.id, modo=ModoIntegracaoVendas(a.modo))
            db.add(integ)
        elif a.modo:
            integ.modo = ModoIntegracaoVendas(a.modo)

        chave = None
        if a.sistema is not None:
            integ.sistema = a.sistema or None
        if a.url is not None:
            integ.url_busca = a.url or None
        if a.variavel is not None:
            integ.variavel_credencial = a.variavel or None
        if a.horario:
            integ.horario_busca = time.fromisoformat(a.horario)
        if a.dias_rebusca is not None:
            if not 0 <= a.dias_rebusca <= 14:
                sys.exit("--dias-rebusca vai de 0 a 14.")
            integ.dias_rebusca = a.dias_rebusca
        if a.nova_chave or (integ.modo == ModoIntegracaoVendas.ENVIO and not integ.chave_hash):
            chave, integ.chave_hash, integ.chave_prefixo = svc.gerar_chave()
        if a.desativar:
            integ.ativa = False
        if a.ativar:
            integ.ativa = True
        if integ.modo == ModoIntegracaoVendas.BUSCA and not integ.url_busca:
            sys.exit("O modo busca precisa de --url.")
        integ.atualizado_em = datetime.utcnow()
        db.commit()

        print(f"Negócio {negocio.id} ({negocio.nome}): integração de vendas no modo {integ.modo.value}, "
              f"{'ativa' if integ.ativa else 'DESATIVADA'}.")
        if integ.modo == ModoIntegracaoVendas.BUSCA:
            print(f"  Busca em {integ.url_busca} às {integ.horario_busca:%H:%M} (Brasília), "
                  f"ontem + {integ.dias_rebusca} dia(s) antes; credencial na variável "
                  f"{integ.variavel_credencial or '(nenhuma)'}.")
        else:
            print(f"  Chave atual começa com {integ.chave_prefixo}…")
        if chave:
            print("\n  CHAVE NOVA (aparece só agora; guarde e entregue ao responsável pelo sistema do cliente):")
            print(f"  {chave}\n")
            print("  Envio: POST /integracao/vendas, cabeçalho X-Chave-Frescor: <chave>,")
            print('  corpo {"vendas": [{"data": "AAAA-MM-DD", "loja": "001", "produto": "123", "quantidade": "12.5"}]}')
        if a.testar:
            if integ.modo != ModoIntegracaoVendas.BUSCA:
                sys.exit("--testar só vale no modo busca.")
            ontem = svc.hoje_local() - timedelta(days=1)
            ex = svc.buscar(db, negocio.id, ontem, ontem, OrigemExecucaoSync.MANUAL)
            print(f"\n  Teste: {ex.situacao.value}; recebidas {ex.linhas_recebidas}, gravadas {ex.linhas_gravadas}, "
                  f"pendentes {ex.linhas_pendentes}, inválidas {ex.linhas_invalidas}. {ex.mensagem or ''}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
