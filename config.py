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

# Default collections names and project directories
BUSINESS_WEB_COLLECTION_NAME = get_env_variable("BUSINESS_WEB_COLLECTION_NAME", "")
BUSINESS_WEB_PROJECT_DIR = get_env_variable(
    "BUSINESS_WEB_PROJECT_DIR", "../business-web"
)

CLIENT_WEB_COLLECTION_NAME = get_env_variable("CLIENT_WEB_COLLECTION_NAME", "")
CLIENT_WEB_PROJECT_DIR = get_env_variable("CLIENT_WEB_PROJECT_DIR", "../client_web")

JETLEND_CORE_COLLECTION_NAME = get_env_variable("JETLEND_CORE_COLLECTION_NAME", "")
JETLEND_CORE_PROJECT_DIR = get_env_variable(
    "JETLEND_CORE_PROJECT_DIR", "../jetlend-core"
)

UNDERWRITER_WEB_COLLECTION_NAME = get_env_variable(
    "UNDERWRITER_WEB_COLLECTION_NAME", ""
)
UNDERWRITER_WEB_PROJECT_DIR = get_env_variable(
    "UNDERWRITER_WEB_PROJECT_DIR", "../underwriter-web"
)

FRONTEND_BUSINESS_COLLECTION_NAME = get_env_variable(
    "FRONTEND_BUSINESS_COLLECTION_NAME", ""
)
FRONTEND_BUSINESS_PROJECT_DIR = get_env_variable(
    "FRONTEND_BUSINESS_PROJECT_DIR", "../jetlend_business_frontend"
)

FRONTEND_UNDERWRITING_COLLECTION_NAME = get_env_variable(
    "FRONTEND_UNDERWRITING_COLLECTION_NAME", ""
)
FRONTEND_UNDERWRITING_PROJECT_DIR = get_env_variable(
    "FRONTEND_UNDERWRITING_PROJECT_DIR", "../jetlend_underwriting_frontend"
)

FRONTEND_PARTNER_COLLECTION_NAME = get_env_variable(
    "FRONTEND_PARTNER_COLLECTION_NAME", ""
)
FRONTEND_PARTNER_PROJECT_DIR = get_env_variable(
    "FRONTEND_PARTNER_PROJECT_DIR", "../jetlend_partner_frontend"
)

FRONTEND_CLIENT_COLLECTION_NAME = get_env_variable(
    "FRONTEND_CLIENT_COLLECTION_NAME", ""
)
FRONTEND_CLIENT_PROJECT_DIR = get_env_variable(
    "FRONTEND_CLIENT_PROJECT_DIR", "../jetlend_client_frontend"
)

FRONTEND_JETLEND_SITE_COLLECTION_NAME = get_env_variable(
    "FRONTEND_JETLEND_SITE_COLLECTION_NAME", ""
)
FRONTEND_JETLEND_SITE_PROJECT_DIR = get_env_variable(
    "FRONTEND_JETLEND_SITE_PROJECT_DIR", "../jetlend_site_ssr"
)

# DeepSeeK configuration
DEEPSEEK_API_KEY = get_env_variable("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = get_env_variable("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# Telegram configuration
TELEGRAM_BOT_TOKEN = get_env_variable("TELEGRAM_BOT_TOKEN")
