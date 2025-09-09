# Redis-Based Message Queue System

## Overview

This document describes the implementation of a Redis-based message queue system for the AI Girlfriend Bot. The system prevents parallel execution of the `send_ai_response` function for the same user by using user-specific Redis lists with a dispatcher mechanism.

## Architecture

The message queue system consists of the following components:

1. **MessageQueueManager**: Handles enqueuing messages to Redis lists per user
2. **MessageDispatcher**: Processes messages from user queues sequentially


## Implementation Details

### MessageQueueManager

The `MessageQueueManager` class in `message_manager.py` provides methods to enqueue messages for users:

```python
async def enqueue_message(self, user_id: int, chat_id: int, text: str, message_type: str = "regular")
```

Messages are stored in Redis lists with keys in the format `queue:{user_id}`.

### MessageDispatcher

The `MessageDispatcher` class in `message_manager.py` processes messages from user queues:

1. Monitors active user queues
2. Processes messages sequentially for each user
3. Implements delays between messages
4. Handles errors with retry mechanism and dead letter queues
## Integration

### Bot Integration

In `bot.py`, the `send_ai_response` calls in `_dispatch_buffered_message` have been replaced with calls to `message_queue_manager.enqueue_message`.

### Proactive Messaging Integration

In `proactive_messaging.py`, the `send_ai_response` calls in `send_proactive_message` have been replaced with calls to `message_queue_manager.enqueue_message`.

## Configuration

The system is configured through the following environment variables:

```env
MESSAGE_QUEUE_REDIS_URL=redis://redis:6379/0
MESSAGE_QUEUE_MAX_RETRIES=3
MESSAGE_QUEUE_LOCK_TIMEOUT=30
MESSAGE_QUEUE_DISPATCHER_INTERVAL=0.1
```

## Testing

Unit tests for the message queue system are located in:
- `tests/test_message_queue.py`
- `tests/test_message_dispatcher.py`
- `tests/test_delay_calculator.py`

Integration tests are located in:
- `tests/test_message_queue_integration.py`

## Benefits

1. **Prevents Parallel Execution**: Ensures only one message is processed per user at a time
2. **Maintains Message Order**: Messages are processed in the order they were received
3. **Error Handling**: Implements retry mechanism and dead letter queues for failed messages
4. **Scalability**: Uses Redis for efficient queue management
5. **Backward Compatibility**: Maintains existing functionality while adding queuing mechanism