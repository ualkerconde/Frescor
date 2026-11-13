"""
Implantação de um cliente novo: cria negócio, centrais, lojas e usuários a
partir de um arquivo JSON. É o "script de implantação" do roteiro do piloto
(STATUS, log de 2026-11-11): criar negócio, central, loja e usuário ainda
não tem tela (só administrador da rede faria isso, e esse perfil não
existe). Produtos, setores, calendário e vínculos produto × loja o gestor
faz na tela de Cadastros depois.

Por padrão SÓ MOSTRA o que faria e desfaz tudo (simulação). Para gravar,
rode de novo com --aplicar.

    python scripts/implantar_cliente.py cliente.json            # simula
    python scripts/implantar_cliente.py cliente.json --aplicar  # grava

Formato do arquivo (exemplo completo em scripts/exemplo_implantacao.json):

    {
      "negocio": "Supermercado Exemplo",
      "centrais": [
        {
          "nome": "Padaria Central",
          "secao": "padaria",                 # padaria, acougue ou hortifruti
          "prazo_entrega_dias": 0,            # opcional, padrão 0
          "gestores": [{"nome": "Maria", "email": "maria@exemplo.com.br"}],
          "lojas": [
            {"nome": "Loja Centro", "codigo": "001",
             "horario_fechamento": "21:00", "horario_zeragem": "06:00",   # opcionais
             "operadores": [{"nome": "João", "email": "joao@exemplo.com.br"}]}
          ]
        }
      ]
    }

Regras:
- Idempotente: negócio pelo nome; central pelo nome dentro do negócio; loja
  pelo código dentro do negócio; usuário pelo e-mail. O que já existe não
  é alterado (nem senha, nem vínculo); só é listado como "existente".
- Usuário com o e-mail já usado em OUTRO negócio, ou com outro papel/loja/
  central, para tudo com erro: e-mail é único no sistema e trocar vínculo
  por script seria perigoso.
- Loja existente ligada a outra central também para com erro (D3: cada
  loja pertence a uma central).
- Senha: cada usuário criado ganha uma senha provisória aleatória, mostrada
  UMA vez na tela no fim (só com --aplicar). Não é gravada em arquivo
  nenhum. Ainda não há tela de troca de senha: entregar a senha à pessoa
  por um canal privado.
- Gestor: `gestor_central`, sem loja, com acesso ao SaaS e sem acesso ao
  app (regra de ouro 2). Operador: `operador_loja`, com acesso ao app.
- Tudo numa transação: qualquer erro desfaz tudo.
"""

import argparse
import json
import re
import secrets
import sys
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.security import hash_senha  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.central_producao import CentralProducao, SecaoCentral  # noqa: E402
from app.models.loja import Loja  # noqa: E402
from app.models.negocio import Negocio  # noqa: E402
from app.models.usuario import StatusUsuario, TipoUsuario, Usuario  # noqa: E402

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ErroImplantacao(Exception):
    pass


@dataclass
class Relatorio:
    linhas: list[str] = field(default_factory=list)
    senhas: list[tuple[str, str]] = field(default_factory=list)

    def add(self, texto: str) -> None:
        self.linhas.append(texto)


def _texto(dado: dict, chave: str, onde: str, maximo: int = 255) -> str:
    valor = dado.get(chave)
    if not isinstance(valor, str) or not valor.strip():
        raise ErroImplantacao(f"{onde}: falta o campo \"{chave}\".")
    valor = valor.strip()
    if len(valor) > maximo:
        raise ErroImplantacao(f"{onde}: \"{chave}\" passa de {maximo} caracteres.")
    return valor


def _hora(dado: dict, chave: str, padrao: time, onde: str) -> time:
    valor = dado.get(chave)
    if valor is None:
        return padrao
    if not isinstance(valor, str) or not HORA.match(valor):
        raise ErroImplantacao(f"{onde}: \"{chave}\" tem de ser HH:MM (ex.: 21:00).")
    h, m = valor.split(":")
    return time(int(h), int(m))


def validar(config: dict) -> None:
    """Confere o arquivo inteiro antes de tocar no banco."""
    if not isinstance(config, dict):
        raise ErroImplantacao("O arquivo tem de ser um objeto JSON.")
    _texto(config, "negocio", "Arquivo")
    centrais = config.get("centrais")
    if not isinstance(centrais, list) or not centrais:
        raise ErroImplantacao("Arquivo: \"centrais\" tem de ser uma lista com pelo menos uma central.")
    emails, codigos, nomes_central = set(), set(), set()
    for i, c in enumerate(centrais, 1):
        onde = f"Central {i}"
        nome = _texto(c, "nome", onde)
        if nome.lower() in nomes_central:
            raise ErroImplantacao(f"{onde}: nome \"{nome}\" repetido no arquivo.")
        nomes_central.add(nome.lower())
        secao = c.get("secao", "padaria")
        if secao not in {s.value for s in SecaoCentral}:
            raise ErroImplantacao(f"{onde}: seção \"{secao}\" inválida (padaria, acougue ou hortifruti).")
        prazo = c.get("prazo_entrega_dias", 0)
        if not isinstance(prazo, int) or isinstance(prazo, bool) or not 0 <= prazo <= 7:
            raise ErroImplantacao(f"{onde}: \"prazo_entrega_dias\" tem de ser um inteiro de 0 a 7.")
        if not c.get("gestores"):
            raise ErroImplantacao(f"{onde}: precisa de pelo menos um gestor.")
        pessoas = [("gestor", g, onde) for g in c.get("gestores", [])]
        lojas = c.get("lojas")
        if not isinstance(lojas, list) or not lojas:
            raise ErroImplantacao(f"{onde}: \"lojas\" tem de ser uma lista com pelo menos uma loja.")
        for j, loja in enumerate(lojas, 1):
            onde_loja = f"{onde}, loja {j}"
            _texto(loja, "nome", onde_loja)
            codigo = _texto(loja, "codigo", onde_loja, maximo=32)
            if codigo.lower() in codigos:
                raise ErroImplantacao(f"{onde_loja}: código \"{codigo}\" repetido no arquivo.")
            codigos.add(codigo.lower())
            _hora(loja, "horario_fechamento", time(21, 0), onde_loja)
            _hora(loja, "horario_zeragem", time(6, 0), onde_loja)
            pessoas += [("operador", o, onde_loja) for o in loja.get("operadores", [])]
        for papel, p, onde_p in pessoas:
            _texto(p, "nome", f"{onde_p}, {papel}")
            email = _texto(p, "email", f"{onde_p}, {papel}").lower()
            if not EMAIL.match(email):
                raise ErroImplantacao(f"{onde_p}, {papel}: e-mail \"{email}\" inválido.")
            if email in emails:
                raise ErroImplantacao(f"{onde_p}, {papel}: e-mail \"{email}\" repetido no arquivo.")
            emails.add(email)


def _usuario(db, rel: Relatorio, negocio: Negocio, pessoa: dict, tipo: TipoUsuario,
             loja_id: int | None, central_id: int | None) -> None:
    email = pessoa["email"].strip().lower()
    nome = pessoa["nome"].strip()
    rotulo = "Gestor" if tipo == TipoUsuario.GESTOR_CENTRAL else "Operador"
    existente = db.query(Usuario).filter(Usuario.email == email).first()
    if existente is not None:
        mesmo = (existente.negocio_id == negocio.id and existente.tipo_usuario == tipo
                 and existente.loja_id == loja_id and existente.central_producao_id == central_id)
        if not mesmo:
            raise ErroImplantacao(
                f"O e-mail {email} já existe com outro negócio, papel, loja ou central (usuário id={existente.id}). "
                "Use outro e-mail ou ajuste o usuário à mão."
            )
        rel.add(f"    {rotulo}: {email} [existente, não alterado]")
        return
    senha = secrets.token_urlsafe(9)
    db.add(Usuario(
        negocio_id=negocio.id,
        tipo_usuario=tipo,
        loja_id=loja_id,
        central_producao_id=central_id,
        nome=nome,
        email=email,
        senha_hash=hash_senha(senha),
        status=StatusUsuario.ATIVO,
        tem_acesso_app=tipo == TipoUsuario.OPERADOR_LOJA,
        tem_acesso_web=tipo == TipoUsuario.GESTOR_CENTRAL,
    ))
    db.flush()
    rel.add(f"    {rotulo}: {email} [criado]")
    rel.senhas.append((email, senha))


def implantar(db, config: dict) -> Relatorio:
    """Cria o que falta. Não faz commit: quem chama decide (simulação ou --aplicar)."""
    validar(config)
    rel = Relatorio()
    nome_negocio = config["negocio"].strip()
    negocios = db.query(Negocio).filter(Negocio.nome == nome_negocio).order_by(Negocio.id).all()
    if len(negocios) > 1:
        raise ErroImplantacao(f"Há {len(negocios)} negócios chamados \"{nome_negocio}\"; resolva à mão antes.")
    if negocios:
        negocio = negocios[0]
        rel.add(f"Negócio: {negocio.nome} (id={negocio.id}) [existente]")
    else:
        negocio = Negocio(nome=nome_negocio, ativo=True)
        db.add(negocio)
        db.flush()
        rel.add(f"Negócio: {negocio.nome} (id={negocio.id}) [criado]")

    for c in config["centrais"]:
        nome_central = c["nome"].strip()
        central = (db.query(CentralProducao)
                   .filter(CentralProducao.negocio_id == negocio.id, CentralProducao.nome == nome_central).first())
        if central:
            rel.add(f"  Central: {central.nome} (id={central.id}, {central.secao.value}) [existente, não alterada]")
        else:
            central = CentralProducao(negocio_id=negocio.id, nome=nome_central, ativa=True,
                                      secao=SecaoCentral(c.get("secao", "padaria")),
                                      prazo_entrega_dias=c.get("prazo_entrega_dias", 0))
            db.add(central)
            db.flush()
            rel.add(f"  Central: {central.nome} (id={central.id}, {central.secao.value}) [criada]")
        for g in c["gestores"]:
            _usuario(db, rel, negocio, g, TipoUsuario.GESTOR_CENTRAL, None, central.id)
        for item in c["lojas"]:
            codigo = item["codigo"].strip()
            onde = f"Loja {codigo}"
            loja = db.query(Loja).filter(Loja.negocio_id == negocio.id, Loja.codigo == codigo).first()
            if loja:
                if loja.central_producao_id != central.id:
                    raise ErroImplantacao(
                        f"A loja de código {codigo} já existe ligada a outra central (id={loja.central_producao_id})."
                    )
                rel.add(f"    Loja: {codigo} {loja.nome} (id={loja.id}) [existente, não alterada]")
            else:
                loja = Loja(negocio_id=negocio.id, central_producao_id=central.id, nome=item["nome"].strip(),
                            codigo=codigo, ativo=True,
                            horario_fechamento=_hora(item, "horario_fechamento", time(21, 0), onde),
                            horario_zeragem=_hora(item, "horario_zeragem", time(6, 0), onde))
                db.add(loja)
                db.flush()
                rel.add(f"    Loja: {codigo} {loja.nome} (id={loja.id}, fecha {loja.horario_fechamento:%H:%M}) [criada]")
            for o in item.get("operadores", []):
                _usuario(db, rel, negocio, o, TipoUsuario.OPERADOR_LOJA, loja.id, None)
    return rel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Implanta um cliente novo a partir de um arquivo JSON.")
    parser.add_argument("arquivo", type=Path)
    parser.add_argument("--aplicar", action="store_true", help="grava no banco (sem isto, só simula)")
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.arquivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERRO: não consegui ler {args.arquivo}: {e}")
        return 2
    db = SessionLocal()
    try:
        rel = implantar(db, config)
        if args.aplicar:
            db.commit()
        else:
            db.rollback()
    except ErroImplantacao as e:
        db.rollback()
        print(f"ERRO: {e}\nNada foi gravado.")
        return 1
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print("\n".join(rel.linhas))
    if not args.aplicar:
        print("\nSIMULAÇÃO: nada foi gravado. Rode de novo com --aplicar para gravar.")
        return 0
    if rel.senhas:
        print("\nSenhas provisórias (aparecem só agora; entregue a cada pessoa por canal privado):")
        for email, senha in rel.senhas:
            print(f"  {email}  {senha}")
    print("\nGravado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
