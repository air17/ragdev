import pytest
from unittest.mock import patch
import os

from config import get_env_variable


class TestConfig:
    def test_get_env_variable_exists(self):
        # Test with existing environment variable
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = get_env_variable("TEST_VAR")
            assert result == "test_value"

    def test_get_env_variable_with_default(self):
        # Test with non-existent variable but with default
        with patch.dict(os.environ, {}, clear=True):  # Clear env variables
            result = get_env_variable("NONEXISTENT_VAR", default="default_value")
            assert result == "default_value"

    def test_get_env_variable_missing(self):
        # Test with non-existent variable and no default
        with patch.dict(os.environ, {}, clear=True):  # Clear env variables
            with pytest.raises(ValueError):
                get_env_variable("NONEXISTENT_VAR")

    def test_config_variables(self):
        # Test that config variables are loaded from environment
        test_dir = "/tmp/test-project"

        with patch.dict(
            os.environ,
            {
                "BUSINESS_WEB_PROJECT_DIR": test_dir,
                "DEEPSEEK_API_KEY": "test-deepseek-key",
                "TELEGRAM_BOT_TOKEN": "test-bot-token",
            },
        ):
            # Re-import to reload environment variables
            import importlib
            import config

            importlib.reload(config)

            # Check that variables match environment
            assert config.BUSINESS_WEB_PROJECT_DIR == test_dir
