from functools import lru_cache
import json
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: str = "development"
    auth_mode: str = "development"  # Use firebase in every public deployment.
    firebase_project_id: str = ""
    firebase_service_account_json: str = ""
    app_allowed_origins: str = "http://localhost:3000,http://localhost:8501"

    database_url: str = "postgresql+asyncpg://jarvis:jarvis@localhost:5432/jarvis"
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_agent_name: str = "jarvis-agent"

    google_api_key: str = ""
    stt_model: str = "speechmatics/linden-1"
    gemini_flash_model: str = "google/gemini-3.6-flash"
    gemini_complex_model: str = "google/gemini-3.1-pro-preview"
    gemini_tts_model: str = "gemini-3.8-flash-tts"
    gemini_tts_voice: str = "Kore"
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768

    ha_url: str = ""
    ha_long_lived_token: str = ""
    ha_allowed_lights: str = "[]"
    ha_allowed_switches: str = "[]"
    ha_allowed_automations: str = "[]"
    ha_readonly_entity_ids: str = "[]"
    confirmation_ttl_seconds: int = 90

    @property
    def cors_origins(self) -> list[str]:
        return [x.strip() for x in self.app_allowed_origins.split(",") if x.strip()]

    @staticmethod
    def _json_list(raw: str) -> set[str]:
        try:
            value = json.loads(raw)
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                raise ValueError
            return {x.strip() for x in value if x.strip()}
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError("Allowlist variables must be JSON arrays of strings") from exc

    @property
    def allowed_lights(self) -> set[str]:
        return self._json_list(self.ha_allowed_lights)

    @property
    def allowed_switches(self) -> set[str]:
        return self._json_list(self.ha_allowed_switches)

    @property
    def allowed_automations(self) -> set[str]:
        return self._json_list(self.ha_allowed_automations)

    @property
    def readonly_entities(self) -> set[str]:
        return self._json_list(self.ha_readonly_entity_ids)


@lru_cache
def get_settings() -> Settings:
    return Settings()
