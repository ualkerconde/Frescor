"""
Modelo da tabela `permissoes_web`.

Relaciona um usuário às páginas/módulos do software web que ele pode
acessar. Mantida simples de propósito (uma linha por permissão concedida);
o conjunto de valores possíveis para `pagina_ou_modulo` é definido e
controlado pelo software web (fora do escopo deste backend de coleta).
"""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PermissaoWeb(Base):
    __tablename__ = "permissoes_web"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    pagina_ou_modulo: Mapped[str] = mapped_column(String(100), nullable=False)
