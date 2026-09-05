from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    telegram_token: str
    telegram_allowed_user_id: int

    # Webhook
    webhook_base_url: str
    webhook_secret_token: str

    # Temporary upstream providers. Wave 1 replaces these with OpenAI.
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-6"
    gemini_api_key: str
    gemini_models: str = "gemini-2.5-flash-lite,gemini-2.5-flash"

    # Conversation storage/context
    database_path: str = "data/telegram-llm.sqlite3"
    recent_context_items: int = 12
    compact_after_items: int = 24
    max_summary_chars: int = 4000

    # Behavior
    max_response_chars: int = 280
    max_tool_iterations: int = 5


settings = Settings()
