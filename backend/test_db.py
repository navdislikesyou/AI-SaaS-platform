import sys
sys.path.insert(0, '.')
from app.models import Base
from sqlalchemy import create_engine, text

engine = create_engine('sqlite:///./app.db')
Base.metadata.create_all(engine)

with engine.connect() as conn:
    result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    print('Tables:', [row[0] for row in result.fetchall()])