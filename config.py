import os
from pathlib import Path
from typing import Optional

# Try to import dotenv, but don't fail if it is not installed
try:
    from dotenv import load_dotenv

    # Load environment variables from .env file if it exists
    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)
except ImportError:
    print("python-dotenv not installed. Using only system environment variables.")


def get_env_variable(name: str, default: Optional[str] = None) -> str:
    """
    Get an environment variable or return a default value if provided.

    Args:
        name: Name of the environment variable
        default: Default value to return if the environment variable is not set

    Returns:
        The value of the environment variable or the default value
    """
    value = os.environ.get(name, default)
    if value is None:
        raise ValueError(
            f"Environment variable {name} is not set and no default was provided"
        )
    return value


# Milvus configuration
MILVUS_ENDPOINT = get_env_variable("MILVUS_ENDPOINT")
MILVUS_TOKEN = get_env_variable("MILVUS_TOKEN")

# Gemini configuration
GEMINI_API_KEY = get_env_variable("GEMINI_API_KEY")

# Default collection name
DEFAULT_COLLECTION_NAME = get_env_variable("DEFAULT_COLLECTION_NAME", "code_chunks")
DEFAULT_PROJECT_DIR = get_env_variable("DEFAULT_PROJECT_DIR", ".")

# DeepSeeK configuration
DEEPSEEK_API_KEY = get_env_variable("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = get_env_variable("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# Telegram configuration
TELEGRAM_BOT_TOKEN = get_env_variable("TELEGRAM_BOT_TOKEN")
