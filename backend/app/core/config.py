"""Centralized application configuration.

All environment-specific values are read here so that no other module
reads ``os.environ`` directly. Settings are loaded from environment
variables and, when present, a local ``.env`` file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]


class Settings(BaseSettings):
    """Application settings resolved from the environment.

    Attributes:
        app_name: Human-readable application name.
        app_version: Semantic version of the deployed backend.
        environment: Deployment environment.
        debug: Enables verbose errors. Must stay false in production.
        api_v1_prefix: Mount prefix for the version 1 API.
        host: Interface the server binds to.
        port: Port the server binds to.
        cors_origins: Origins allowed to call the API from a browser.
        log_level: Root log level name.
        log_format: ``console`` for local development, ``json`` for shipping.
        log_request_body: Whether to log request bodies. Off by default
            because bodies can contain user data.
        knowledge_agent_enabled: Whether to attempt constructing the Knowledge
            Agent at startup. A construction failure degrades it to unavailable
            rather than blocking startup.
        automation_agent_enabled: Whether to attempt constructing the Automation
            Agent at startup, with the same failure behaviour.
        performance_agent_enabled: Whether the Performance Analyzer is listed as
            available in the agent catalog. It does not gate the job API: jobs
            run whether or not this flag is set.
        knowledge_chroma_path: Directory backing the Knowledge Agent vector
            store. Relative paths resolve from the backend directory.
        knowledge_embedding_model: HuggingFace embedding model identifier.
        knowledge_upload_dir: Directory holding documents uploaded through the
            Knowledge document API. Relative paths resolve from the backend
            directory. Local disk is a development-MVP choice; a deployment
            needs persistent, shared storage.
        knowledge_upload_manifest_path: JSON manifest recording the metadata of
            each uploaded document. Holds no document contents and no vectors.
        knowledge_max_upload_bytes: Largest accepted upload, enforced while
            streaming so an oversized file is never fully buffered.
        ollama_base_url: Base URL of the local Ollama server.
        ollama_model: Ollama model tag used for generation.
        knowledge_agent_timeout_seconds: Wall-clock budget for one Knowledge
            Agent operation. Sized for CPU-bound generation plus embedding.
        automation_agent_timeout_seconds: Wall-clock budget for one Automation
            Agent operation.
        performance_agent_timeout_seconds: Reserved. Not currently read by any
            code: the job runner enforces no time limit, so a Performance job
            runs until it completes or fails and never returns 504.
        agent_max_concurrency: Upper bound on agent operations executing at
            once, across all agents. Real agents are CPU-bound, so this is
            deliberately far below anyio's default thread limiter of 40.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AI SaaS Platform API"
    app_version: str = "0.1.0"
    environment: Environment = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    host: str = "127.0.0.1"
    port: int = 8000

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"
    log_request_body: bool = False

    knowledge_agent_enabled: bool = False
    automation_agent_enabled: bool = False
    performance_agent_enabled: bool = False

    knowledge_chroma_path: Path = Path("knowledge_agent/data/chroma_db")
    knowledge_embedding_model: str = "BAAI/bge-base-en-v1.5"

    knowledge_upload_dir: Path = Path("uploads/knowledge")
    knowledge_upload_manifest_path: Path = Path("uploads/knowledge/documents.json")
    knowledge_max_upload_bytes: int = 25 * 1024 * 1024

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    knowledge_agent_timeout_seconds: float = 300.0
    automation_agent_timeout_seconds: float = 180.0
    performance_agent_timeout_seconds: float = 600.0

    agent_max_concurrency: int = 4

    @property
    def backend_dir(self) -> Path:
        """Return the backend package directory.

        Agent paths are stored relative to this directory so that they do not
        depend on the process working directory.

        Returns:
            The directory containing app/ and the agent packages.
        """
        return Path(__file__).resolve().parents[2]

    @property
    def resolved_knowledge_chroma_path(self) -> Path:
        """Return the Knowledge Agent vector store directory.

        Returns:
            An absolute path to the Chroma persistence directory.
        """
        path = self.knowledge_chroma_path
        return path if path.is_absolute() else self.backend_dir / path

    def resolve_upload_path(self, path: Path) -> Path:
        """Resolve a configured path against the backend directory.

        Args:
            path: A configured path, absolute or backend-relative.

        Returns:
            An absolute path that does not depend on the process working
            directory.
        """
        return path if path.is_absolute() else self.backend_dir / path

    @property
    def resolved_knowledge_upload_dir(self) -> Path:
        """Return the directory that stores uploaded knowledge documents.

        Returns:
            An absolute path to the upload directory.
        """
        return self.resolve_upload_path(self.knowledge_upload_dir)

    @property
    def resolved_knowledge_upload_manifest_path(self) -> Path:
        """Return the document manifest file path.

        Returns:
            An absolute path to the JSON manifest.
        """
        return self.resolve_upload_path(self.knowledge_upload_manifest_path)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Allow comma-separated origins in addition to a JSON list.

        Args:
            value: Raw value from the environment.

        Returns:
            Parsed origin list, or the original value when already a list.
        """
        if isinstance(value, str) and not value.strip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        """Uppercase the log level name.

        Args:
            value: Raw level string.

        Returns:
            Uppercased level name.
        """
        return value.upper()

    @property
    def is_production(self) -> bool:
        """Report whether the app is running in production.

        Returns:
            True when the environment is production.
        """
        return self.environment == "production"

    @property
    def wildcard_cors_enabled(self) -> bool:
        """Report whether any CORS origin is a wildcard.

        Returns:
            True when ``*`` appears in the configured origins.
        """
        return "*" in self.cors_origins


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings instance.

    Returns:
        The process-wide Settings object.
    """
    return Settings()
