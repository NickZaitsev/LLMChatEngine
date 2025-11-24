import asyncio
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from proactive_messaging import ProactiveMessagingService, manage_proactive_messages_async, CADENCE_LEVELS, PROACTIVE_MESSAGING_CADENCES
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
    # User's last message was long ago, they are due for a proactive message
    initial_state = {
        "cadence": "1h",
        "last_proactive_message": (datetime.now() - timedelta(hours=2)).isoformat(),
        "consecutive_outreaches": 1,
        "scheduled_task_id": None, # No task is currently scheduled
        "user_replied": False,
    }
    
    mock_redis_client.get.return_value = ProactiveMessagingService._serialize_state(initial_state)
    mock_redis_client.keys.return_value = [f"proactive_messaging:user:{user_id}".encode('utf-8')]

    mock_task = MagicMock()
    mock_task.id = 'new_test_task_id'
    mock_apply_async.return_value = mock_task

    mock_celery_task = MagicMock()
    mock_celery_task.request.id = "test_beat_task"
    await manage_proactive_messages_async(mock_celery_task)

    # ASSERT: A new task should have been scheduled
    mock_apply_async.assert_called_once()
    
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
    # This user is due, but a task is already scheduled. This can happen if the beat runs
    # again before a previously scheduled task has been cleared.
    initial_state = {
        "cadence": "1h",
        "last_proactive_message": (datetime.now() - timedelta(hours=2)).isoformat(),
        "consecutive_outreaches": 1,
        "scheduled_task_id": "already_existing_task", # A task is already scheduled
        "user_replied": False,
    }
    
    mock_redis_client.get.return_value = ProactiveMessagingService._serialize_state(initial_state)
    mock_redis_client.keys.return_value = [f"proactive_messaging:user:{user_id}".encode('utf-8')]

    mock_celery_task = MagicMock()
    mock_celery_task.request.id = "test_beat_task"
    await manage_proactive_messages_async(mock_celery_task)

    # ASSERT: No new task should be scheduled
    mock_apply_async.assert_not_called()

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
    proactive_service.quiet_hours_start = "02:30"
    proactive_service.quiet_hours_end = "08:00"
    
    assert proactive_service.is_within_quiet_hours(datetime(2023, 1, 1, 5, 0)) is True
    assert proactive_service.is_within_quiet_hours(datetime(2023, 1, 1, 10, 0)) is False
    assert proactive_service.is_within_quiet_hours(datetime(2023, 1, 1, 2, 30)) is True
    assert proactive_service.is_within_quiet_hours(datetime(2023, 1, 1, 8, 0)) is True

def test_adjust_for_quiet_hours(proactive_service):
    """Test adjusting scheduled time for quiet hours."""
    proactive_service.quiet_hours_start = "02:30"
    proactive_service.quiet_hours_end = "08:00"
    
    scheduled_time = datetime(2023, 1, 1, 5, 0)
    adjusted_time = proactive_service.adjust_for_quiet_hours(scheduled_time)
    expected_time = datetime(2023, 1, 1, 8, 5)
    assert adjusted_time == expected_time
    
    scheduled_time_outside = datetime(2023, 1, 1, 10, 0)
    adjusted_time_outside = proactive_service.adjust_for_quiet_hours(scheduled_time_outside)
    assert adjusted_time_outside == scheduled_time_outside