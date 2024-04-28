import json
import sys
from unittest.mock import mock_open, patch

import pytest


# Helper function to reload a module within a test
def reload_server():
    if "server" in sys.modules:
        del sys.modules["server"]  # Remove cache
    import server

    return server


@pytest.fixture
def server_module():
    # Patch before import/reload
    config_data = json.dumps(
        {
            "url": "https://example.com",
            "port": 1234,
            "certfile": "/fake/certfile",
            "keyfile": "/fake/keyfile",
            "download_extensions": [".txt", ".jpg"],
        }
    )
    with patch("builtins.open", mock_open(read_data=config_data)), patch(
        "json.load", return_value=json.loads(config_data)
    ):
        server = reload_server()
    return server


def test_config_load_success(server_module):
    # Use the fixture to handle the reload with the mock in place
    assert server_module.URL == "https://example.com"
    assert server_module.PORT == 1234


def test_config_file_missing():
    with patch("builtins.open", side_effect=FileNotFoundError):
        with pytest.raises(SystemExit) as excinfo:
            reload_server()
        assert "Configuration file not found" in str(excinfo.value)


def test_config_invalid_json():
    with patch("builtins.open", mock_open(read_data="{invalid json")):
        with pytest.raises(SystemExit) as excinfo:
            reload_server()
        assert "Configuration file is not valid JSON" in str(excinfo.value)
