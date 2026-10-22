import sys
sys.path.insert(0, '.')
from app.models import Base, User
tbl = Base.metadata.tables['users']
print("Columns:")
for col in tbl.columns:
    print(f"  {col.name}: {col.type}, index={col.index}, unique={col.unique}")
print("\nIndexes:")
for idx in tbl.indexes:
    print(f"  {idx.name}: {idx.columns}, unique={idx.unique}")