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
    PROACTIVE_MESSAGING_CADENCES,
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

# Create a mapping from cadence name to its properties for quick lookups
CADENCE_MAP = {c["name"]: c for c in PROACTIVE_MESSAGING_CADENCES}
CADENCE_LEVELS = [c["name"] for c in PROACTIVE_MESSAGING_CADENCES]

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
        cadence_info = ", ".join([f'{c["name"]}={c["interval"]}s (jitter: {c["jitter"]}s)' for c in PROACTIVE_MESSAGING_CADENCES])
        logger.info(f"  Cadences: {cadence_info}")
        
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

    @staticmethod
    def _serialize_state(state: dict) -> str:
        """Serialize state dictionary to a JSON string, handling datetimes."""
        state_copy = state.copy()
        for key, value in state_copy.items():
            if isinstance(value, datetime):
                state_copy[key] = value.isoformat()
        return json.dumps(state_copy, default=str)

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
        cadence_config = CADENCE_MAP.get(cadence, CADENCE_MAP[CADENCE_LEVELS[0]])
        base_interval = cadence_config["interval"]
        jitter = cadence_config["jitter"]
        
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
            'cadence': CADENCE_LEVELS[0],
            'consecutive_outreaches': 0,
            'last_proactive_message': datetime.now(),
            'scheduled_task_id': None,
            'user_replied': False
        })
        self._set_user_state(user_id, user_state)
        
        logger.info(f"Reset cadence for user {user_id} to {CADENCE_LEVELS[0]}")
    
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
            # When a user replies, we just reset their state.
            # The centralized `manage_proactive_messages` task will handle rescheduling.
            self.reset_cadence(user_id)
            logger.info(f"User {user_id} replied. Cadence state has been reset.")
    
    def handle_user_message(self, user_id: int):
        """
        Handle incoming user message - reset cadence state.
        The `manage_proactive_messages` task will handle rescheduling.
        
        Args:
            user_id: Telegram user ID
        """
        # A user message resets their proactive messaging cadence.
        self.reset_cadence(user_id)
        logger.info(f"Handled user message for user {user_id}, cadence state reset.")

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
    
    # This task is now simplified: its only job is to send a message.
    # The `manage_proactive_messages` task is responsible for all scheduling logic.

    # Verify that this task should run.
    # The 'scheduled_task_id' in Redis should match this task's ID.
    if user_state.get('scheduled_task_id') != task_id:
        logger.warning(
            f"Task {task_id} for user {user_id} is stale or superseded. "
            f"Expected {user_state.get('scheduled_task_id')}. Skipping."
        )
        return
        
    app_context = await get_app_context()

    try:
        # Generate and send the message...
        conversation_history = await app_context.conversation_manager.get_formatted_conversation_async(user_id)
        conversation = await app_context.conversation_manager._ensure_user_and_conversation(user_id)
        conversation_id = str(conversation.id) if conversation else None
        
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
                await app_context.conversation_manager.add_message_async(user_id, "assistant", cleaned_response)
                await app_context.message_queue_manager.enqueue_message(
                    user_id=user_id,
                    chat_id=user_id,
                    text=cleaned_response,
                    message_type="proactive",
                )
                logger.info(f"Proactive message successfully generated and enqueued for user {user_id} [{task_id}]")
        else:
            logger.error(f"AI response was empty for proactive message to user {user_id} [{task_id}]")

    except Exception as e:
        logger.error(f"Error in send_proactive_message_async for user {user_id} [{task_id}]: {e}", exc_info=True)
        # The sync task's retry logic will handle this.
        raise
    finally:
        # CRITICAL: Update state AFTER sending.
        # This signals that the outreach was completed and the user has not yet replied.
        user_state = proactive_messaging_service._get_user_state(user_id)
        
        # Determine the next cadence level
        current_cadence = user_state.get('cadence', CADENCE_LEVELS[0])
        next_cadence = proactive_messaging_service.get_next_interval(current_cadence)

        # Update the state
        user_state['last_proactive_message'] = datetime.now()
        user_state['consecutive_outreaches'] = user_state.get('consecutive_outreaches', 0) + 1
        user_state['user_replied'] = False
        user_state['cadence'] = next_cadence
        user_state['scheduled_task_id'] = None  # Clear the task ID

        proactive_messaging_service._set_user_state(user_id, user_state)
        
        logger.info(
            f"Updated user {user_id} state post-outreach. "
            f"New cadence: {next_cadence}. "
            f"Consecutive outreaches: {user_state['consecutive_outreaches']}."
        )


@celery_app.task(bind=True)
def manage_proactive_messages(self):
    """
    Celery Beat task to manage and schedule proactive messages.
    This task is now a lightweight sync wrapper for the async implementation.
    """
    task_id = self.request.id
    logger.info(f"Starting Celery Beat task manage_proactive_messages [{task_id}]")
    if not proactive_messaging_service.enabled:
        logger.info(f"Proactive messaging is disabled. Skipping task [{task_id}].")
        return
    try:
        asyncio.run(manage_proactive_messages_async(self))
    except Exception as e:
        logger.error(f"Error in manage_proactive_messages task [{task_id}]: {e}")


async def manage_proactive_messages_async(task):
    """
    Async implementation of the proactive message management logic.
    This is the SOLE authority for scheduling proactive messages.
    """
    task_id = task.request.id
    logger.info(f"Running proactive message management task [{task_id}]")

    user_states = proactive_messaging_service._get_all_user_states()
    now = datetime.now()

    for user_id, state in user_states.items():
        lock_key = f"proactive_messaging:lock:user:{user_id}"
        lock = proactive_messaging_service.redis_client.lock(lock_key, timeout=60)

        if lock.acquire(blocking=False):
            try:
                # Re-fetch state now that we have the lock
                state = proactive_messaging_service._get_user_state(user_id)

                logger.info(f"Processing user {user_id} with state: {state}")

                if state.get('scheduled_task_id'):
                    logger.debug(f"Skipping user {user_id}: task {state['scheduled_task_id']} is already scheduled.")
                    continue

                current_cadence_name = state.get('cadence', CADENCE_LEVELS[0])
                if proactive_messaging_service.should_switch_to_long_term_mode(user_id):
                    current_cadence_name = CADENCE_LEVELS[-1]
                
                cadence_config = CADENCE_MAP.get(current_cadence_name)
                
                last_message_time = state.get('last_proactive_message')
                if not last_message_time:
                    logger.info(f"User {user_id} has no 'last_proactive_message' timestamp. Initializing it to the current time.")
                    state['last_proactive_message'] = now
                    proactive_messaging_service._set_user_state(user_id, state)
                    continue

                interval_with_jitter = proactive_messaging_service.get_interval_with_jitter(current_cadence_name)
                next_schedule_time = last_message_time + timedelta(seconds=interval_with_jitter)

                if now >= next_schedule_time:
                    logger.info(f"User {user_id} is due for a proactive message. Scheduling now.")
                    
                    scheduled_time = proactive_messaging_service.adjust_for_quiet_hours(now)
                    
                    new_task = send_proactive_message.apply_async(
                        args=[user_id],
                        eta=scheduled_time
                    )
                    
                    state['scheduled_task_id'] = new_task.id
                    proactive_messaging_service._set_user_state(user_id, state)
                    
                    logger.info(
                        f"Scheduled new proactive message for user {user_id} with task ID {new_task.id} "
                        f"at {scheduled_time} (cadence: {current_cadence_name})."
                    )

            except Exception as e:
                logger.error(f"Error processing user {user_id} in manage_proactive_messages: {e}", exc_info=True)
            finally:
                lock.release()


# Celery Beat Schedule (only if enabled)
if PROACTIVE_MESSAGING_ENABLED:
    celery_app.conf.beat_schedule = {
        'manage-proactive-messages': {
            'task': 'proactive_messaging.manage_proactive_messages',
            'schedule': crontab(minute='*/1'),  # Run every 1 minute
        },
    }

# Default queue
celery_app.conf.task_default_queue = 'proactive_messaging'
