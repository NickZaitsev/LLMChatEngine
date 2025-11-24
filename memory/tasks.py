"""
Celery tasks for memory management, including conversation summarization.
"""

import logging
from celery import Celery
import asyncio
from app_context import get_app_context
from config import SUMMARIZATION_PROMPT
import celeryconfig

# Initialize Celery
celery_app = Celery('memory_tasks')
celery_app.config_from_object(celeryconfig)

logger = logging.getLogger(__name__)


@celery_app.task(name='memory.tasks.create_conversation_summary')
def create_conversation_summary(conversation_id: str):
    """
    Celery task to create a summary of a conversation.
    """
    logger.info(f"Starting summarization task for conversation_id: {conversation_id}")
    try:
        asyncio.run(create_conversation_summary_async(conversation_id))
    except Exception as e:
        logger.error(f"Error in summarization task for conversation_id {conversation_id}: {e}", exc_info=True)
        raise


async def create_conversation_summary_async(conversation_id: str):
    """
    Async implementation of the conversation summarization logic.
    """
    app_context = await get_app_context()
    conversation_repo = app_context.conversation_manager.storage.conversations
    message_repo = app_context.conversation_manager.storage.messages
    ai_handler = app_context.ai_handler

    # 1. Fetch the conversation
    conversation = await conversation_repo.get_conversation(conversation_id)
    if not conversation:
        logger.error(f"Conversation with ID {conversation_id} not found.")
        return

    # 2. Fetch messages to summarize
    messages_to_summarize = await message_repo.get_messages_for_summary(
        conversation_id,
        conversation.last_summarized_message_id
    )

    if not messages_to_summarize:
        logger.info(f"No new messages to summarize for conversation_id: {conversation_id}")
        return

    # 3. Use only the oldest half of messages to avoid context length issues
    half_count = len(messages_to_summarize) // 2
    if half_count > 0:
        messages_to_summarize = messages_to_summarize[:half_count]
        logger.info(f"Using oldest {len(messages_to_summarize)} messages for summarization (out of {len(messages_to_summarize) * 2} total)")
    else:
        # If only 1 message, use it
        messages_to_summarize = messages_to_summarize[:1]

    # 4. Prepare the text for summarization
    text_to_summarize = "\n".join([f"{msg.role}: {msg.content}" for msg in messages_to_summarize])

    # 4. Generate the new summary with error handling for context length
    prompt = SUMMARIZATION_PROMPT.format(
        existing_summary=conversation.summary or "This is the beginning of the conversation.",
        text=text_to_summarize
    )

    try:
        new_summary = await ai_handler.get_response(prompt)
    except Exception as e:
        error_message = str(e).lower()
        if any(pattern in error_message for pattern in ["context length", "token limit", "too long", "maximum context"]):
            logger.warning(f"Context length exceeded for conversation {conversation_id}. Reducing message count and retrying.")
            # If context is too long, try with even fewer messages (quarter instead of half)
            quarter_count = len(messages_to_summarize) // 4
            if quarter_count > 0:
                messages_to_summarize = messages_to_summarize[:quarter_count]
                text_to_summarize = "\n".join([f"{msg.role}: {msg.content}" for msg in messages_to_summarize])
                logger.info(f"Retrying with oldest {len(messages_to_summarize)} messages for summarization")

                # Retry with reduced context
                prompt = SUMMARIZATION_PROMPT.format(
                    existing_summary=conversation.summary or "This is the beginning of the conversation.",
                    text=text_to_summarize
                )
                new_summary = await ai_handler.get_response(prompt)
            else:
                # If we can't reduce further, skip summarization for this conversation
                logger.error(f"Cannot reduce context further for conversation {conversation_id}. Skipping summarization.")
                return
        else:
            # Re-raise non-context-length errors
            raise e

    # 5. Update the conversation
    last_message_id = messages_to_summarize[-1].id
    await conversation_repo.update_conversation(
        conversation_id=conversation_id,
        summary=new_summary,
        last_summarized_message_id=last_message_id
    )

    logger.info(f"Successfully summarized conversation {conversation_id}. Last message ID: {last_message_id}")
