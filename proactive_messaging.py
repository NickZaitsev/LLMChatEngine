"""
Proactive Messaging System for AI Girlfriend Bot

This module handles the scheduling and sending of proactive messages to users
based on configurable intervals, jitter, quiet hours, and cadence escalation.
"""

import asyncio
import logging
import random
import re
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
    PROACTIVE_MESSAGING_QUIET_HOURS_START,
    PROACTIVE_MESSAGING_QUIET_HOURS_END,
    PROACTIVE_MESSAGING_MAX_CONSECUTIVE_OUTREACHES,
    PROACTIVE_MESSAGING_PROMPT,
    PROACTIVE_MESSAGING_RESTART_DELAY_MAX,
    TELEGRAM_TOKEN, DATABASE_URL, USE_PGVECTOR
)

# Import components for proactive messaging
from ai_handler import AIHandler
from message_manager import send_ai_response, TypingIndicatorManager, clean_ai_response, generate_ai_response
from storage_conversation_manager import PostgresConversationManager

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
        self.quiet_hours_start = PROACTIVE_MESSAGING_QUIET_HOURS_START
        self.quiet_hours_end = PROACTIVE_MESSAGING_QUIET_HOURS_END
        self.max_consecutive_outreaches = PROACTIVE_MESSAGING_MAX_CONSECUTIVE_OUTREACHES
        
        # Log configuration
        logger.info(f"Proactive Messaging Service Configuration:")
        logger.info(f"  Enabled: {self.enabled}")
        logger.info(f"  Redis URL: {self.redis_url}")
        logger.info(f"  Quiet Hours: {self.quiet_hours_start} - {self.quiet_hours_end}")
        logger.info(f"  Max Consecutive Outreaches: {self.max_consecutive_outreaches}")
        logger.info(f"  Intervals: 1H={PROACTIVE_MESSAGING_INTERVAL_1H}s, 9H={PROACTIVE_MESSAGING_INTERVAL_9H}s, 1D={PROACTIVE_MESSAGING_INTERVAL_1D}s, 1W={PROACTIVE_MESSAGING_INTERVAL_1W}s, 1MO={PROACTIVE_MESSAGING_INTERVAL_1MO}s")
        logger.info(f"  Jitter: 1H={PROACTIVE_MESSAGING_JITTER_1H}s, 9H={PROACTIVE_MESSAGING_JITTER_9H}s, 1D={PROACTIVE_MESSAGING_JITTER_1D}s, 1W={PROACTIVE_MESSAGING_JITTER_1W}s, 1MO={PROACTIVE_MESSAGING_JITTER_1MO}s")
        
        # Initialize Redis client
        self.redis_client = redis.from_url(self.redis_url)
        logger.info("Redis client initialized")
        
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
            # Get all keys matching the pattern
            pattern = "proactive_messaging:user:*"
            keys = self.redis_client.keys(pattern)
            
            user_states = {}
            for key in keys:
                try:
                    # Extract user ID from key
                    user_id = int(key.decode('utf-8').split(':')[-1])
                    state_json = self.redis_client.get(key)
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

    def _reschedule_missed_messages(self):
        """
        Reschedule missed messages with a random delay.
        """
        logger.info("Checking for missed proactive messages to reschedule...")
        
        # Get all user states
        user_states = self._get_all_user_states()
        
        rescheduled_count = 0
        for user_id, state in user_states.items():
            try:
                # Check if there's a scheduled time
                scheduled_time = state.get('scheduled_time')
                if not scheduled_time:
                    continue
                
                # Check if scheduled time is in the past
                if self._is_scheduled_time_in_past(scheduled_time):
                    logger.info(f"Found missed proactive message for user {user_id}, scheduled at {scheduled_time}")
                    
                    # Generate a random delay (up to PROACTIVE_MESSAGING_RESTART_DELAY_MAX seconds)
                    delay = random.randint(30, PROACTIVE_MESSAGING_RESTART_DELAY_MAX)
                    new_scheduled_time = datetime.now() + timedelta(seconds=delay)
                    
                    logger.info(f"Rescheduling missed message for user {user_id} with delay of {delay} seconds (at {new_scheduled_time})")
                    
                    # Revoke any existing scheduled task for this user
                    self._revoke_user_task(user_id, state)
                    
                    # Schedule the next message using the Celery task
                    schedule_next_message.apply_async(
                        args=[user_id]
                    )
                    
                    # Note: The task ID is no longer directly available since we're not
                    # calling send_proactive_message directly anymore. The state update
                    # will be handled by the schedule_proactive_message method.
                    
                    rescheduled_count += 1
            except Exception as e:
                logger.error(f"Error rescheduling message for user {user_id}: {e}")
                continue
        
        logger.info(f"Rescheduled {rescheduled_count} missed proactive messages")
        logger.info("Proactive Messaging Service initialized")
    
    def _revoke_user_task(self, user_id: int, state: dict):
        """
        Revoke any existing scheduled task for a user.
        
        Args:
            user_id: Telegram user ID
            state: User state dictionary containing task information
        """
        try:
            # Get the scheduled task ID from user state
            task_id = state.get('scheduled_task_id')
            if task_id:
                logger.info(f"Revoking scheduled task {task_id} for user {user_id}")
                # Revoke the Celery task
                celery_app.control.revoke(task_id, terminate=True)
                logger.info(f"Revoked scheduled task {task_id} for user {user_id}")
                
                # Clear the task ID from state
                state['scheduled_task_id'] = None
            else:
                logger.debug(f"No scheduled task found for user {user_id}")
        except Exception as e:
            logger.error(f"Error revoking task for user {user_id}: {e}")
    
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
    
    def schedule_proactive_message(self, user_id: int, scheduled_time: datetime = None):
        """
        Schedule a proactive message for a user.
        
        Args:
            user_id: Telegram user ID
            scheduled_time: Optional specific time to schedule the message (defaults to None)
        """
        logger.info(f"Scheduling proactive message for user {user_id}")
        
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
        
        # Schedule the Celery task
        logger.debug(f"Scheduling Celery task for user {user_id} with ETA: {scheduled_time}")
        send_proactive_message.apply_async(
            args=[user_id],
            eta=scheduled_time
        )
        
        logger.info(f"Scheduled proactive message for user {user_id} at {scheduled_time} with cadence {current_cadence}")
    
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
            self._revoke_user_task(user_id, user_state)
            
            # Update user state
            user_state['scheduled_time'] = None
            user_state['scheduled_task_id'] = None
            user_state['user_replied'] = True
            self._set_user_state(user_id, user_state)
        
        # Reset cadence to shortest interval
        self.reset_cadence(user_id)
        
        # Schedule new proactive message
        self.schedule_proactive_message(user_id)
        
        logger.info(f"Handled user message for user {user_id}, cadence reset and new message scheduled")

# Initialize the service
proactive_messaging_service = ProactiveMessagingService()

@celery_app.task(bind=True)
def send_proactive_message(self, user_id: int):
    """
    Celery task to send a proactive message to a user.
    
    Args:
        self: Celery task instance
        user_id: Telegram user ID
    """
    task_id = self.request.id
    logger.info(f"Starting Celery task send_proactive_message [{task_id}] for user {user_id}")
    
    # Get user state
    user_state = proactive_messaging_service._get_user_state(user_id)
    logger.debug(f"User {user_id} state: {user_state}")
    
    # Check if user has replied since scheduling
    if user_state.get('user_replied', False):
        logger.info(f"User {user_id} has replied since scheduling, skipping proactive message [{task_id}]")
        return
    
    # Update consecutive outreaches count
    consecutive_outreaches = user_state.get('consecutive_outreaches', 0)
    consecutive_outreaches += 1
    
    user_state['consecutive_outreaches'] = consecutive_outreaches
    user_state['last_proactive_message'] = datetime.now().isoformat()
    proactive_messaging_service._set_user_state(user_id, user_state)
    
    logger.info(f"Updated user {user_id} consecutive outreaches count to {consecutive_outreaches} [{task_id}]")
    
    # Generate and send proactive message
    try:
        # Initialize components needed for sending messages
        ai_handler = AIHandler()
        typing_manager = TypingIndicatorManager()
        conversation_manager = PostgresConversationManager(DATABASE_URL, USE_PGVECTOR)
        
        # Create Telegram bot instance
        from telegram import Bot
        bot = Bot(token=TELEGRAM_TOKEN)
        
        # Initialize the conversation manager storage
        async def init_storage():
            await conversation_manager.initialize()
        
        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run the async initialization with timeout
        try:
            loop.run_until_complete(run_with_timeout(init_storage(), timeout=30))
        except asyncio.TimeoutError:
            logger.error(f"Storage initialization timed out for user {user_id} [{task_id}]")
            raise
        except Exception as e:
            logger.error(f"Error initializing storage for user {user_id} [{task_id}]: {e}")
            raise
        
        # Get conversation history with timeout
        try:
            conversation_history = loop.run_until_complete(
                run_with_timeout(conversation_manager.get_formatted_conversation_async(user_id), timeout=30)
            )
        except asyncio.TimeoutError:
            logger.error(f"Getting conversation history timed out for user {user_id} [{task_id}]")
            raise
        except Exception as e:
            logger.error(f"Error getting conversation history for user {user_id} [{task_id}]: {e}")
            raise
        
        # Generate proactive message prompt
        proactive_prompt = PROACTIVE_MESSAGING_PROMPT
        
        # Generate AI response using shared function with timeout
        try:
            ai_response = loop.run_until_complete(
                run_with_timeout(
                    generate_ai_response(ai_handler, typing_manager, bot, user_id, proactive_prompt, conversation_history, None, "user", True),
                    timeout=60
                )
            )
        except asyncio.TimeoutError:
            logger.error(f"AI response generation timed out for user {user_id} [{task_id}]")
            raise
        except Exception as e:
            logger.error(f"Error generating AI response for user {user_id} [{task_id}]: {e}")
            raise
        
        if ai_response:
            # Clean the AI response
            cleaned_response = clean_ai_response(ai_response)
            
            # Add the proactive message to conversation history
            try:
                loop.run_until_complete(
                    run_with_timeout(
                        conversation_manager.add_message_async(user_id, "assistant", cleaned_response),
                        timeout=30
                    )
                )
                logger.info(f"Proactive message added to history for user {user_id} [{task_id}]: {cleaned_response[:50]}...")
            except asyncio.TimeoutError:
                logger.error(f"Adding message to history timed out for user {user_id} [{task_id}]")
                # Continue even if adding to history fails
            except Exception as e:
                logger.error(f"Error adding message to history for user {user_id} [{task_id}]: {e}")
                # Continue even if adding to history fails
            
            # Send the message with timeout
            try:
                loop.run_until_complete(
                    run_with_timeout(
                        send_ai_response(chat_id=user_id, text=cleaned_response, bot=bot, typing_manager=typing_manager),
                        timeout=30
                    )
                )
                logger.info(f"Proactive message sent to user {user_id} [{task_id}]: {cleaned_response[:50]}...")
            except asyncio.TimeoutError:
                logger.error(f"Sending message timed out for user {user_id} [{task_id}]")
                raise
            except Exception as e:
                logger.error(f"Error sending message to user {user_id} [{task_id}]: {e}")
                raise
        else:
            logger.error(f"Failed to generate proactive message for user {user_id} [{task_id}]")
            
    except Exception as e:
        logger.error(f"Error sending proactive message to user {user_id} [{task_id}]: {e}")
        # Retry with exponential backoff
        try:
            raise self.retry(exc=e, countdown=60, max_retries=3)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for task {task_id} for user {user_id}")
        # Continue with state management even if message sending fails
    
    # Escalate cadence for next message
    current_cadence = user_state.get('cadence', '1h')
    next_cadence = proactive_messaging_service.get_next_interval(current_cadence)
    
    logger.info(f"Escalating cadence for user {user_id} from {current_cadence} to {next_cadence} [{task_id}]")
    
    # Update cadence
    user_state['cadence'] = next_cadence
    proactive_messaging_service._set_user_state(user_id, user_state)
    
    # REVOKE MESSAGES
    proactive_messaging_service._revoke_user_task(user_id, user_state)

    # Schedule next message
    proactive_messaging_service.schedule_proactive_message(user_id)
    
    logger.info(f"Completed Celery task send_proactive_message [{task_id}] for user {user_id}")


async def run_with_timeout(coro, timeout=30):
    """
    Run an async coroutine with a timeout.
    
    Args:
        coro: The coroutine to run
        timeout: Timeout in seconds
        
    Returns:
        The result of the coroutine
        
    Raises:
        asyncio.TimeoutError: If the coroutine times out
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(f"Async operation timed out after {timeout} seconds")
        raise

@celery_app.task(bind=True)
def schedule_next_message(self, user_id: int):
    """
    Celery task to schedule the next proactive message.
    
    Args:
        self: Celery task instance
        user_id: Telegram user ID
    """
    task_id = self.request.id
    logger.info(f"Starting Celery task schedule_next_message [{task_id}] for user {user_id}")
    try:
        # Get user state to check for existing scheduled tasks
        user_state = proactive_messaging_service._get_user_state(user_id)
        
        # Revoke any existing scheduled task for this user
        if user_state:
            proactive_messaging_service._revoke_user_task(user_id, user_state)
        
        # Calculate the new scheduled time with delay for rescheduling missed messages
        delay = random.randint(30, PROACTIVE_MESSAGING_RESTART_DELAY_MAX)
        new_scheduled_time = datetime.now() + timedelta(seconds=delay)
        
        # Call the modified method with the scheduled time override
        proactive_messaging_service.schedule_proactive_message(user_id, new_scheduled_time)
        logger.info(f"Completed Celery task schedule_next_message [{task_id}] for user {user_id}")
    except Exception as e:
        logger.error(f"Error in schedule_next_message [{task_id}] for user {user_id}: {e}")
        raise

# Celery Beat Schedule
celery_app.conf.beat_schedule = {
    'check-proactive-messaging': {
        'task': 'proactive_messaging.send_proactive_message',
        'schedule': crontab(minute='*/30'),  # Run every 30 minutes
    },
}

# Default queue
celery_app.conf.task_default_queue = 'proactive_messaging'

# Import Celery signals
from celery.signals import worker_ready

@worker_ready.connect
def startup_proactive_messaging(sender=None, **kwargs):
    """
    Function to run when Celery worker is ready.
    Checks for and reschedules any missed proactive messages.
    """
    logger.info("Celery worker is ready, checking for missed proactive messages...")
    try:
        # Ensure the proactive messaging service is initialized
        if proactive_messaging_service is not None:
            proactive_messaging_service._reschedule_missed_messages()
        else:
            logger.error("Proactive messaging service is not initialized")
    except Exception as e:
        logger.error(f"Error during startup proactive message rescheduling: {e}")