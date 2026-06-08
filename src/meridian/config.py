"""Central configuration (pydantic-settings).

Single source of truth for env-driven config. Budget ceilings here back
Property 4 (production scaffolding); model fields keep the model layer
swappable (Anthropic default, not vendor-locked).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # protected_namespaces=() silences pydantic's warning about `model*` fields.
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
        protected_namespaces=(),
    )

    env: str = Field("local", validation_alias=AliasChoices("env", "MERIDIAN_ENV"))

    # Models — provider-neutral interface, Anthropic defaults.
    anthropic_api_key: str = ""
    model: str = Field("claude-opus-4-8", validation_alias=AliasChoices("model", "MERIDIAN_MODEL"))
    fallback_model: str = Field(
        "claude-sonnet-4-6",
        validation_alias=AliasChoices("fallback_model", "MERIDIAN_FALLBACK_MODEL"),
    )
    model_fast: str = Field(
        "claude-haiku-4-5-20251001",
        validation_alias=AliasChoices("model_fast", "MERIDIAN_MODEL_FAST"),
    )

    # Datastores
    database_url: str = "postgresql+asyncpg://meridian:meridian@localhost:5432/meridian"
    redis_url: str = "redis://localhost:6379/0"

    # Agent budget ceilings (Property 4) — enforced natively by the SDK.
    max_budget_usd: float = Field(
        5.0, validation_alias=AliasChoices("max_budget_usd", "MERIDIAN_MAX_BUDGET_USD")
    )
    max_turns: int = Field(80, validation_alias=AliasChoices("max_turns", "MERIDIAN_MAX_TURNS"))

    # Per-task git worktree root (Property 2 isolation).
    workspace_dir: Path = Field(
        Path("./.workspaces"),
        validation_alias=AliasChoices("workspace_dir", "MERIDIAN_WORKSPACE_DIR"),
    )

    # Retry policy (Property 4 — W2). Transient SDK failures only.
    retry_max_attempts: int = Field(
        3, validation_alias=AliasChoices("retry_max_attempts", "MERIDIAN_RETRY_MAX_ATTEMPTS")
    )
    retry_base_s: float = Field(
        1.0, validation_alias=AliasChoices("retry_base_s", "MERIDIAN_RETRY_BASE_S")
    )
    retry_cap_s: float = Field(
        30.0, validation_alias=AliasChoices("retry_cap_s", "MERIDIAN_RETRY_CAP_S")
    )

    # GitHub App (Phase 4 intake)
    github_app_id: str = ""
    github_webhook_secret: str = ""
    github_private_key_path: str = ""
    github_token: str = Field(
        "", validation_alias=AliasChoices("github_token", "MERIDIAN_GITHUB_TOKEN")
    )

    # Azure AI Foundry — optional. When set, the Claude Agent SDK routes through
    # Azure's hosted Claude endpoint instead of Anthropic's API directly.
    # Get these from: Azure AI Foundry → your project → Models → Claude deployment.
    azure_ai_foundry_endpoint: str = Field(
        "", validation_alias=AliasChoices("azure_ai_foundry_endpoint", "AZURE_AI_FOUNDRY_ENDPOINT")
    )
    azure_ai_foundry_key: str = Field(
        "", validation_alias=AliasChoices("azure_ai_foundry_key", "AZURE_AI_FOUNDRY_KEY")
    )

    # Azure Monitor — optional. When set, spans are also forwarded to App Insights.
    azure_application_insights_connection_string: str = Field(
        "",
        validation_alias=AliasChoices(
            "azure_application_insights_connection_string",
            "APPLICATIONINSIGHTS_CONNECTION_STRING",
        ),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
