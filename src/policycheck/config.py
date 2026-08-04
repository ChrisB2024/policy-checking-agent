"""Settings, loaded from the environment and `.env`.

Precedence: real environment variables win over `.env`, so CI and shell exports override the
local file without editing it.

⚠️ One gotcha worth knowing: the Anthropic SDK reads `ANTHROPIC_API_KEY` from the *process*
environment. A key that lives only in `.env` is visible to this module but invisible to a
bare `anthropic.Anthropic()`. Either pass it explicitly —

    anthropic.Anthropic(api_key=settings().anthropic_api_key)

— or call `export_to_environ()` once at process start. The explicit form is preferred; it
keeps the dependency visible at the call site.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Credentials -------------------------------------------------------
    # SecretStr keeps these out of tracebacks and repr() output. Call
    # .get_secret_value() at the point of use.
    anthropic_api_key: SecretStr | None = None
    courtlistener_api_token: SecretStr | None = None

    database_url: str = "postgresql+asyncpg://localhost:5432/policycheck"
    """Only the API and demo cache need this. The engine — extract, normalize, compare,
    eval — runs with no database available (.spec/modules/persistence.md)."""

    # --- Pipeline ----------------------------------------------------------
    extraction_model: str = "claude-opus-5"
    """Do not downgrade to save cost. Extraction accuracy is the product."""

    extraction_passes: int = 2
    """Spec §10: two independent passes, disagreements marked `low` confidence. Dropping to
    1 does not just cost accuracy — it makes the `needs_review` bucket dishonest, because
    nothing is left to disagree."""

    demo_mode: bool = True
    """Spec invariant 5: documents are processed in memory and discarded. This is stated to
    prospects unprompted, so the default is on and turning it off is deliberate."""

    raster_cache_dir: Path = Field(default=Path(".raster_cache"))
    """Run-scoped. Cleared when a run ends, including on failure — otherwise the retention
    claim above is false."""

    # A blank line in .env (`ANTHROPIC_API_KEY=`) parses as SecretStr(""), not None — so
    # these check the value, not just the field. Otherwise an unfilled .env sails through
    # and surfaces as a 401 from the API instead of "you didn't set the key."
    def require_anthropic_key(self) -> str:
        value = self.anthropic_api_key.get_secret_value() if self.anthropic_api_key else ""
        if not value:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to .env (see .env.example) or export it."
            )
        return value

    def require_courtlistener_token(self) -> str:
        value = (
            self.courtlistener_api_token.get_secret_value()
            if self.courtlistener_api_token
            else ""
        )
        if not value:
            raise RuntimeError(
                "COURTLISTENER_API_TOKEN is not set. Get one from "
                "https://www.courtlistener.com/profile/api/ and add it to .env "
                "(see .env.example). Unauthenticated requests are throttled far below the "
                "125/day authenticated budget."
            )
        return value

    def export_to_environ(self) -> None:
        """Push credentials into os.environ for libraries that read it directly.

        Escape hatch for third-party clients constructed somewhere you cannot pass a key.
        Prefer explicit injection; this widens the blast radius of a leak.
        """
        import os

        if self.anthropic_api_key:
            os.environ.setdefault("ANTHROPIC_API_KEY", self.anthropic_api_key.get_secret_value())
        if self.courtlistener_api_token:
            os.environ.setdefault(
                "COURTLISTENER_API_TOKEN", self.courtlistener_api_token.get_secret_value()
            )


@lru_cache(maxsize=1)
def settings() -> Settings:
    """Process-wide settings. Cached so `.env` is read once.

    A function rather than a module-level constant so tests can clear the cache
    (`settings.cache_clear()`) instead of monkeypatching an already-bound object.
    """
    return Settings()
