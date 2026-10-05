# AI Workforce SaaS

A multi-agent AI platform where specialized agents automate HR, Marketing,
Finance, Legal, Research, and Productivity workflows.

## Current Module

- Backend foundation (in progress)
  - FastAPI application with versioned API (`/api/v1`)
  - Agent abstraction, registry, and adapters
  - Orchestrator for agent dispatch
- Agents (developed separately, not yet integrated)
  - Knowledge Agent — RAG document Q&A
  - Automation Agent — productivity request drafting
  - Performance Analyzer — data analytics

## Tech Stack

Backend: Python 3.12, FastAPI, Pydantic v2, pydantic-settings, pytest, ruff,
mypy. The agents additionally use PyTorch, Transformers, and Llama 3.1 8B.

## Getting Started

See [`backend/README.md`](backend/README.md) for setup, running the API, the API
reference, and instructions for integrating the agent implementations.

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```