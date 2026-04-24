import asyncio
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from proactive_messaging import ProactiveMessagingService, manage_proactive_messages_async

@pytest.fixture
def mock_redis_client():
    """Fixture for a mock Redis client."""
    client = MagicMock()
    client.get.return_value = None
    client.set.return_value = True
    client.keys.return_value = []
    return client

@pytest.fixture
def proactive_service(mock_redis_client):
    """
    Fixture that provides a ProactiveMessagingService instance with a mocked Redis client,
    and patches the singleton instance in the module.
    """
    # Create an instance of the service with a mocked redis client
    service = ProactiveMessagingService()
    service.redis_client = mock_redis_client

    # Patch the singleton instance in the module where it's defined
    with patch('proactive_messaging.proactive_messaging_service', service):
        # Also patch the logger to suppress output during tests
        with patch('proactive_messaging.logger'):
            yield service

@pytest.mark.asyncio
async def test_concurrent_scheduling_creates_only_one_task(proactive_service, mock_redis_client):
    """
    Verify that even with multiple concurrent triggers, only one proactive message
    task is scheduled, preventing the race condition.
    """
    user_id = 12345
    bot_id = "33333333-3333-3333-3333-333333333333"
    initial_state = {
        "cadence": "1h",
        "last_proactive_message": (datetime.now() - timedelta(hours=2)).isoformat(),
        "consecutive_outreaches": 0,
        "scheduled_task_id": None, # Critically, no task is currently scheduled
        "user_replied": False,
        "bot_id": bot_id,
    }
    state_key = f"proactive_messaging:user:{user_id}:{bot_id}"
    redis_state = {state_key: initial_state.copy()}

    def mock_get(key):
        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        state = redis_state.get(key_str)
        return ProactiveMessagingService._serialize_state(state) if state else None

    def mock_set(key, value):
        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        redis_state[key_str] = json.loads(value)
        return True

    lock_held = False

    def mock_lock(*args, **kwargs):
        lock = MagicMock()

        def acquire(blocking=False):
            nonlocal lock_held
            if lock_held:
                return False
            lock_held = True
            return True

        def release():
            nonlocal lock_held
            lock_held = False

        lock.acquire.side_effect = acquire
        lock.release.side_effect = release
        return lock

    mock_redis_client.get.side_effect = mock_get
    mock_redis_client.set.side_effect = mock_set
    mock_redis_client.keys.return_value = [state_key.encode('utf-8')]
    mock_redis_client.lock.side_effect = mock_lock

    # Mock the Celery task scheduling
    with patch('proactive_messaging.send_proactive_message.apply_async') as mock_apply_async:
        # Create a mock task object with an ID
        mock_task = MagicMock()
        mock_task.id = "mock_task_id_123"
        mock_apply_async.return_value = mock_task

        # Simulate two 'manage_proactive_messages' tasks running almost simultaneously
        # This is the scenario that previously caused the race condition.
        mock_celery_task = MagicMock()
        mock_celery_task.request.id = "test_beat_task_1"

        mock_celery_task_2 = MagicMock()
        mock_celery_task_2.request.id = "test_beat_task_2"

        # Run them concurrently
        await asyncio.gather(
            manage_proactive_messages_async(mock_celery_task),
            manage_proactive_messages_async(mock_celery_task_2)
        )

        # ASSERT: Even with two concurrent runs, apply_async should only be called ONCE.
        # This is the key validation. The first run schedules a task and sets 'scheduled_task_id'.
        # The second run should see that 'scheduled_task_id' is now set and should immediately skip the user.
        mock_apply_async.assert_called_once()
        _, kwargs = mock_apply_async.call_args
        assert kwargs["args"] == [user_id, bot_id]

        # Additionally, verify that the final state in Redis correctly records the scheduled task ID.
        # We need to check the arguments passed to the 'set' method.
        # The first call to 'get' is for reading, the second call is inside the loop.
        # The final 'set' call should contain our new task ID.
        final_state = redis_state[state_key]

        assert final_state['scheduled_task_id'] == "mock_task_id_123"
