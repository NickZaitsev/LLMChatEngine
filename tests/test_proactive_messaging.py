import asyncio
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from proactive_messaging import (
    ProactiveMessagingService,
    manage_proactive_messages_async,
    send_proactive_message_async,
    CADENCE_LEVELS,
    PROACTIVE_MESSAGING_CADENCES,
)
from config import PROACTIVE_MESSAGING_QUIET_HOURS_START, PROACTIVE_MESSAGING_QUIET_HOURS_END

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
@patch('proactive_messaging.send_proactive_message.apply_async')
async def test_manage_proactive_messages_schedules_due_user(mock_apply_async, proactive_service, mock_redis_client):
    """
    Test that the centralized `manage_proactive_messages` task correctly schedules a message for a user who is due.
    """
    user_id = 123
    bot_id = "11111111-1111-1111-1111-111111111111"
    # User's last message was long ago, they are due for a proactive message
    initial_state = {
        "cadence": "1h",
        "last_proactive_message": (datetime.now() - timedelta(hours=2)).isoformat(),
        "consecutive_outreaches": 1,
        "scheduled_task_id": None, # No task is currently scheduled
        "user_replied": False,
        "bot_id": bot_id,
    }
    
    mock_redis_client.get.return_value = ProactiveMessagingService._serialize_state(initial_state)
    mock_redis_client.keys.return_value = [f"proactive_messaging:user:{user_id}:{bot_id}".encode('utf-8')]

    mock_task = MagicMock()
    mock_task.id = 'new_test_task_id'
    mock_apply_async.return_value = mock_task

    mock_celery_task = MagicMock()
    mock_celery_task.request.id = "test_beat_task"
    await manage_proactive_messages_async(mock_celery_task)

    # ASSERT: A new task should have been scheduled
    mock_apply_async.assert_called_once()
    _, kwargs = mock_apply_async.call_args
    assert kwargs["args"] == [user_id, bot_id]
    
    # Verify the user's state was updated with the new task ID
    args, kwargs = mock_redis_client.set.call_args
    final_state = json.loads(args[1])
    assert final_state['scheduled_task_id'] == 'new_test_task_id'

@pytest.mark.asyncio
@patch('proactive_messaging.send_proactive_message.apply_async')
async def test_manage_proactive_messages_skips_scheduled_user(mock_apply_async, proactive_service, mock_redis_client):
    """
    Test that `manage_proactive_messages` correctly skips a user who already has a task scheduled.
    """
    user_id = 456
    bot_id = "22222222-2222-2222-2222-222222222222"
    # This user is due, but a task is already scheduled. This can happen if the beat runs
    # again before a previously scheduled task has been cleared.
    initial_state = {
        "cadence": "1h",
        "last_proactive_message": (datetime.now() - timedelta(hours=2)).isoformat(),
        "consecutive_outreaches": 1,
        "scheduled_task_id": "already_existing_task", # A task is already scheduled
        "scheduled_time": (datetime.now() + timedelta(minutes=5)).isoformat(),
        "user_replied": False,
        "bot_id": bot_id,
    }
    
    mock_redis_client.get.return_value = ProactiveMessagingService._serialize_state(initial_state)
    mock_redis_client.keys.return_value = [f"proactive_messaging:user:{user_id}:{bot_id}".encode('utf-8')]

    mock_celery_task = MagicMock()
    mock_celery_task.request.id = "test_beat_task"
    await manage_proactive_messages_async(mock_celery_task)

    # ASSERT: No new task should be scheduled
    mock_apply_async.assert_not_called()


@pytest.mark.asyncio
@patch('proactive_messaging.send_proactive_message.apply_async')
async def test_manage_proactive_messages_reschedules_stale_task(mock_apply_async, proactive_service, mock_redis_client):
    user_id = 457
    bot_id = "33333333-3333-3333-3333-333333333333"
    stale_time = datetime.now() - timedelta(hours=2)
    initial_state = {
        "cadence": "1h",
        "last_proactive_message": (datetime.now() - timedelta(hours=3)).isoformat(),
        "consecutive_outreaches": 1,
        "scheduled_task_id": "stale-task",
        "scheduled_time": stale_time.isoformat(),
        "user_replied": False,
        "bot_id": bot_id,
    }

    mock_redis_client.get.return_value = ProactiveMessagingService._serialize_state(initial_state)
    mock_redis_client.keys.return_value = [f"proactive_messaging:user:{user_id}:{bot_id}".encode("utf-8")]

    mock_task = MagicMock()
    mock_task.id = "replacement-task"
    mock_apply_async.return_value = mock_task

    mock_celery_task = MagicMock()
    mock_celery_task.request.id = "test_beat_task"
    await manage_proactive_messages_async(mock_celery_task)

    mock_apply_async.assert_called_once()
    final_state = json.loads(mock_redis_client.set.call_args[0][1])
    assert final_state["scheduled_task_id"] == "replacement-task"
    assert final_state["scheduled_time"] is not None

def test_handle_user_message_resets_cadence(proactive_service, mock_redis_client):
    """Test that handling a user message simply resets the user's state."""
    user_id = 789
    # Simulate a user in a high-cadence state
    mock_redis_client.get.return_value = json.dumps({
        'cadence': '1d',
        'consecutive_outreaches': 3,
        'scheduled_task_id': 'some_old_task'
    })
    
    proactive_service.handle_user_message(user_id)
    
    # ASSERT: The only thing that should happen is the state is reset.
    state_str = mock_redis_client.set.call_args[0][1]
    state = json.loads(state_str)
    
    assert state['cadence'] == CADENCE_LEVELS[0]
    assert state['consecutive_outreaches'] == 0
    assert state['scheduled_task_id'] is None

def test_handle_user_message_persists_bot_id(proactive_service, mock_redis_client):
    """Test that handling a user message stores the active bot ID for multi-bot routing."""
    user_id = 790
    bot_id = "8c52d8d6-f8c7-4523-8f4c-44d468704d2c"

    proactive_service.handle_user_message(user_id, bot_id=bot_id)

    state_str = mock_redis_client.set.call_args[0][1]
    state = json.loads(state_str)

    assert state['bot_id'] == bot_id

@pytest.mark.asyncio
@patch('proactive_messaging.send_proactive_message.apply_async')
async def test_manage_proactive_messages_schedules_same_user_per_bot(mock_apply_async, proactive_service, mock_redis_client):
    """Test that the same Telegram user can have independent proactive schedules per bot."""
    user_id = 901
    bot_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    bot_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    states = {
        proactive_service._state_key(user_id, bot_a): {
            "cadence": "1h",
            "last_proactive_message": (datetime.now() - timedelta(hours=2)).isoformat(),
            "consecutive_outreaches": 0,
            "scheduled_task_id": None,
            "user_replied": False,
            "bot_id": bot_a,
        },
        proactive_service._state_key(user_id, bot_b): {
            "cadence": "1h",
            "last_proactive_message": (datetime.now() - timedelta(hours=2)).isoformat(),
            "consecutive_outreaches": 0,
            "scheduled_task_id": None,
            "user_replied": False,
            "bot_id": bot_b,
        },
    }

    def mock_get(key):
        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        state = states.get(key_str)
        return ProactiveMessagingService._serialize_state(state) if state else None

    def mock_set(key, value):
        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        states[key_str] = json.loads(value)
        return True

    mock_redis_client.get.side_effect = mock_get
    mock_redis_client.set.side_effect = mock_set
    mock_redis_client.keys.return_value = [key.encode('utf-8') for key in states.keys()]

    mock_task_a = MagicMock()
    mock_task_a.id = 'task-a'
    mock_task_b = MagicMock()
    mock_task_b.id = 'task-b'
    mock_apply_async.side_effect = [mock_task_a, mock_task_b]

    mock_celery_task = MagicMock()
    mock_celery_task.request.id = "test_beat_task"
    await manage_proactive_messages_async(mock_celery_task)

    assert mock_apply_async.call_count == 2
    scheduled_args = [call.kwargs["args"] for call in mock_apply_async.call_args_list]
    assert [user_id, bot_a] in scheduled_args
    assert [user_id, bot_b] in scheduled_args

def test_get_next_interval(proactive_service):
    """Test cadence escalation logic."""
    assert proactive_service.get_next_interval(CADENCE_LEVELS[0]) == CADENCE_LEVELS[1]
    assert proactive_service.get_next_interval(CADENCE_LEVELS[1]) == CADENCE_LEVELS[2]
    assert proactive_service.get_next_interval(CADENCE_LEVELS[-1]) == CADENCE_LEVELS[-1]
    assert proactive_service.get_next_interval('invalid_cadence') == CADENCE_LEVELS[0]

def test_get_interval_with_jitter(proactive_service):
    """Test that jitter is applied correctly."""
    for cadence_config in PROACTIVE_MESSAGING_CADENCES:
        cadence_name = cadence_config["name"]
        interval = cadence_config["interval"]
        jitter = cadence_config["jitter"]
        
        results = [proactive_service.get_interval_with_jitter(cadence_name) for _ in range(100)]
        
        assert all(interval - jitter <= r <= interval + jitter for r in results)
        if jitter > 0:
            assert len(set(results)) > 1

def test_is_within_quiet_hours(proactive_service):
    """Test checking if time is within quiet hours."""
    proactive_service.quiet_hours_enabled = True
    proactive_service.quiet_hours_start = "02:30"
    proactive_service.quiet_hours_end = "08:00"
    
    assert proactive_service.is_within_quiet_hours(datetime(2023, 1, 1, 5, 0)) is True
    assert proactive_service.is_within_quiet_hours(datetime(2023, 1, 1, 10, 0)) is False
    assert proactive_service.is_within_quiet_hours(datetime(2023, 1, 1, 2, 30)) is True
    assert proactive_service.is_within_quiet_hours(datetime(2023, 1, 1, 8, 0)) is True

def test_adjust_for_quiet_hours(proactive_service):
    """Test adjusting scheduled time for quiet hours."""
    proactive_service.quiet_hours_enabled = True
    proactive_service.quiet_hours_start = "02:30"
    proactive_service.quiet_hours_end = "08:00"
    
    scheduled_time = datetime(2023, 1, 1, 5, 0)
    adjusted_time = proactive_service.adjust_for_quiet_hours(scheduled_time)
    expected_time = datetime(2023, 1, 1, 8, 5)
    assert adjusted_time == expected_time
    
    scheduled_time_outside = datetime(2023, 1, 1, 10, 0)
    adjusted_time_outside = proactive_service.adjust_for_quiet_hours(scheduled_time_outside)
    assert adjusted_time_outside == scheduled_time_outside


@pytest.mark.asyncio
async def test_send_proactive_message_uses_bot_scoped_ai_runtime(proactive_service):
    user_id = 321
    bot_id = "11111111-1111-1111-1111-111111111111"
    task = MagicMock()
    task.request.id = "task-123"

    proactive_service._get_user_state = MagicMock(return_value={
        "scheduled_task_id": "task-123",
        "cadence": CADENCE_LEVELS[0],
        "consecutive_outreaches": 0,
        "bot_id": bot_id,
    })
    proactive_service._set_user_state = MagicMock()

    conversation = MagicMock()
    conversation.id = "conv-1"
    conversation.bot_id = None

    app_context = MagicMock()
    app_context.get_ai_runtime_for_bot = AsyncMock(return_value=("bot-scoped-ai", None))
    app_context.conversation_manager.get_formatted_conversation_async = AsyncMock(return_value=[])
    app_context.conversation_manager._ensure_user_and_conversation = AsyncMock(return_value=conversation)
    app_context.conversation_manager.add_message_async = AsyncMock()
    app_context.message_queue_manager.enqueue_message = AsyncMock()
    app_context.typing_manager = MagicMock()

    with patch("proactive_messaging.get_app_context", AsyncMock(return_value=app_context)), \
         patch("proactive_messaging.generate_ai_response", AsyncMock(return_value="Hello there")), \
         patch("proactive_messaging.clean_ai_response", return_value="Hello there"), \
         patch("proactive_messaging.Bot"):
        await send_proactive_message_async(task, user_id, bot_id=bot_id)

    app_context.get_ai_runtime_for_bot.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_proactive_message_does_not_advance_state_on_failure(proactive_service):
    user_id = 654
    bot_id = "11111111-1111-1111-1111-111111111111"
    task = MagicMock()
    task.request.id = "task-999"

    proactive_service._get_user_state = MagicMock(return_value={
        "scheduled_task_id": "task-999",
        "scheduled_time": datetime.now(),
        "cadence": CADENCE_LEVELS[0],
        "consecutive_outreaches": 1,
        "bot_id": bot_id,
    })
    proactive_service._set_user_state = MagicMock()

    conversation = MagicMock()
    conversation.id = "conv-1"
    conversation.bot_id = None

    app_context = MagicMock()
    app_context.get_ai_runtime_for_bot = AsyncMock(return_value=("bot-scoped-ai", None))
    app_context.conversation_manager._ensure_user_and_conversation = AsyncMock(return_value=conversation)
    app_context.conversation_manager.get_formatted_conversation_async = AsyncMock(return_value=[])

    with patch("proactive_messaging.get_app_context", AsyncMock(return_value=app_context)), \
         patch("proactive_messaging.generate_ai_response", AsyncMock(side_effect=RuntimeError("llm failed"))), \
         patch("proactive_messaging.Bot"):
        with pytest.raises(RuntimeError):
            await send_proactive_message_async(task, user_id, bot_id=bot_id)

    proactive_service._set_user_state.assert_not_called()
