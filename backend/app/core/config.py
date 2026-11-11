from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Autonomous Inventory Management"
    environment: str = "development"
    secret_key: str = "dev-secret-change-me-in-production"
    access_token_expire_minutes: int = 60 * 12

    # SQLite by default so the project runs with zero infrastructure.
    # docker-compose overrides this with a PostgreSQL URL.
    database_url: str = "sqlite:///./inventory.db"

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Open self-service registration. Disable after creating your owner account
    # if the deployment is private.
    allow_registration: bool = True

    # Inventory policy defaults (can be overridden per product/warehouse).
    service_level: float = 0.95
    review_period_days: int = 7
    default_lead_time_days: int = 7
    default_moq: int = 1
    default_order_multiple: int = 1
    forecast_history_days: int = 180

    # Optional LLM for the AI agent. When empty, a deterministic tool router
    # answers questions so the product remains fully functional offline.
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # Demo seeding is OFF by default. Set SEED_DEMO_DATA=true only when you
    # explicitly want the synthetic "Cửa hàng Demo" data for a walkthrough.
    seed_demo_data: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
