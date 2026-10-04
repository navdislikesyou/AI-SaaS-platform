# Knowledge Agent checks

These are manual verification scripts, not automated tests. Each one loads real
data or a real model and prints what it finds, so they are slow and have side
effects. They were previously named `test_*.py`, which made pytest try to
collect them.

They are not collected today because `pyproject.toml` sets
`testpaths = ["tests"]`, pointing at the backend suite only. That is a
coincidence of configuration, not a safeguard, and it is why they were renamed.

Run one directly:

```bash
cd backend
python -m knowledge_agent.checks.check_loader
```

| Script | What it does |
|---|---|
| `check_loader.py` | Loads `data/documents/sample.pdf` and prints page count, metadata, and the first 500 characters |
| `check_splitter.py` | Loads the sample PDF and prints the resulting chunk sizes |
| `check_embeddings.py` | Loads the BGE embedding model and prints its vector dimension |
| `check_vectordb.py` | Builds the Chroma store and runs a search against it |

`check_embeddings.py` and `check_vectordb.py` require the agent dependencies
and a populated Chroma store. See `requirements-agents.txt`.

Real automated coverage for this agent is in `backend/tests/`, using fakes. It
never loads a model.