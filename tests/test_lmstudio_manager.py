from types import SimpleNamespace
from unittest.mock import patch

import pytest

from lmstudio_manager import LMStudioManager


@pytest.mark.asyncio
async def test_is_server_running_uses_executor_request():
    manager = LMStudioManager(base_url="http://lmstudio.local", timeout=1)

    with patch("lmstudio_manager.requests.get", return_value=SimpleNamespace(status_code=200)) as get:
        assert await manager.is_server_running() is True

    get.assert_called_once_with("http://lmstudio.local/v1/models", timeout=5)
