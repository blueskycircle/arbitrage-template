import os
from functools import lru_cache
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings:
    """Application settings loaded from environment variables with defaults.

    This centralized configuration class follows the 12-factor app methodology
    by allowing configuration through environment variables, while providing
    sensible defaults for local development.
    """

    # Project metadata
    PROJECT_NAME = "Arbitrage Tracker"
    PROJECT_VERSION = "0.1.0"

    # Database Settings
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_NAME = os.getenv("DB_NAME", "arbitrage")
    DB_USER = os.getenv("DB_USER", "user")
    DB_PASS = os.getenv("DB_PASSWORD", "password")

    @property
    def DATABASE_URL(self) -> str:
        """Constructs a SQLAlchemy connection string for MySQL."""
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


# For direct access in other modules
settings = get_settings()
