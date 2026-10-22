"""Version 1 API router.

Aggregates the v1 sub-routers. Adding a new area means adding a module here
and nothing else.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import activity, agents, auth, automation, health, knowledge, performance, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(agents.router)
api_router.include_router(activity.router)
api_router.include_router(knowledge.router)
api_router.include_router(automation.router)
api_router.include_router(performance.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
