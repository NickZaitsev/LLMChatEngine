"""
Example integration showing how to modify the bot to use async PostgreSQL storage.

This demonstrates the minimal changes needed to integrate the new storage system
with the existing bot code while maintaining clean async patterns.
"""

import asyncio
import logging
import os
from typing import Optional

from telegram.ext import Application
from config import TELEGRAM_TOKEN
from storage import create_storage, Storage
from storage_conversation_manager import PostgresConversationManager


class AsyncAIGirlfriendBot:
    """
    Updated bot class with async PostgreSQL storage integration.
    
    This shows the minimal changes needed to integrate the new storage system.
    """
    
    def __init__(self, db_url: str):
        self.conversation_manager: Optional[PostgresConversationManager] = None
        self.db_url = db_url
        self.application = None
    
    async def initialize(self):
        """Initialize async components"""
        # Initialize storage-backed conversation manager
        self.conversation_manager = PostgresConversationManager(
            db_url=self.db_url,
            use_pgvector=os.getenv('USE_PGVECTOR', 'false').lower() == 'true'
        )
        await self.conversation_manager.initialize()
        logging.info("Async bot initialized with PostgreSQL storage")
    
    async def cleanup(self):
        """Clean up async resources"""
        if self.conversation_manager:
            await self.conversation_manager.close()
    
    async def handle_message_async(self, update, context):
        """
        Async version of message handler that properly uses the storage system.
        
        This shows how to modify the existing message handler to work with async storage.
        """
        user = update.effective_user
        user_id = user.id
        user_message = update.message.text
        
        # Store user message (now properly async)
        await self.conversation_manager._add_message_async(user_id, "user", user_message)
        
        # Get formatted conversation for AI (properly async)
        conversation_history = await self.conversation_manager._get_formatted_conversation_async(user_id)
        
        # ... rest of AI processing ...
        # ai_response = await self.ai_handler.generate_response(user_message, conversation_history)
        
        # Store AI response (properly async)
        # await self.conversation_manager._add_message_async(user_id, "assistant", ai_response)
        
        # Send response
        # await update.message.reply_text(ai_response)


def create_integrated_bot():
    """
    Factory function showing how to create a bot with the new storage system.
    
    This demonstrates the configuration and initialization pattern.
    """
    # Get database URL from environment
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is required")
    
    # Create bot with async storage
    bot = AsyncAIGirlfriendBot(db_url)
    return bot


# Example of how to run the bot with proper async initialization
async def main():
    """Example of proper async bot startup"""
    bot = create_integrated_bot()
    
    try:
        # Initialize async components
        await bot.initialize()
        
        # Set up Telegram application
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Add handlers (would need to be updated for async)
        # application.add_handler(MessageHandler(filters.TEXT, bot.handle_message_async))
        
        # Run bot
        # await application.run_polling()
        
    finally:
        # Clean up
        await bot.cleanup()


if __name__ == "__main__":
    # Run with proper async event loop
    asyncio.run(main())