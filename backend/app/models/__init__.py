"""
Importa todos os modelos em um único lugar.

Isso é importante por dois motivos:
1. O Alembic (ferramenta de migração) precisa que todos os modelos já
   tenham sido importados para conseguir detectar as tabelas e gerar
   as migrações automaticamente.
2. Os relacionamentos entre tabelas (relationship) usam o nome da classe
   como string (ex.: "Usuario"), e o SQLAlchemy só consegue resolver isso
   se a classe já tiver sido carregada em algum momento.
"""

from app.models.negocio import Negocio  # noqa: F401
from app.models.central_producao import CentralProducao  # noqa: F401
from app.models.loja import Loja  # noqa: F401
from app.models.usuario import Usuario, StatusUsuario, TipoUsuario  # noqa: F401
from app.models.permissao_web import PermissaoWeb  # noqa: F401
from app.models.produto import Produto, UnidadeMedida, CicloPrevisao  # noqa: F401
from app.models.produto_loja import ProdutoLoja  # noqa: F401
from app.models.nivel_classificacao import NivelClassificacao  # noqa: F401
from app.models.produto_classificacao import ProdutoClassificacao  # noqa: F401
from app.models.estoque_atual import EstoqueAtual  # noqa: F401
from app.models.historico_contagem import HistoricoContagem  # noqa: F401
from app.models.calendario_producao import CalendarioProducao, DiaSemana  # noqa: F401
from app.models.evento import Evento, EventoLoja, EventoProduto  # noqa: F401
from app.models.evento import EscopoLoja, EscopoProduto, TipoAjuste  # noqa: F401
from app.models.venda_diaria import VendaDiaria, OrigemVenda  # noqa: F401
from app.models.perda_diaria import PerdaDiaria, OrigemPerda  # noqa: F401
