import sys
sys.path.insert(0, '.')
from app.models import Base
for tbl in Base.metadata.tables:
    print(tbl, Base.metadata.tables[tbl].indexes)