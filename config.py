from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    telegram_token: str
    telegram_allowed_user_id: int

    # Webhook
    webhook_base_url: str
    webhook_secret_token: str

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-5.6-terra"
    openai_reasoning_effort: str = "low"
    openai_timeout_seconds: float = 45.0
    openai_max_output_tokens: int = 1800
    web_search_context_size: str = "medium"

    # Conversation storage/context
    database_path: str = "data/telegram-llm.sqlite3"
    recent_context_items: int = 12
    compact_after_items: int = 24
    max_summary_chars: int = 4000

    # Deployment/behavior
    app_revision: str = "unknown"
    max_response_chars: int = 3500
    pdf_max_chars: int = 60000


settings = Settings()
