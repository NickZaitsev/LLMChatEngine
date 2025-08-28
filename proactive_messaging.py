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
        
        # In-memory storage for tracking user states (in production, this should be in Redis or database)
        self.user_states = {}
        
        logger.info("Proactive Messaging Service initialized")
    
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
        user_state = self.user_states.get(user_id, {})
        consecutive_outreaches = user_state.get('consecutive_outreaches', 0)
        return consecutive_outreaches >= self.max_consecutive_outreaches
    
    def reset_cadence(self, user_id: int):
        """
        Reset cadence to shortest interval for a user.
        
        Args:
            user_id: Telegram user ID
        """
        if user_id not in self.user_states:
            self.user_states[user_id] = {}
        
        self.user_states[user_id].update({
            'cadence': '1h',
            'consecutive_outreaches': 0,
            'last_proactive_message': None,
            'user_replied': False
        })
        
        logger.info(f"Reset cadence for user {user_id} to 1h")
    
    def update_user_reply_status(self, user_id: int, replied: bool = True):
        """
        Update user reply status and reset cadence if they replied.
        
        Args:
            user_id: Telegram user ID
            replied: Whether user replied (default True)
        """
        if user_id not in self.user_states:
            self.user_states[user_id] = {}
        
        self.user_states[user_id]['user_replied'] = replied
        
        if replied:
            # Reset cadence when user replies
            self.reset_cadence(user_id)
            logger.info(f"User {user_id} replied, cadence reset")
    
    def schedule_proactive_message(self, user_id: int):
        """
        Schedule a proactive message for a user.
        
        Args:
            user_id: Telegram user ID
        """
        logger.info(f"Scheduling proactive message for user {user_id}")
        
        if not self.enabled:
            logger.info("Proactive messaging is disabled")
            return
        
        # Get user state or initialize it
        if user_id not in self.user_states:
            logger.debug(f"User {user_id} not found in user_states, initializing...")
            self.reset_cadence(user_id)
        
        user_state = self.user_states[user_id]
        current_cadence = user_state.get('cadence', '1h')
        logger.debug(f"Current cadence for user {user_id}: {current_cadence}")
        
        # Check if we should switch to long-term mode
        if self.should_switch_to_long_term_mode(user_id):
            current_cadence = '1mo'
            logger.info(f"Switching user {user_id} to long-term mode")
        
        # Calculate next interval with jitter
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
            'scheduled_time': scheduled_time,
            'cadence': current_cadence,
            'user_replied': False
        })
        
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
        # Cancel any scheduled proactive message for this user
        # In a real implementation, we would revoke the Celery task
        # For now, we'll just update the user state
        
        if user_id in self.user_states:
            self.user_states[user_id]['scheduled_time'] = None
            self.user_states[user_id]['user_replied'] = True
        
        # Reset cadence to shortest interval
        self.reset_cadence(user_id)
        
        # Schedule new proactive message
        self.schedule_proactive_message(user_id)
        
        logger.info(f"Handled user message for user {user_id}, cadence reset and new message scheduled")

# Initialize the service
proactive_messaging_service = ProactiveMessagingService()

@celery_app.task
def send_proactive_message(user_id: int):
    """
    Celery task to send a proactive message to a user.
    
    Args:
        user_id: Telegram user ID
    """
    logger.info(f"Starting Celery task send_proactive_message for user {user_id}")
    
    # Get user state
    user_state = proactive_messaging_service.user_states.get(user_id, {})
    logger.debug(f"User {user_id} state: {user_state}")
    
    # Check if user has replied since scheduling
    if user_state.get('user_replied', False):
        logger.info(f"User {user_id} has replied since scheduling, skipping proactive message")
        return
    
    # Update consecutive outreaches count
    consecutive_outreaches = user_state.get('consecutive_outreaches', 0)
    consecutive_outreaches += 1
    
    if user_id not in proactive_messaging_service.user_states:
        proactive_messaging_service.user_states[user_id] = {}
    
    proactive_messaging_service.user_states[user_id]['consecutive_outreaches'] = consecutive_outreaches
    proactive_messaging_service.user_states[user_id]['last_proactive_message'] = datetime.now()
    
    logger.info(f"Updated user {user_id} consecutive outreaches count to {consecutive_outreaches}")
    
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
        
        # Run the async initialization in a new event loop
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(init_storage())
        
        # Get conversation history
        conversation_history = loop.run_until_complete(conversation_manager.get_formatted_conversation_async(user_id))
        
        # Generate proactive message prompt
        proactive_prompt = PROACTIVE_MESSAGING_PROMPT
        
        # Generate AI response using shared function
        ai_response = loop.run_until_complete(
            generate_ai_response(ai_handler, typing_manager, bot, user_id, proactive_prompt, conversation_history, None, "system", True)
        )
        
        if ai_response:
            # Clean the AI response
            cleaned_response = clean_ai_response(ai_response)
            
            # Send the message
            loop.run_until_complete(
                send_ai_response(chat_id=user_id, text=cleaned_response, bot=bot, typing_manager=typing_manager)
            )
            logger.info(f"Proactive message sent to user {user_id}: {cleaned_response[:50]}...")
        else:
            logger.error(f"Failed to generate proactive message for user {user_id}")
            
    except Exception as e:
        logger.error(f"Error sending proactive message to user {user_id}: {e}")
        # Continue with state management even if message sending fails
    
    # Escalate cadence for next message
    current_cadence = user_state.get('cadence', '1h')
    next_cadence = proactive_messaging_service.get_next_interval(current_cadence)
    
    logger.info(f"Escalating cadence for user {user_id} from {current_cadence} to {next_cadence}")
    
    # Update cadence
    proactive_messaging_service.user_states[user_id]['cadence'] = next_cadence
    
    # Schedule next message
    proactive_messaging_service.schedule_proactive_message(user_id)
    
    logger.info(f"Completed Celery task send_proactive_message for user {user_id}")

@celery_app.task
def schedule_next_message(user_id: int):
    """
    Celery task to schedule the next proactive message.
    
    Args:
        user_id: Telegram user ID
    """
    logger.info(f"Starting Celery task schedule_next_message for user {user_id}")
    proactive_messaging_service.schedule_proactive_message(user_id)
    logger.info(f"Completed Celery task schedule_next_message for user {user_id}")

# Celery Beat Schedule
celery_app.conf.beat_schedule = {
    'check-proactive-messaging': {
        'task': 'proactive_messaging.send_proactive_message',
        'schedule': crontab(minute='*/30'),  # Run every 30 minutes
    },
}

# Default queue
celery_app.conf.task_default_queue = 'proactive_messaging'