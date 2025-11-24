"""
Celery Configuration for Proactive Messaging System

This module contains the Celery configuration settings for the proactive messaging system.
"""

# Celery Configuration
broker_url = 'redis://redis:6379/0'
result_backend = 'redis://redis:6379/0'

# Task Serialization
task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']

# Timezone and Schedule
timezone = 'UTC'
enable_utc = True

# Task Acknowledgment
task_acks_late = True
worker_prefetch_multiplier = 1

# Persistent Revokes
worker_persistent_revokes = True

# Task Result Expiration
result_expires = 3600  # 1 hour

# Task Routing
task_routes = {
    'proactive_messaging.send_proactive_message': {'queue': 'proactive_messaging'},
    'proactive_messaging.manage_proactive_messages': {'queue': 'proactive_messaging'},
    'memory.tasks.create_conversation_summary': {'queue': 'memory_tasks'},
}

# Task Queues
task_default_queue = 'proactive_messaging'
task_queues = {
    'proactive_messaging': {
        'exchange': 'proactive_messaging',
        'routing_key': 'proactive_messaging',
    },
    'memory_tasks': {
        'exchange': 'memory_tasks',
        'routing_key': 'memory_tasks',
    },
}