import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa
from app.db.session import SessionLocal

db = SessionLocal()
result = db.execute(sa.text("SELECT typname FROM pg_catalog.pg_type WHERE typtype = 'e' ORDER BY typname")).fetchall()
db.close()
print("Enum types no banco:")
for r in result:
    print(" -", r[0])
