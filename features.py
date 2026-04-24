"""
Feature flags system for multi-bot architecture.

This module defines the available features that can be toggled per-bot
and provides utilities for checking feature availability.
"""

from enum import Enum
from typing import Dict, Any, TYPE_CHECKING, Optional
from functools import wraps

if TYPE_CHECKING:
    from storage.models import Bot


class BotFeature(Enum):
    """Enumeration of features that can be toggled per-bot."""
    
    # Core features
    PROACTIVE_MESSAGING = "proactive_messaging"
    MEMORY = "memory"
    
    # Message handling features
    VOICE_MESSAGES = "voice_messages"
    PHOTO_REACTIONS = "photo_reactions"
    
    # User interaction features
    PERSONALITY_SWITCH = "personality_switch"
    USER_SETTINGS = "user_settings"
    
    # Advanced features
    BUFFER_MANAGER = "buffer_manager"
    MESSAGE_QUEUE = "message_queue"


# Default feature flags for new bots
DEFAULT_FEATURE_FLAGS: Dict[str, bool] = {
    BotFeature.PROACTIVE_MESSAGING.value: True,
    BotFeature.MEMORY.value: True,
    BotFeature.VOICE_MESSAGES.value: True,
    BotFeature.PHOTO_REACTIONS.value: True,
    BotFeature.PERSONALITY_SWITCH.value: True,
    BotFeature.USER_SETTINGS.value: True,
    BotFeature.BUFFER_MANAGER.value: True,
    BotFeature.MESSAGE_QUEUE.value: True,
}


def has_feature(feature_flags: Optional[Dict[str, Any]], feature: BotFeature) -> bool:
    """
    Check if a feature is enabled in the given feature flags dict.
    
    Args:
        feature_flags: Dictionary of feature flags
        feature: The feature to check
        
    Returns:
        True if the feature is enabled, False otherwise
    """
    feature_flags = feature_flags or {}
    return feature_flags.get(feature.value, DEFAULT_FEATURE_FLAGS.get(feature.value, False))


def has_feature_from_bot(bot: "Bot", feature: BotFeature) -> bool:
    """
    Check if a bot has a specific feature enabled.
    
    Args:
        bot: The Bot instance to check
        feature: The feature to check
        
    Returns:
        True if the feature is enabled, False otherwise
    """
    return has_feature(bot.feature_flags, feature)


def require_feature(feature: BotFeature):
    """
    Decorator to require a feature for a handler method.
    
    If the feature is not enabled, the handler will return early
    without executing.
    
    Args:
        feature: The feature required for this handler
        
    Returns:
        Decorator function
        
    Usage:
        @require_feature(BotFeature.PROACTIVE_MESSAGING)
        async def handle_proactive_message(self, ...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Check if bot_config exists and has the feature
            if hasattr(self, 'bot_config') and self.bot_config:
                if not has_feature(self.bot_config.feature_flags, feature):
                    return None
            return await func(self, *args, **kwargs)
        return wrapper
    return decorator


def get_enabled_features(feature_flags: Optional[Dict[str, Any]]) -> list:
    """
    Get a list of all enabled features.
    
    Args:
        feature_flags: Dictionary of feature flags
        
    Returns:
        List of enabled BotFeature values
    """
    return [
        feature for feature in BotFeature
        if has_feature(feature_flags, feature)
    ]


def get_disabled_features(feature_flags: Optional[Dict[str, Any]]) -> list:
    """
    Get a list of all disabled features.
    
    Args:
        feature_flags: Dictionary of feature flags
        
    Returns:
        List of disabled BotFeature values
    """
    return [
        feature for feature in BotFeature
        if not has_feature(feature_flags, feature)
    ]
