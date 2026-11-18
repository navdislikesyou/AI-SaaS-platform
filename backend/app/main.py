"""Application entry point.

Builds the FastAPI application, wires logging, configuration, CORS, middleware,
exception handlers, and the shared agent registry and orchestrator. Importing
``app.main:app`` and running uvicorn against it is the only supported way to
start the server.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse

from app.agents.factory import build_registry
from app.api.deps import init_orchestrator, init_registry
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.database import init_engine, shutdown_engine
from app.core.exceptions import register_exception_handlers
from app.core.logging_config import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.services.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

DESCRIPTION = """
Backend API for the AI SaaS Platform.

The backend exposes stable HTTP contracts and coordinates a set of agents:
a Knowledge Agent for document question answering, an Automation Agent for
productivity requests, and a Performance Analyzer for data analytics.

Agents are connected through adapters and run synchronously via
POST /api/v1/agents/execute. The Performance Analyzer is implemented too, but
its analysis is CPU-bound and long running, so it runs as a background job via
POST /api/v1/performance/jobs. It appears in the catalog with no capabilities so
the catalog does not imply it is reachable through /agents/execute.
""".strip()


def custom_openapi(app: FastAPI) -> dict:
    """Generate an OpenAPI schema with a JWT HTTP Bearer security scheme.

    Args:
        app: The FastAPI application instance.

    Returns:
        Custom OpenAPI schema dictionary.
    """
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=DESCRIPTION,
        routes=app.routes,
    )

    if "components" not in openapi_schema:
        openapi_schema["components"] = {}

    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {}

    openapi_schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Access token returned by POST /api/v1/auth/login.",
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application.

    Args:
        settings: Optional settings override. Defaults to the cached
            environment-backed settings.

    Returns:
        A configured FastAPI application.

    Raises:
        ValueError: If production settings are unsafe, such as debug enabled
            or wildcard CORS origins.
    """
    resolved = settings or get_settings()
    configure_logging(resolved.log_level, resolved.log_format)
    _validate_settings(resolved)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Initialize shared services on startup and log shutdown."""
        registry = build_registry(resolved)
        init_registry(registry)
        init_orchestrator(Orchestrator(registry))
        # Initialize database engine
        init_engine(resolved.database_url, echo=resolved.environment != "production")
        logger.info(
            "startup app=%s version=%s env=%s agents=%d",
            resolved.app_name,
            resolved.app_version,
            resolved.environment,
            len(registry),
        )
        for adapter in registry.list_all():
            logger.info(
                "agent_status agent=%s available=%s capabilities=%s",
                adapter.name,
                adapter.is_available(),
                adapter.capabilities(),
            )
        yield
        logger.info("shutdown app=%s", resolved.app_name)
        # Dispose of database engine
        await shutdown_engine()

    app = FastAPI(
        title=resolved.app_name,
        version=resolved.app_version,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url=None,
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Override the default openapi method with our custom one
    app.openapi = lambda: custom_openapi(app)  # type: ignore[method-assign]

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui() -> HTMLResponse:
        """Serve Swagger UI with a helper for the email-and-password login flow."""
        swagger_response = get_swagger_ui_html(
            openapi_url=app.openapi_url or "/openapi.json",
            title=f"{app.title} - Swagger UI",
        )
        html = bytes(swagger_response.body).decode("utf-8")
        initializer = "const ui = SwaggerUIBundle("
        if initializer not in html:
            raise RuntimeError("Could not expose the Swagger UI instance for login authorization.")
        html = html.replace(initializer, "window.ui = SwaggerUIBundle(", 1)

        login_helper = """
<section aria-label="Swagger email and password login" style="padding: 1rem;">
  <form id="swagger-login-form">
    <label for="swagger-login-email">Email</label>
    <input id="swagger-login-email" name="email" type="email" autocomplete="username" required>
    <label for="swagger-login-password">Password</label>
    <input
      id="swagger-login-password"
      name="password"
      type="password"
      autocomplete="current-password"
      required
    >
    <button type="submit">Login and authorize</button>
    <span id="swagger-login-status" role="status" aria-live="polite"></span>
  </form>
</section>
<script>
(() => {
  const form = document.getElementById("swagger-login-form");
  const status = document.getElementById("swagger-login-status");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = new URLSearchParams({
      email: document.getElementById("swagger-login-email").value,
      password: document.getElementById("swagger-login-password").value
    });
    status.textContent = "Signing in...";
    try {
      const response = await fetch(__LOGIN_URL__ + "?" + query.toString(), { method: "POST" });
      const result = await response.json();
      if (!response.ok || typeof result.access_token !== "string" || !result.access_token) {
        status.textContent = "Login failed. Check your email and password.";
        return;
      }
      if (!window.ui || typeof window.ui.preauthorizeApiKey !== "function") {
        status.textContent = "Login succeeded, but Swagger authorization is unavailable.";
        return;
      }
      window.ui.preauthorizeApiKey("BearerAuth", result.access_token);
      document.getElementById("swagger-login-password").value = "";
      status.textContent = "Signed in. Bearer token is ready for authorized requests.";
    } catch (error) {
      status.textContent = "Unable to contact the login endpoint.";
    }
  });
})();
</script>
"""
        login_helper = login_helper.replace(
            "__LOGIN_URL__", json.dumps(f"{resolved.api_v1_prefix}/auth/login")
        )
        swagger_container = '<div id="swagger-ui">'
        if swagger_container not in html:
            raise RuntimeError("Could not locate the Swagger UI container for the login helper.")
        html = html.replace(swagger_container, f"{login_helper}\n{swagger_container}", 1)
        return HTMLResponse(content=html, status_code=swagger_response.status_code)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=resolved.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        """Redirect consumers toward the API documentation.

        Returns:
            A short pointer to the docs and health endpoints.
        """
        return {
            "service": resolved.app_name,
            "version": resolved.app_version,
            "docs": "/docs",
            "health": f"{resolved.api_v1_prefix}/health",
        }

    return app


def _validate_settings(settings: Settings) -> None:
    """Reject unsafe production configuration.

    Args:
        settings: The settings to check.

    Raises:
        ValueError: If debug is enabled or CORS allows any origin in
            production.
    """
    if not settings.is_production:
        return
    if settings.debug:
        raise ValueError("DEBUG must be false when ENVIRONMENT=production.")
    if settings.wildcard_cors_enabled:
        raise ValueError("Wildcard CORS origins are not allowed in production.")


app = create_app()
