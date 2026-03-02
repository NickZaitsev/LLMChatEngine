"""
Celery tasks for memory management.

Includes:
- create_conversation_summary: Summarises a conversation (unchanged).
- extract_memories: Chunks and embeds conversation fragments (rewritten:
  no LLM fact extraction, uses AdaptiveChunker + batch embed).
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
    # 1. Fetch the conversation
    conversation = await conversation_repo.get_conversation(conversation_id)
    if not conversation:
        logger.error(f"Conversation with ID {conversation_id} not found.")
        return

    ai_handler, _ = await app_context.get_ai_runtime_for_bot(conversation.bot_id)

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


# -----------------------------------------------------------------------
# Memory extraction — adaptive chunking + direct embedding (no LLM)
# -----------------------------------------------------------------------

@celery_app.task(name='memory.tasks.extract_memories')
def extract_memories(user_id: str, conversation_id: str):
    """
    Celery task to chunk and embed conversation fragments.

    This is the rewritten version: no LLM fact extraction.
    Messages are grouped into adaptive token-aware chunks and embedded
    directly into pgvector.
    """
    logger.info(
        "Starting memory chunk-embed task for user_id: %s, conversation_id: %s",
        user_id, conversation_id,
    )
    try:
        asyncio.run(extract_memories_async(user_id, conversation_id))
    except Exception as e:
        logger.error("Error in memory chunk-embed task: %s", e, exc_info=True)
        raise


async def extract_memories_async(user_id: str, conversation_id: str):
    """
    Async implementation of memory chunking + embedding.

    1. Fetch unprocessed messages (after last_memorized_message_id).
    2. Run AdaptiveChunker to group them into token-aware chunks.
    3. Batch-embed and store via the memory manager.
    4. Update last_memorized_message_id.
    """
    from config import MEMORY_CHUNK_MAX_MESSAGES, MEMORY_CHUNK_TARGET_TOKENS
    from memory.adaptive_chunker import AdaptiveChunker

    app_context = await get_app_context()
    conversation_repo = app_context.conversation_manager.storage.conversations
    message_repo = app_context.conversation_manager.storage.messages
    memory_manager = app_context.memory_manager

    if not memory_manager:
        logger.error("Memory manager not available for chunk-embed task")
        return

    # 1. Fetch the conversation to get last_memorized_message_id
    conversation = await conversation_repo.get_conversation(conversation_id)
    if not conversation:
        logger.error("Conversation %s not found", conversation_id)
        return

    last_memorized_id = getattr(conversation, 'last_memorized_message_id', None)

    # 2. Fetch unprocessed messages
    messages = await message_repo.get_messages_for_summary(
        conversation_id, last_memorized_id
    )
    if not messages:
        logger.info(
            "No new messages to process for memory chunking (conversation %s)",
            conversation_id,
        )
        return

    logger.info("Processing %d messages for memory chunking", len(messages))

    # 3. Create adaptive chunks
    chunker = AdaptiveChunker(
        max_messages=MEMORY_CHUNK_MAX_MESSAGES,
        target_tokens=MEMORY_CHUNK_TARGET_TOKENS,
    )
    chunks = chunker.create_chunks(messages)

    if not chunks:
        logger.info("No complete turns to chunk in conversation %s", conversation_id)
    else:
        # 4. Batch-embed and store
        stored_count = await memory_manager.store_conversation_chunks(
            user_id=user_id,
            chunks=chunks,
            conversation_id=conversation_id,
            bot_id=str(conversation.bot_id) if conversation.bot_id else None,
        )
        logger.info(
            "Stored %d conversation chunk(s) for user %s", stored_count, user_id
        )

    # 5. Update last_memorized_message_id
    last_msg_id = messages[-1].id
    await conversation_repo.update_conversation(
        conversation_id=conversation_id,
        last_memorized_message_id=last_msg_id,
    )
    logger.info(
        "Updated last_memorized_message_id to %s for conversation %s",
        last_msg_id, conversation_id,
    )
