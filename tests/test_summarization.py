import pytest
import asyncio
from uuid import uuid4
from app_context import AppContext
from ai_handler import AIHandler
from prompt.assembler import PromptAssembler
from storage.repos import PostgresConversationRepo, PostgresMessageRepo
from memory.tasks import create_conversation_summary_async

@pytest.mark.asyncio
async def test_summarization_flow(app_context: AppContext):
    """
    Test the full summarization flow, from triggering to verification.
    """
    # 1. Setup: Create user, persona, and conversation
    user_repo = app_context.conversation_manager.storage.users
    persona_repo = app_context.conversation_manager.storage.personas
    conversation_repo = app_context.conversation_manager.storage.conversations
    message_repo = app_context.conversation_manager.storage.messages

    user = await user_repo.create_user(username=f"test_user_{uuid4()}")
    persona = await persona_repo.create_persona(user_id=str(user.id), name="test_persona")
    conversation = await conversation_repo.create_conversation(user_id=str(user.id), persona_id=str(persona.id))

    # 2. Add messages to exceed the summary threshold
    for i in range(app_context.config.MAX_ACTIVE_MESSAGES + 5):
        await message_repo.append_message(
            conversation_id=str(conversation.id),
            role="user",
            content=f"This is message {i}."
        )

    # 3. Manually trigger the summarization task
    await create_conversation_summary_async(str(conversation.id))

    # 4. Verification
    updated_conversation = await conversation_repo.get_conversation(str(conversation.id))
    
    assert updated_conversation.summary is not None
    assert updated_conversation.last_summarized_message_id is not None

    active_messages_count = await message_repo.count_active_messages(
        str(conversation.id),
        updated_conversation.last_summarized_message_id
    )
    
    assert active_messages_count < app_context.config.MAX_ACTIVE_MESSAGES