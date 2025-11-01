"""
Proactive Messaging System for AI Girlfriend Bot

This module handles the scheduling and sending of proactive messages to users
based on configurable intervals, jitter, quiet hours, and cadence escalation.
"""

import asyncio
import logging
import random
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from celery import Celery
from celery.schedules import crontab
import redis
import json

from config import (
    PROACTIVE_MESSAGING_ENABLED,
    PROACTIVE_MESSAGING_REDIS_URL,
    PROACTIVE_MESSAGING_INTERVAL_1H,
    PROACTIVE_MESSAGING_INTERVAL_9H,
    PROACTIVE_MESSAGING_INTERVAL_1D,
    PROACTIVE_MESSAGING_INTERVAL_1W,
    PROACTIVE_MESSAGING_INTERVAL_1MO,
    PROACTIVE_MESSAGING_JITTER_1H,
    PROACTIVE_MESSAGING_JITTER_9H,
    PROACTIVE_MESSAGING_JITTER_1D,
    PROACTIVE_MESSAGING_JITTER_1W,
    PROACTIVE_MESSAGING_JITTER_1MO,
    PROACTIVE_MESSAGING_QUIET_HOURS_ENABLED,
    PROACTIVE_MESSAGING_QUIET_HOURS_START,
    PROACTIVE_MESSAGING_QUIET_HOURS_END,
    PROACTIVE_MESSAGING_MAX_CONSECUTIVE_OUTREACHES,
    PROACTIVE_MESSAGING_PROMPT,
    PROACTIVE_MESSAGING_RESTART_DELAY_MAX,
)

# Import AppContext for shared services
from app_context import get_app_context, AppContext

# Import message queue manager and related functions
from message_manager import clean_ai_response, generate_ai_response


# Import celery configuration
import celeryconfig

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize Celery
celery_app = Celery('proactive_messaging')
celery_app.config_from_object(celeryconfig)

# Cadence levels
CADENCE_LEVELS = [
    '1h',   # 1 hour
    '9h',   # 9 hours
    '1d',   # 1 day
    '1w',   # 1 week
    '1mo'   # 1 month
]

# Interval mappings
INTERVALS = {
    '1h': PROACTIVE_MESSAGING_INTERVAL_1H,
    '9h': PROACTIVE_MESSAGING_INTERVAL_9H,
    '1d': PROACTIVE_MESSAGING_INTERVAL_1D,
    '1w': PROACTIVE_MESSAGING_INTERVAL_1W,
    '1mo': PROACTIVE_MESSAGING_INTERVAL_1MO
}

# Jitter mappings
JITTERS = {
    '1h': PROACTIVE_MESSAGING_JITTER_1H,
    '9h': PROACTIVE_MESSAGING_JITTER_9H,
    '1d': PROACTIVE_MESSAGING_JITTER_1D,
    '1w': PROACTIVE_MESSAGING_JITTER_1W,
    '1mo': PROACTIVE_MESSAGING_JITTER_1MO
}

class ProactiveMessagingService:
    """Service for handling proactive messaging functionality."""
    
    def __init__(self):
        """Initialize the proactive messaging service."""
        self.enabled = PROACTIVE_MESSAGING_ENABLED
        self.redis_url = PROACTIVE_MESSAGING_REDIS_URL
        self.quiet_hours_enabled = PROACTIVE_MESSAGING_QUIET_HOURS_ENABLED
        self.quiet_hours_start = PROACTIVE_MESSAGING_QUIET_HOURS_START
        self.quiet_hours_end = PROACTIVE_MESSAGING_QUIET_HOURS_END
        self.max_consecutive_outreaches = PROACTIVE_MESSAGING_MAX_CONSECUTIVE_OUTREACHES
        
        # Log configuration
        logger.info(f"Proactive Messaging Service Configuration:")
        logger.info(f"  Enabled: {self.enabled}")
        logger.info(f"  Redis URL: {self.redis_url}")
        logger.info(f"  Quiet Hours Enabled: {self.quiet_hours_enabled}")
        logger.info(f"  Quiet Hours: {self.quiet_hours_start} - {self.quiet_hours_end}")
        logger.info(f"  Max Consecutive Outreaches: {self.max_consecutive_outreaches}")
        logger.info(f"  Intervals: 1H={PROACTIVE_MESSAGING_INTERVAL_1H}s, 9H={PROACTIVE_MESSAGING_INTERVAL_9H}s, 1D={PROACTIVE_MESSAGING_INTERVAL_1D}s, 1W={PROACTIVE_MESSAGING_INTERVAL_1W}s, 1MO={PROACTIVE_MESSAGING_INTERVAL_1MO}s")
        logger.info(f"  Jitter: 1H={PROACTIVE_MESSAGING_JITTER_1H}s, 9H={PROACTIVE_MESSAGING_JITTER_9H}s, 1D={PROACTIVE_MESSAGING_JITTER_1D}s, 1W={PROACTIVE_MESSAGING_JITTER_1W}s, 1MO={PROACTIVE_MESSAGING_JITTER_1MO}s")
        
        # Initialize Redis client
        self.redis_client = redis.from_url(self.redis_url)
        logger.info("Redis client initialized")
        
        # Message queue manager is now retrieved from AppContext, not initialized here
        self.message_queue_manager = None

    async def _get_app_context(self) -> AppContext:
        """Helper to get initialized app context."""
        app_context = await get_app_context()
        if self.message_queue_manager is None:
            self.message_queue_manager = app_context.message_queue_manager
        return app_context
        
    def _get_user_state(self, user_id: int) -> dict:
        """
        Get user state from Redis.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            User state dictionary
        """
        try:
            state_json = self.redis_client.get(f"proactive_messaging:user:{user_id}")
            if state_json:
                state = json.loads(state_json)
                # Convert datetime strings back to datetime objects
                if 'last_proactive_message' in state and state['last_proactive_message']:
                    try:
                        state['last_proactive_message'] = datetime.fromisoformat(state['last_proactive_message'])
                    except ValueError:
                        # If parsing fails, remove the field
                        state['last_proactive_message'] = None
                if 'scheduled_time' in state and state['scheduled_time']:
                    try:
                        state['scheduled_time'] = datetime.fromisoformat(state['scheduled_time'])
                    except ValueError:
                        # If parsing fails, remove the field
                        state['scheduled_time'] = None
                # scheduled_task_id is already a string, no conversion needed
                return state
            return {}
        except Exception as e:
            logger.error(f"Error getting user state for user {user_id} from Redis: {e}")
            return {}

    def _set_user_state(self, user_id: int, state: dict):
        """
        Set user state in Redis.
        
        Args:
            user_id: Telegram user ID
            state: User state dictionary
        """
        try:
            # Create a copy of the state to avoid modifying the original
            state_copy = state.copy()
            # Convert datetime objects to ISO format strings for JSON serialization
            if 'last_proactive_message' in state_copy and isinstance(state_copy['last_proactive_message'], datetime):
                state_copy['last_proactive_message'] = state_copy['last_proactive_message'].isoformat()
            if 'scheduled_time' in state_copy and isinstance(state_copy['scheduled_time'], datetime):
                state_copy['scheduled_time'] = state_copy['scheduled_time'].isoformat()
            # scheduled_task_id is already a string, no conversion needed
                
            state_json = json.dumps(state_copy, default=str)
            self.redis_client.set(f"proactive_messaging:user:{user_id}", state_json)
        except Exception as e:
            logger.error(f"Error setting user state for user {user_id} in Redis: {e}")

    def _get_all_user_states(self):
        """
        Get all user states from Redis.
        
        Returns:
            Dictionary of user states keyed by user ID
        """
        try:
            pattern = "proactive_messaging:user:*"
            all_keys = self.redis_client.keys(pattern)
            
            user_states = {}
            for key in all_keys:
                try:
                    key_str = key.decode('utf-8')
                    key_segments = key_str.split(':')
                    
                    # Ensure this is a user state key (e.g., "proactive_messaging:user:12345")
                    if len(key_segments) != 3:
                        logger.debug(f"Skipping non-user-state key: {key_str}")
                        continue
                        
                    user_id_str = key_segments[-1]
                    if not user_id_str.isdigit():
                        logger.warning(f"Skipping malformed user key in Redis: {key_str}")
                        continue
                        
                    user_id = int(user_id_str)
                    state_json = self.redis_client.get(key)
                    if state_json:
                        state = json.loads(state_json)
                        # Convert datetime strings back to datetime objects
                        if 'last_proactive_message' in state and state['last_proactive_message']:
                            try:
                                state['last_proactive_message'] = datetime.fromisoformat(state['last_proactive_message'])
                            except (ValueError, TypeError):
                                state['last_proactive_message'] = None
                        if 'scheduled_time' in state and state['scheduled_time']:
                            try:
                                state['scheduled_time'] = datetime.fromisoformat(state['scheduled_time'])
                            except (ValueError, TypeError):
                                state['scheduled_time'] = None
                        user_states[user_id] = state
                except Exception as e:
                    logger.error(f"Error processing key {key}: {e}")
                    continue
            
            return user_states
        except Exception as e:
            logger.error(f"Error getting all user states from Redis: {e}")
            return {}

    def _is_scheduled_time_in_past(self, scheduled_time):
        """
        Check if the scheduled time is in the past.
        
        Args:
            scheduled_time: Scheduled datetime
            
        Returns:
            True if scheduled time is in the past, False otherwise
        """
        if not scheduled_time:
            return False
        return scheduled_time < datetime.now()

    
    def _revoke_user_tasks(self, user_id: int, state: dict, message_type: str = "RegularReachout", exclude_task_id: str = None):
        """
        Revoke all existing scheduled tasks for a user of a specific message type.

        Args:
            user_id: Telegram user ID
            state: User state dictionary containing task information
            message_type: Type of message tasks to revoke (default: "RegularReachout")
            exclude_task_id: Task ID to exclude from revocation (default: None)
        """
        try:
            # Get all task IDs for the user from Redis for the specific message type
            task_key = f"proactive_messaging:user:{user_id}:tasks:{message_type}"
            task_ids = self.redis_client.smembers(task_key)
            
            revoked_count = 0
            for task_id_bytes in task_ids:
                # Handle None values and convert bytes to string
                if task_id_bytes is None:
                    continue  # Skip None values
                task_id = task_id_bytes.decode('utf-8') if isinstance(task_id_bytes, bytes) else str(task_id_bytes)
                if not task_id:  # Skip empty task IDs
                    continue
                if exclude_task_id and task_id == exclude_task_id:
                    logger.debug(f"Skipping revocation of current task {task_id} for user {user_id}")
                    continue
                logger.info(f"Revoking scheduled task {task_id} for user {user_id} of type {message_type}")
                # Revoke the Celery task
                celery_app.control.revoke(task_id, terminate=True)
                # Track the revoked task in Redis
                self._add_revoked_task(user_id, task_id, message_type)
                revoked_count += 1
                logger.info(f"Revoked scheduled task {task_id} for user {user_id} of type {message_type}")
            
            # Clear all task IDs from Redis for this message type
            if task_ids:
                self.redis_client.delete(task_key)
                logger.info(f"Revoked {revoked_count} {message_type} tasks for user {user_id} and cleared task list")
            else:
                logger.debug(f"No scheduled {message_type} tasks found for user {user_id}")
        except Exception as e:
            logger.error(f"Error revoking {message_type} tasks for user {user_id}: {e}")
            # Re-raise the exception so callers can handle it if needed
            raise

    
    def _revoke_all_user_tasks(self, user_id: int, state: dict):
        """
        Revoke all existing scheduled tasks for a user regardless of message type.
        
        Args:
            user_id: Telegram user ID
            state: User state dictionary containing task information
        """
        try:
            # Get all task keys for the user from Redis
            pattern = f"proactive_messaging:user:{user_id}:tasks:*"
            task_keys = self.redis_client.keys(pattern)
            
            total_revoked_count = 0
            for task_key in task_keys:
                task_ids = self.redis_client.smembers(task_key)
                
                revoked_count = 0
                for task_id_bytes in task_ids:
                    task_id = task_id_bytes.decode('utf-8') if isinstance(task_id_bytes, bytes) else task_id_bytes
                    # Extract message type from key
                    message_type = task_key.decode('utf-8').split(':')[-1] if isinstance(task_key, bytes) else task_key.split(':')[-1]
                    logger.info(f"Revoking scheduled task {task_id} for user {user_id} of type {message_type}")
                    # Revoke the Celery task
                    celery_app.control.revoke(task_id, terminate=True)
                    # Track the revoked task in Redis
                    self._add_revoked_task(user_id, task_id, message_type)
                    revoked_count += 1
                    logger.info(f"Revoked scheduled task {task_id} for user {user_id} of type {message_type}")
                
                # Clear all task IDs from Redis for this message type
                if task_ids:
                    self.redis_client.delete(task_key)
                    total_revoked_count += revoked_count
                    logger.info(f"Revoked {revoked_count} tasks of type {message_type} for user {user_id} and cleared task list")
                else:
                    logger.debug(f"No scheduled tasks of type {message_type} found for user {user_id}")
            
            logger.info(f"Revoked a total of {total_revoked_count} tasks for user {user_id} across all message types")
        except Exception as e:
            logger.error(f"Error revoking all tasks for user {user_id}: {e}")
    
    def _add_task_id(self, user_id: int, task_id: str, message_type: str = "RegularReachout"):
        """
        Add a task ID to the user's task list in Redis for a specific message type.
        
        Args:
            user_id: Telegram user ID
            task_id: Celery task ID
            message_type: Type of message (default: "RegularReachout")
        """
        try:
            task_key = f"proactive_messaging:user:{user_id}:tasks:{message_type}"
            self.redis_client.sadd(task_key, task_id)
            logger.debug(f"Added task {task_id} of type {message_type} to user {user_id}'s task list")
        except Exception as e:
            logger.error(f"Error adding task ID for user {user_id} of type {message_type}: {e}")
    def _add_revoked_task(self, user_id: int, task_id: str, message_type: str = "RegularReachout"):
        """
        Add a revoked task ID to a set in Redis to track revoked tasks.
        
        Args:
            user_id: Telegram user ID
            task_id: Celery task ID
            message_type: Type of message (default: "RegularReachout")
        """
        try:
            revoked_key = f"proactive_messaging:user:{user_id}:revoked_tasks:{message_type}"
            self.redis_client.sadd(revoked_key, task_id)
            logger.debug(f"Added revoked task {task_id} of type {message_type} for user {user_id}")
            
            # Set expiration for the revoked tasks set (24 hours)
            self.redis_client.expire(revoked_key, 86400)
        except Exception as e:
            logger.error(f"Error adding revoked task ID for user {user_id} of type {message_type}: {e}")
    
    def _is_task_revoked(self, user_id: int, task_id: str, message_type: str = "RegularReachout") -> bool:
        """
        Check if a task has been revoked.
        
        Args:
            user_id: Telegram user ID
            task_id: Celery task ID
            message_type: Type of message (default: "RegularReachout")
            
        Returns:
            True if task has been revoked, False otherwise
        """
        try:
            revoked_key = f"proactive_messaging:user:{user_id}:revoked_tasks:{message_type}"
            return self.redis_client.sismember(revoked_key, task_id)
        except Exception as e:
            logger.error(f"Error checking if task {task_id} is revoked for user {user_id} of type {message_type}: {e}")
            return False
    
    def parse_time(self, time_str: str) -> tuple:
        """
        Parse time string in HH:MM format to hours and minutes.
        
        Args:
            time_str: Time string in HH:MM format
            
        Returns:
            Tuple of (hours, minutes)
        """
        try:
            hours, minutes = map(int, time_str.split(':'))
            return hours, minutes
        except ValueError:
            logger.error(f"Invalid time format: {time_str}")
            return 0, 0
    
    def is_within_quiet_hours(self, check_time: datetime = None) -> bool:
        """
        Check if the given time is within quiet hours.

        Args:
            check_time: Time to check (defaults to current time)

        Returns:
            True if within quiet hours, False otherwise
        """
        if not self.quiet_hours_enabled:
            return False

        if not check_time:
            check_time = datetime.now()

        start_hours, start_minutes = self.parse_time(self.quiet_hours_start)
        end_hours, end_minutes = self.parse_time(self.quiet_hours_end)

        start_time = check_time.replace(hour=start_hours, minute=start_minutes, second=0, microsecond=0)
        end_time = check_time.replace(hour=end_hours, minute=end_minutes, second=0, microsecond=0)

        # Handle case where quiet hours cross midnight
        if end_time <= start_time:
            return check_time >= start_time or check_time <= end_time
        else:
            return start_time <= check_time <= end_time
    
    def adjust_for_quiet_hours(self, scheduled_time: datetime) -> datetime:
        """
        Adjust scheduled time if it falls within quiet hours.
        
        Args:
            scheduled_time: Originally scheduled time
            
        Returns:
            Adjusted time that's outside quiet hours
        """
        logger.debug(f"Checking if {scheduled_time} is within quiet hours ({self.quiet_hours_start} - {self.quiet_hours_end})")
        
        if not self.is_within_quiet_hours(scheduled_time):
            logger.debug(f"Time {scheduled_time} is not within quiet hours, no adjustment needed")
            return scheduled_time
        
        logger.info(f"Time {scheduled_time} is within quiet hours, adjusting...")
        
        # Move to end of quiet hours
        end_hours, end_minutes = self.parse_time(self.quiet_hours_end)
        adjusted_time = scheduled_time.replace(hour=end_hours, minute=end_minutes, second=0, microsecond=0)
        
        # Add a small buffer to ensure we're outside quiet hours
        adjusted_time += timedelta(minutes=5)
        
        logger.info(f"Adjusted time from {scheduled_time} to {adjusted_time}")
        return adjusted_time
    
    def get_next_interval(self, current_cadence: str) -> str:
        """
        Get the next interval in the cadence escalation.
        
        Args:
            current_cadence: Current cadence level
            
        Returns:
            Next cadence level
        """
        try:
            current_index = CADENCE_LEVELS.index(current_cadence)
            # Don't go beyond the last level
            next_index = min(current_index + 1, len(CADENCE_LEVELS) - 1)
            return CADENCE_LEVELS[next_index]
        except ValueError:
            # If current_cadence is not in the list, start from the beginning
            return CADENCE_LEVELS[0]
    
    def get_interval_with_jitter(self, cadence: str) -> int:
        """
        Get interval with jitter applied.
        
        Args:
            cadence: Cadence level
            
        Returns:
            Interval in seconds with jitter
        """
        base_interval = INTERVALS.get(cadence, PROACTIVE_MESSAGING_INTERVAL_1H)
        jitter = JITTERS.get(cadence, PROACTIVE_MESSAGING_JITTER_1H)
        
        logger.debug(f"Calculating interval with jitter for cadence {cadence}: base={base_interval}, jitter={jitter}")
        
        # Apply jitter (add or subtract random amount)
        jitter_amount = random.randint(-jitter, jitter)
        final_interval = max(base_interval + jitter_amount, 60)  # Minimum 1 minute
        
        logger.debug(f"Jitter calculation: {base_interval} + {jitter_amount} = {final_interval}")
        return final_interval
    
    def should_switch_to_long_term_mode(self, user_id: int) -> bool:
        """
        Check if user should be switched to long-term mode.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if should switch to long-term mode, False otherwise
        """
        user_state = self._get_user_state(user_id)
        consecutive_outreaches = user_state.get('consecutive_outreaches', 0)
        return consecutive_outreaches >= self.max_consecutive_outreaches
    
    def reset_cadence(self, user_id: int):
        """
        Reset cadence to shortest interval for a user.
        
        Args:
            user_id: Telegram user ID
        """
        user_state = self._get_user_state(user_id)
        user_state.update({
            'cadence': '1h',
            'consecutive_outreaches': 0,
            'last_proactive_message': None,
            'scheduled_task_id': None,
            'user_replied': False
        })
        self._set_user_state(user_id, user_state)
        
        logger.info(f"Reset cadence for user {user_id} to 1h")
    
    def update_user_reply_status(self, user_id: int, replied: bool = True):
        """
        Update user reply status and reset cadence if they replied.
        
        Args:
            user_id: Telegram user ID
            replied: Whether user replied (default True)
        """
        user_state = self._get_user_state(user_id)
        user_state['user_replied'] = replied
        user_state['scheduled_task_id'] = None
        self._set_user_state(user_id, user_state)
        
        if replied:
            # Reset cadence when user replies
            self.reset_cadence(user_id)
            logger.info(f"User {user_id} replied, cadence reset")
    
    def schedule_proactive_message(self, user_id: int, scheduled_time: datetime = None, message_type: str = "RegularReachout", exclude_task_id: str = None):
        """
        Schedule a proactive message for a user.

        Args:
            user_id: Telegram user ID
            scheduled_time: Optional specific time to schedule the message (defaults to None)
            message_type: Type of message to schedule (default: "RegularReachout")
            exclude_task_id: Task ID to exclude from revocation (default: None)
        """
        logger.info(f"Scheduling proactive message for user {user_id} of type {message_type}")
        
        if not self.enabled:
            logger.info("Proactive messaging is disabled")
            return
        
        # Get user state or initialize it
        user_state = self._get_user_state(user_id)
        if not user_state:
            logger.debug(f"User {user_id} not found in Redis, initializing...")
            self.reset_cadence(user_id)
            user_state = self._get_user_state(user_id)
        
        current_cadence = user_state.get('cadence', '1h')
        logger.debug(f"Current cadence for user {user_id}: {current_cadence}")
        
        # Check if we should switch to long-term mode
        if self.should_switch_to_long_term_mode(user_id):
            current_cadence = '1mo'
            logger.info(f"Switching user {user_id} to long-term mode")
        
        # Calculate next interval with jitter if no scheduled_time provided
        if scheduled_time is None:
            interval = self.get_interval_with_jitter(current_cadence)
            logger.debug(f"Calculated interval for user {user_id}: {interval} seconds")
            
            # Schedule the message
            scheduled_time = datetime.now() + timedelta(seconds=interval)
            logger.debug(f"Initial scheduled time for user {user_id}: {scheduled_time}")
        
        # Adjust for quiet hours
        original_time = scheduled_time
        scheduled_time = self.adjust_for_quiet_hours(scheduled_time)
        if original_time != scheduled_time:
            logger.info(f"Adjusted scheduled time for user {user_id} due to quiet hours: {original_time} -> {scheduled_time}")
        
        # Update user state
        user_state.update({
            'scheduled_time': scheduled_time.isoformat() if scheduled_time else None,
            'cadence': current_cadence,
            'user_replied': False
        })
        self._set_user_state(user_id, user_state)
        
        # Revoke any existing scheduled tasks for this user before scheduling a new one
        self._revoke_user_tasks(user_id, user_state, message_type, exclude_task_id)
        logger.debug(f"Other user tasks of type {message_type} revoked for user {user_id}")
        
        # Schedule the Celery task
        logger.debug(f"Scheduling Celery task for user {user_id} with ETA: {scheduled_time}")
        task = send_proactive_message.apply_async(
            args=[user_id],
            eta=scheduled_time
        )
        
        # Store the task ID in Redis
        self._add_task_id(user_id, task.id, message_type)
        
        logger.info(f"Scheduled proactive message for user {user_id} at {scheduled_time} with cadence {current_cadence} and task ID {task.id}")
    
    def handle_user_message(self, user_id: int):
        """
        Handle incoming user message - cancel scheduled message and reset cadence.
        
        Args:
            user_id: Telegram user ID
        """
        # Revoke any scheduled proactive message for this user
        user_state = self._get_user_state(user_id)
        if user_state:
            # Revoke the scheduled task if it exists
            self._revoke_user_tasks(user_id, user_state, "RegularReachout")
            
            # Update user state
            user_state['scheduled_time'] = None
            user_state['scheduled_task_id'] = None
            user_state['user_replied'] = True
            self._set_user_state(user_id, user_state)
        
        # Reset cadence to shortest interval
        self.reset_cadence(user_id)
        
        # Schedule new proactive message
        self.schedule_proactive_message(user_id, message_type="RegularReachout")
        
        logger.info(f"Handled user message for user {user_id}, cadence reset and new message scheduled")

# Initialize the service
proactive_messaging_service = ProactiveMessagingService()

@celery_app.task(bind=True)
def send_proactive_message(self, user_id: int):
    """
    Celery task to send a proactive message to a user.
    This task is now lightweight and uses the shared AppContext.
    """
    task_id = self.request.id
    logger.info(f"Starting Celery task send_proactive_message [{task_id}] for user {user_id}")

    try:
        # Run the async part of the task
        asyncio.run(send_proactive_message_async(self, user_id))
    except Exception as e:
        logger.error(f"Error in send_proactive_message task for user {user_id} [{task_id}]: {e}")
        # Retry with exponential backoff
        try:
            raise self.retry(exc=e, countdown=60, max_retries=3)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for task {task_id} for user {user_id}")
    
    logger.info(f"Completed Celery task send_proactive_message [{task_id}] for user {user_id}")


async def send_proactive_message_async(task, user_id: int):
    """
    Async implementation of the proactive message sending logic.
    """
    task_id = task.request.id

    # Get user state
    user_state = proactive_messaging_service._get_user_state(user_id)
    logger.debug(f"User {user_id} state: {user_state}")
    
    # Check if user has replied since scheduling
    if user_state.get('user_replied', False):
        logger.info(f"User {user_id} has replied, skipping proactive message [{task_id}]")
        return

    # Check if this task has been revoked
    if proactive_messaging_service._is_task_revoked(user_id, task_id, "RegularReachout"):
        logger.info(f"Task {task_id} for user {user_id} has been revoked, skipping.")
        return


    app_context = await get_app_context()

    # Update consecutive outreaches
    consecutive_outreaches = user_state.get('consecutive_outreaches', 0) + 1
    user_state['consecutive_outreaches'] = consecutive_outreaches
    user_state['last_proactive_message'] = datetime.now().isoformat()
    proactive_messaging_service._set_user_state(user_id, user_state)
    logger.info(f"User {user_id} consecutive outreaches: {consecutive_outreaches} [{task_id}]")
    
    try:
        # Get conversation history
        conversation_history = await app_context.conversation_manager.get_formatted_conversation_async(user_id)
        
        # Get conversation ID
        conversation = await app_context.conversation_manager._ensure_user_and_conversation(user_id)
        conversation_id = str(conversation.id) if conversation else None
        
        # Generate AI response
        ai_response = await generate_ai_response(
            ai_handler=app_context.ai_handler,
            typing_manager=app_context.typing_manager,
            bot=app_context.bot,
            chat_id=user_id,
            additional_prompt=PROACTIVE_MESSAGING_PROMPT,
            conversation_history=conversation_history,
            conversation_id=conversation_id,
            role="user",
            show_typing=True
        )
        
        if ai_response:
            cleaned_response = clean_ai_response(ai_response)
            if cleaned_response:
                # Add message to history
                await app_context.conversation_manager.add_message_async(user_id, "assistant", cleaned_response)
                logger.info(f"Proactive message added to history for user {user_id} [{task_id}]")
                
                # Enqueue message for sending
                await app_context.message_queue_manager.enqueue_message(
                    user_id=user_id,
                    chat_id=user_id,
                    text=cleaned_response,
                    message_type="proactive",
                )
                logger.info(f"Proactive message enqueued for user {user_id} [{task_id}]")
            else:
                logger.info(f"Cleaned proactive message for user {user_id} was empty.")
        else:
            logger.error(f"Failed to generate proactive message for user {user_id} [{task_id}]")

    except Exception as e:
        logger.error(f"Error during async proactive message generation for user {user_id} [{task_id}]: {e}")
        # The main sync task will handle retry logic
        raise

    # Escalate and schedule the next message
    current_cadence = user_state.get('cadence', '1h')
    next_cadence = proactive_messaging_service.get_next_interval(current_cadence)
    logger.info(f"Escalating cadence for user {user_id} from {current_cadence} to {next_cadence}")
    user_state['cadence'] = next_cadence
    proactive_messaging_service._set_user_state(user_id, user_state)
    proactive_messaging_service.schedule_proactive_message(user_id, exclude_task_id=task_id)


@celery_app.task(bind=True)
def manage_proactive_messages(self):
    """
    Celery Beat task to manage and schedule proactive messages.
    This task is now a lightweight sync wrapper for the async implementation.
    """
    task_id = self.request.id
    logger.info(f"Starting Celery Beat task manage_proactive_messages [{task_id}]")
    try:
        asyncio.run(manage_proactive_messages_async(self))
    except Exception as e:
        logger.error(f"Error in manage_proactive_messages task [{task_id}]: {e}")


async def manage_proactive_messages_async(task):
    """
    Async implementation of the proactive message management logic.
    """
    task_id = task.request.id
    logger.info(f"Running async logic for manage_proactive_messages [{task_id}]")

    try:
        user_states = proactive_messaging_service._get_all_user_states()
        now = datetime.now()

        for user_id, state in user_states.items():
            scheduled_time = state.get('scheduled_time')

            if isinstance(scheduled_time, str):
                try:
                    scheduled_time = datetime.fromisoformat(scheduled_time)
                except (ValueError, TypeError):
                    logger.error(f"Invalid scheduled_time format for user {user_id}: {scheduled_time}")
                    continue

            if scheduled_time and scheduled_time < now:
                logger.info(f"User {user_id} is due for a proactive message. Triggering via service.")

                # Use the proactive messaging service to handle scheduling properly
                # This ensures proper task management and prevents duplicates
                proactive_messaging_service.schedule_proactive_message(
                    user_id,
                    message_type="RegularReachout"
                )

    except Exception as e:
        logger.error(f"Async error in manage_proactive_messages_async [{task_id}]: {e}")


# Celery Beat Schedule
celery_app.conf.beat_schedule = {
    'manage-proactive-messages': {
        'task': 'proactive_messaging.manage_proactive_messages',
        'schedule': crontab(minute='*/1'),  # Run every 1 minute
    },
}

# Default queue
celery_app.conf.task_default_queue = 'proactive_messaging'
