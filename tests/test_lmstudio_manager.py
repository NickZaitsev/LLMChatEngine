from unittest.mock import AsyncMock

import pytest

from lmstudio_manager import LMStudioManager


@pytest.mark.asyncio
async def test_ensure_model_loaded_returns_true_when_model_already_loaded():
    manager = LMStudioManager()
    manager.is_server_running = AsyncMock(return_value=True)
    manager.is_model_loaded = AsyncMock(return_value=True)
    manager.load_model = AsyncMock()

    result = await manager.ensure_model_loaded("test-model", auto_load=False)

    assert result is True
    manager.load_model.assert_not_called()
