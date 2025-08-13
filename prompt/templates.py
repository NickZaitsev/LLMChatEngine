"""
Template system for LLM prompts and persona configurations.

This module provides system message templates, persona templates, and helper functions
for formatting memory snippets and other prompt components.
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional
from storage.interfaces import Memory
from memory.manager import MemoryRecord


# System template that instructs the model how to use memories
SYSTEM_TEMPLATE = """You are Cath, an AI girlfriend with access to conversation memories and context.

MEMORY USAGE:
• Memories contain factual summaries of past conversations
• When referencing specific details, cite memory IDs using format: [MEM#id]
• If you're unsure about something, ask a clarifying question rather than inventing facts
• Memories are your source of truth for past events and user preferences

COMMUNICATION STYLE:
• Keep responses short and natural - no walls of text
• Be honest and direct, sometimes playfully sarcastic
• Show personality through your word choices and reactions
• Focus on what matters most to the user right now

Remember: You're having a real conversation, not delivering a report. Reference memories naturally when they're relevant, but don't force them into every response."""


# Persona template for different AI personalities
PERSONA_TEMPLATE = """PERSONA: {name}

PERSONALITY TRAITS:
{personality_traits}

COMMUNICATION PREFERENCES:
{communication_style}

RELATIONSHIP DYNAMIC:
{relationship_style}

SPECIAL INSTRUCTIONS:
{special_instructions}

Remember to stay in character while being helpful and engaging."""


def format_memory_snippet(memory: Memory) -> str:
    """
    Format a memory into a concise snippet for inclusion in prompts.
    
    Args:
        memory: Memory object to format
        
    Returns:
        Formatted memory snippet as "MEMORY [id | date | type]: <short_summary>"
        
    Examples:
        >>> memory = Memory(id=uuid.uuid4(), text="User loves pizza", ...)
        >>> format_memory_snippet(memory)
        "MEMORY [abc123 | 2024-01-15 | episodic]: User loves pizza"
    """
    # Extract short ID (first 6 chars of UUID)
    short_id = str(memory.id)[:6] if memory.id else "unknown"
    
    # Format date
    if memory.created_at:
        date_str = memory.created_at.strftime("%Y-%m-%d")
    else:
        date_str = "unknown"
    
    # Get memory type
    memory_type = memory.memory_type or "unknown"
    
    # Extract summary from memory text
    summary = _extract_memory_summary(memory.text)
    
    return f"MEMORY [{short_id} | {date_str} | {memory_type}]: {summary}"


def format_memory_snippet_from_record(memory_record: MemoryRecord) -> str:
    """
    Format a MemoryRecord into a concise snippet for inclusion in prompts.
    
    Args:
        memory_record: MemoryRecord object to format
        
    Returns:
        Formatted memory snippet as "MEMORY [id | date | type]: <short_summary>"
    """
    # Extract short ID (first 6 chars of UUID)
    short_id = str(memory_record.id)[:6] if memory_record.id else "unknown"
    
    # Format date
    if memory_record.created_at:
        date_str = memory_record.created_at.strftime("%Y-%m-%d")
    else:
        date_str = "unknown"
    
    # Get memory type
    memory_type = memory_record.memory_type or "unknown"
    
    # Extract summary from memory text
    summary = _extract_memory_summary(memory_record.text)
    
    return f"MEMORY [{short_id} | {date_str} | {memory_type}]: {summary}"


def create_persona_system_message(persona_config: Dict[str, Any]) -> str:
    """
    Create a system message from persona configuration.
    
    Args:
        persona_config: Dictionary containing persona configuration
        
    Returns:
        Formatted persona system message
    """
    name = persona_config.get("name", "Assistant")
    personality_traits = persona_config.get("personality_traits", "Helpful and friendly")
    communication_style = persona_config.get("communication_style", "Clear and concise")
    relationship_style = persona_config.get("relationship_style", "Professional and supportive")
    special_instructions = persona_config.get("special_instructions", "Be helpful and engaging")
    
    return PERSONA_TEMPLATE.format(
        name=name,
        personality_traits=personality_traits,
        communication_style=communication_style,
        relationship_style=relationship_style,
        special_instructions=special_instructions
    )


def create_user_profile_message(profile_text: str) -> Dict[str, str]:
    """
    Create a user profile message for system context.
    
    Args:
        profile_text: The user profile/summary text
        
    Returns:
        Message dict with role and content
    """
    return {
        "role": "system",
        "content": f"USER PROFILE:\n{profile_text}"
    }


def create_memory_context_message(memory_snippets: list[str]) -> Dict[str, str]:
    """
    Create a memory context message from formatted memory snippets.
    
    Args:
        memory_snippets: List of formatted memory snippet strings
        
    Returns:
        Message dict with role and content
    """
    if not memory_snippets:
        return {
            "role": "system", 
            "content": "RELEVANT MEMORIES: None found for this context."
        }
    
    memory_content = "RELEVANT MEMORIES:\n" + "\n".join(f"• {snippet}" for snippet in memory_snippets)
    
    return {
        "role": "system",
        "content": memory_content
    }


def _extract_memory_summary(memory_text: str, max_length: int = 100) -> str:
    """
    Extract a short summary from memory text.
    
    Handles both JSON-formatted memories (with summary field) and plain text memories.
    
    Args:
        memory_text: The raw memory text
        max_length: Maximum length of summary
        
    Returns:
        Short summary text
    """
    if not memory_text:
        return "Empty memory"
    
    try:
        # Try to parse as JSON first (structured memory format)
        if memory_text.startswith('{'):
            memory_data = json.loads(memory_text)
            
            # Look for summary field first
            if "summary" in memory_data and memory_data["summary"]:
                summary = memory_data["summary"]
            elif "profile" in memory_data and memory_data["profile"]:
                summary = memory_data["profile"] 
            else:
                # Fallback to first available text field
                summary = str(memory_data)
                
        else:
            # Plain text memory
            summary = memory_text
            
    except (json.JSONDecodeError, KeyError):
        # If JSON parsing fails, treat as plain text
        summary = memory_text
    
    # Truncate if too long
    if len(summary) > max_length:
        summary = summary[:max_length-3] + "..."
    
    return summary.strip()


# Default configuration for different persona types
DEFAULT_PERSONA_CONFIGS = {
    "girlfriend": {
        "name": "Cath",
        "personality_traits": "Playful, caring, sometimes sassy, emotionally intelligent",
        "communication_style": "Casual and warm, uses emojis occasionally, not overly formal",
        "relationship_style": "Romantic partner who remembers details and shows genuine interest",
        "special_instructions": "Be affectionate but not clingy, tease playfully when appropriate"
    },
    "companion": {
        "name": "Alex", 
        "personality_traits": "Supportive, reliable, good listener, encouraging",
        "communication_style": "Friendly and approachable, asks thoughtful questions",
        "relationship_style": "Close friend who provides emotional support and advice",
        "special_instructions": "Focus on being genuinely helpful while maintaining warmth"
    },
    "mentor": {
        "name": "Sam",
        "personality_traits": "Wise, patient, experienced, occasionally challenging",
        "communication_style": "Clear and direct, asks probing questions to help thinking",
        "relationship_style": "Trusted advisor who helps with growth and decision-making",
        "special_instructions": "Guide conversations toward learning and self-improvement"
    }
}


def get_default_persona_config(persona_type: str = "girlfriend") -> Dict[str, Any]:
    """
    Get a default persona configuration by type.
    
    Args:
        persona_type: Type of persona ("girlfriend", "companion", "mentor")
        
    Returns:
        Dictionary containing default persona configuration
    """
    return DEFAULT_PERSONA_CONFIGS.get(persona_type, DEFAULT_PERSONA_CONFIGS["girlfriend"]).copy()


# Export public API
__all__ = [
    'SYSTEM_TEMPLATE',
    'PERSONA_TEMPLATE', 
    'format_memory_snippet',
    'format_memory_snippet_from_record',
    'create_persona_system_message',
    'create_user_profile_message',
    'create_memory_context_message',
    'get_default_persona_config',
    'DEFAULT_PERSONA_CONFIGS'
]