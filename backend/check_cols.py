import sys
sys.path.insert(0, '.')
from app.models import Base, Organization
tbl = Base.metadata.tables['organizations']
print("Columns:")
for col in tbl.columns:
    print(f"  {col.name}: {col.type}, index={col.index}, unique={col.unique}")