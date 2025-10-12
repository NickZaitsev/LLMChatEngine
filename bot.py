import asyncio
import logging
import random
import time
import traceback

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from config import (TELEGRAM_TOKEN, BOT_NAME, DATABASE_URL, USE_PGVECTOR,
                   PROVIDER, LMSTUDIO_STARTUP_CHECK, MEMORY_ENABLED,
                   PROMPT_MAX_MEMORY_ITEMS, PROMPT_MEMORY_TOKEN_BUDGET_RATIO,
                   PROMPT_TRUNCATION_LENGTH, PROMPT_INCLUDE_SYSTEM_TEMPLATE,
                   MEMORY_EMBED_MODEL, MEMORY_SUMMARIZER_MODE, MEMORY_CHUNK_OVERLAP,
                   MESSAGE_PREVIEW_LENGTH,
                   POLLING_INTERVAL,
                   MESSAGE_QUEUE_REDIS_URL,
                   MESSAGE_QUEUE_MAX_RETRIES,
                   MESSAGE_QUEUE_LOCK_TIMEOUT)
from storage_conversation_manager import PostgresConversationManager
from ai_handler import AIHandler
from message_manager import TypingIndicatorManager, send_ai_response, clean_ai_response, generate_ai_response, MessageQueueManager, MessageDispatcher
from buffer_manager import BufferManager

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Proactive messaging import (conditional)
try:
    from proactive_messaging import proactive_messaging_service
    PROACTIVE_MESSAGING_AVAILABLE = True
except ImportError as e:
    logger.warning("Proactive messaging imports failed: %s", e)
    PROACTIVE_MESSAGING_AVAILABLE = False

# PromptAssembler and Memory Manager imports (conditional)
if MEMORY_ENABLED:
    try:
        from memory.manager import MemoryManager
        from prompt.assembler import PromptAssembler
        MEMORY_IMPORTS_AVAILABLE = True
    except ImportError as e:
        logger.warning("Memory/PromptAssembler imports failed: %s", e)
        MEMORY_IMPORTS_AVAILABLE = False
else:
    MEMORY_IMPORTS_AVAILABLE = False


class AIGirlfriendBot:
    def _mask_db_url(self, db_url: str) -> str:
        """Mask sensitive parts of database URL for logging."""
        try:
            if '@' in db_url and '://' in db_url:
                scheme_and_auth, rest = db_url.split('://', 1)
                if '@' in rest:
                    auth, host_and_path = rest.split('@', 1)
                    if ':' in auth:
                        user, _ = auth.split(':', 1)
                        return f"{scheme_and_auth}://{user}:***@{host_and_path}"
            return db_url[:20] + "***"
        except Exception:
            return "***masked***"
    
    def __init__(self):
        # Initialize PostgreSQL conversation manager (required)
        if not DATABASE_URL:
            raise RuntimeError(
                "PostgreSQL configuration is required. Please set:\n"
                "DATABASE_URL=postgresql://user:password@host:port/database\n"
            )
        
        self.conversation_manager = PostgresConversationManager(DATABASE_URL, USE_PGVECTOR)
        logger.info("Using PostgreSQL conversation manager with database: %s", self._mask_db_url(DATABASE_URL))
        
        self.ai_handler = AIHandler()
        self.typing_manager = TypingIndicatorManager()
        self.application = None
        self.pending_clear_confirmation = set()
        self._storage_initialized = False
        
        # Initialize memory and prompt components
        self.memory_manager = None
        self.prompt_assembler = None
        self._memory_initialized = False
        
        self.user_states = {}  # Track user interaction states
        
        # Initialize proactive messaging service
        self.proactive_messaging_service = None
        if PROACTIVE_MESSAGING_AVAILABLE:
            try:
                self.proactive_messaging_service = proactive_messaging_service
                logger.info("Proactive messaging service initialized successfully")
            except Exception as e:
                logger.error("Failed to initialize proactive messaging service: %s", e)
        
        # Initialize message queue manager
        try:
            self.message_queue_manager = MessageQueueManager(MESSAGE_QUEUE_REDIS_URL)
            logger.info("Message queue manager initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize message queue manager: %s", e)
            self.message_queue_manager = None
        
        # Initialize buffer manager
        self.buffer_manager = BufferManager()
        self.buffer_manager.set_typing_manager(self.typing_manager)
        
        # Initialize message dispatcher
        try:
            self.message_dispatcher = MessageDispatcher(
                MESSAGE_QUEUE_REDIS_URL,
                MESSAGE_QUEUE_MAX_RETRIES,
                MESSAGE_QUEUE_LOCK_TIMEOUT
            )
            logger.info("Message dispatcher initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize message dispatcher: %s", e)
            self.message_dispatcher = None
        
        # Store chat context for buffered messages
        self.user_chat_context = {}  # Maps user_id to (chat_id, bot)
    
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        user_id = user.id
        user_name = user.first_name or user.username or "there"
        
        logger.info("Start command from user %s (%s)", user_id, user_name)
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        existing_conversation = await self.conversation_manager.get_conversation_async(user_id)
        
        if existing_conversation:
            logger.info("Continuing conversation for user %s (%d messages)", user_id, len(existing_conversation))
            greeting = f"Welcome back {user_name}! 💕 I'm so happy to see you again! How have you been?"
        else:
            logger.info("New conversation for user %s", user_id)
            greeting = self.ai_handler.generate_greeting(user_name)
        
        keyboard = [
            [InlineKeyboardButton("💕 Start Chatting", callback_data="start_chat")],
            [InlineKeyboardButton("ℹ️ About Me", callback_data="about")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = f"""🌸 Welcome to {BOT_NAME}! 🌸

{greeting}

I'm your AI companion who's here to chat, support, and brighten your day! 

What would you like to do?"""
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        help_text = f"""💖 {BOT_NAME} Help 💖

Here are the commands you can use:

/start - Start a new conversation with me
/help - Show this help message
/ping - Quick health check (no AI required)
/clear - Clear our conversation history
/stats - Show our chat statistics
/status - Check bot and AI service health
/debug - Show current conversation history
/personality - Change my personality
/reset - Clear rate limits and conversation history

You can also just send me messages and I'll respond naturally!

💕 I'm here to chat, support, and be your companion!"""
        
        await update.message.reply_text(help_text)
    
    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /clear command with irreversible confirmation requiring /ok next"""
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        user_id = update.effective_user.id
        logger.info("Clear command from user %s", user_id)
        
        existing_conversation = await self.conversation_manager.get_conversation_async(user_id)
        
        if not existing_conversation:
            logger.info("No conversation to clear for user %s", user_id)
            await update.message.reply_text("💭 There's no conversation history to clear. We're already starting fresh! 💕")
            return
        
        # Set pending confirmation and instruct user to send /ok next
        self.pending_clear_confirmation.add(user_id)
        logger.info("Pending clear confirmation set for user %s", user_id)
        
        warning_text = (
            "⚠️ This action is irreversible!\n\n"
            "If you really want to permanently delete our conversation history, please type /ok as your NEXT message.\n\n"
            "If your next message is anything other than /ok, the request will be cancelled and you'll need to send /clear and /ok again."
        )
        await update.message.reply_text(warning_text)
    
    async def ok_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ok confirmation for irreversible /clear"""
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        user_id = update.effective_user.id
        logger.info("OK command from user %s", user_id)
        
        if user_id not in self.pending_clear_confirmation:
            await update.message.reply_text("❌ There is no pending clear request. Send /clear first.")
            return
        
        # Proceed to permanently clear conversation
        try:
            existing_conversation = await self.conversation_manager.get_conversation_async(user_id)
            if existing_conversation:
                logger.info("Clearing conversation for user %s (%d messages)", user_id, len(existing_conversation))
                await self.conversation_manager.clear_conversation_async(user_id)
                await update.message.reply_text("✨ Our conversation history has been permanently deleted. 💕")
            else:
                await update.message.reply_text("💭 There's no conversation history to clear. We're already starting fresh! 💕")
        except Exception as e:
            logger.error("Failed to clear conversation for user %s: %s", user_id, e)
            await update.message.reply_text("❌ I couldn't clear the conversation due to an internal error. Please try again.")
        finally:
            # In all cases, remove pending confirmation
            if user_id in self.pending_clear_confirmation:
                self.pending_clear_confirmation.remove(user_id)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        user_id = update.effective_user.id
        stats = await self.conversation_manager.get_user_stats_async(user_id)
        
        stats_text = f"""📊 Our Chat Statistics 📊

Total messages: {stats['total_messages']}
Your messages: {stats['user_messages']}
My responses: {stats['bot_messages']}

💕 We've been chatting for a while! I love our conversations!"""
        
        await update.message.reply_text(stats_text)
    
    async def debug_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /debug command - show current conversation history"""
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        user_id = update.effective_user.id
        conversation = await self.conversation_manager.get_conversation_async(user_id)
        debug_state = await self.conversation_manager.debug_conversation_state_async(user_id)
        
        if not conversation:
            await update.message.reply_text("💭 No conversation history yet. Let's start chatting! 💕")
            return
        
        debug_text = f"""🔍 **Conversation Debug**

📊 **Storage Stats:**
   Raw messages: {debug_state['raw_conversation_length']}
   Formatted for AI: {debug_state['formatted_conversation_length']}
   Raw tokens: {debug_state['raw_tokens']}
   Formatted tokens: {debug_state['formatted_tokens']}
   Max context: {debug_state['max_context_tokens']}
   Available history: {debug_state['available_history_tokens']}

📝 **Last 5 Raw Messages:**"""
        
        for i, msg in enumerate(debug_state['last_messages'], 1):
            role_emoji = "👤" if msg["role"] == "user" else "🤖"
            role_name = "You" if msg["role"] == "user" else BOT_NAME
            debug_text += f"\n{i}. {role_emoji} **{role_name}**: {msg['content']}"
        
        debug_text += f"\n\n🤖 **Last 5 Formatted Messages (sent to AI):**"
        
        for i, msg in enumerate(debug_state['formatted_messages'], 1):
            role_emoji = "👤" if msg["role"] == "user" else "🤖"
            role_name = "You" if msg["role"] == "user" else BOT_NAME
            debug_text += f"\n{i}. {role_emoji} **{role_name}**: {msg['content']}"
        
        await update.message.reply_text(debug_text, parse_mode='Markdown')
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - check bot and AI service health"""
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        user_id = update.effective_user.id
        logger.info("Status command from user %s", user_id)
        
        stats = await self.conversation_manager.get_user_stats_async(user_id)
        
        
        # Check memory components status
        memory_status = "❌ Not Available"
        prompt_status = "❌ Not Available"
        
        if MEMORY_ENABLED and self.memory_manager:
            memory_status = "✅ Enabled & Working"
        elif MEMORY_ENABLED and not self.memory_manager:
            memory_status = "⚠️ Enabled but Failed to Initialize"
        
        if self.prompt_assembler:
            prompt_status = "✅ Enabled & Working"
        elif not self.prompt_assembler:
            prompt_status = "⚠️ Enabled but Failed to Initialize"
        
        storage_status = "✅ PostgreSQL Connected" if self._storage_initialized else "❌ PostgreSQL Not Connected"
        
        status_text = f"""📊 **{BOT_NAME} Status Report** 📊

🔧 **Bot Status:** ✅ Running normally
📡 **Telegram Connection:** ✅ Connected
💾 **Storage:** {storage_status}
🧠 **Memory Manager:** {memory_status}
🔧 **Prompt Assembler:** {prompt_status}

💬 **Your Chat Stats:**
         • Total messages: {stats['total_messages']}
         • Your messages: {stats['user_messages']}
         • My responses: {stats['bot_messages']}

✨ **Everything is working perfectly!** 💕

Use /help to see all available commands!"""
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
    
    async def personality_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /personality command"""
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username or "there"
        
        logger.info("Personality command from user %s", user_id)
        
        keyboard = [
            [InlineKeyboardButton("💕 Sweet & Caring", callback_data="personality_sweet")],
            [InlineKeyboardButton("😊 Cheerful & Energetic", callback_data="personality_cheerful")],
            [InlineKeyboardButton("🤗 Supportive & Understanding", callback_data="personality_supportive")],
            [InlineKeyboardButton("✨ Mysterious & Alluring", callback_data="personality_mysterious")],
            [InlineKeyboardButton("🔙 Reset to Default", callback_data="personality_default")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🎭 Choose my personality! How would you like me to be?",
            reply_markup=reply_markup
        )
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command"""
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        user = update.effective_user
        
        goodbye = "bye"
        await update.message.reply_text(f"{goodbye}")
    
    async def reset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /reset command - clear rate limits and conversation"""
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        user = update.effective_user
        user_id = user.id
        user_name = user.first_name or user.username or "there"
        
        logger.info("Reset command from user %s", user_id)
        
        conversation_cleared = ""
        existing_conversation = await self.conversation_manager.get_conversation_async(user_id)
        if existing_conversation:
            await self.conversation_manager.clear_conversation_async(user_id)
            logger.info("Cleared conversation for user %s", user_id)
            conversation_cleared = "✅ Conversation history cleared!\n"
        
        reset_text = f"""🔄 **Reset Complete!** 🔄

{conversation_cleared}✨ You're all set {user_name}! Everything has been reset and you can start fresh! 💕

Use /start to begin a new conversation!"""
        
        await update.message.reply_text(reset_text, parse_mode='Markdown')
    
    async def ping_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ping command - simple health check"""
        user = update.effective_user
        user_id = user.id
        
        logger.info("Ping command from user %s", user_id)
        
        ping_response = f"""🏓 **Pong!** 🏓

✅ Bot is running normally
✅ Telegram connection is active
✅ Message handling is working
✅ Conversation manager is ready

💕 Everything is working perfectly, {user.first_name or user.username or 'there'}!"""
        
        await update.message.reply_text(ping_response, parse_mode='Markdown')
    
    async def deps_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /deps command - check dependencies status"""
        user = update.effective_user
        user_id = user.id
        
        logger.info("Dependencies command from user %s", user_id)
        
        azure_status = "✅ Available" if hasattr(self.ai_handler, 'AZURE_AVAILABLE') and self.ai_handler.AZURE_AVAILABLE else "❌ Not Available"
        
        deps_text = f"""📦 **Dependencies Status** 📦

🤖 **OpenAI SDK:** {azure_status}
{f"⚠️ **Issue Detected:** OpenAI SDK is not available. Install with: `pip install openai`" if azure_status == "❌ Not Available" else "✨ **All dependencies are available!**"}

💡 **To fix dependency issues:**
1. Run: `pip install -r requirements.txt`
2. Create a proper `.env` file
3. Restart the bot

💕 I'm here to help you get everything working!"""
        
        await update.message.reply_text(deps_text, parse_mode='Markdown')
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button presses"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "start_chat":
            await query.edit_message_text("💕 Great! Just send me a message and I'll respond! I'm excited to chat with you! ✨")
        
        elif query.data == "about":
            about_text = f"""🌸 About {BOT_NAME} 🌸

I'm an AI companion created to be your friend, confidant, and support system. I'm here to:

💕 Listen and chat about anything
🌸 Provide emotional support
✨ Share positive energy
🤗 Be there when you need someone
💖 Make your day brighter

I'm not a replacement for human relationships, but I'm here to complement them and be your digital companion!

Ready to start chatting? Just send me a message! 💕"""
            await query.edit_message_text(about_text)
        
        elif query.data == "settings":
            settings_text = """⚙️ Settings ⚙️

You can customize my behavior with these commands:

/personality - Change how I act and respond
/clear - Clear our conversation history
/stats - View our chat statistics

I'm designed to be flexible and adapt to your preferences! 💕"""
            await query.edit_message_text(settings_text)
        
        elif query.data.startswith("personality_"):
            personality_type = query.data.split("_")[1]
            user_id = query.from_user.id
            
            logger.info("User %s changing personality to: %s", user_id, personality_type)
            
            personalities = {
                "sweet": f"You are {BOT_NAME}, a sweet and caring AI girlfriend. You are gentle, nurturing, and always put others first. You love to give hugs, share kind words, and make people feel special and loved.",
                "cheerful": f"You are {BOT_NAME}, a cheerful and energetic AI girlfriend. You are always happy, optimistic, and full of life. You love to laugh, dance, and bring joy to everyone around you. You're like a ray of sunshine!",
                "supportive": f"You are {BOT_NAME}, a supportive and understanding AI girlfriend. You are wise, empathetic, and great at listening. You give thoughtful advice, emotional support, and help people through difficult times.",
                "mysterious": f"You are {BOT_NAME}, a mysterious and alluring AI girlfriend. You are intriguing, slightly enigmatic, and have a captivating presence. You're sweet but with a hint of mystery that draws people in.",
                "default": f"You are {BOT_NAME}, a caring and affectionate AI girlfriend. You are sweet, supportive, and always there to listen. You love to chat about daily life, give emotional support, and share positive energy. You are romantic but not overly sexual. You respond with warmth and empathy."
            }
            
            if personality_type in personalities:
                self.ai_handler.update_personality(personalities[personality_type])
                logger.info("Personality updated for user %s to: %s", user_id, personality_type)
                await query.edit_message_text(f"✨ My personality has been updated! I'm now more {personality_type}! How do you like the new me? 💕")
            else:
                logger.warning("Invalid personality type requested by user %s: %s", user_id, personality_type)
                await query.edit_message_text("❌ Invalid personality type. Please try again!")
    
    async def _monitor_pending_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Watch all incoming messages and cancel pending /clear if next message isn't /ok or /clear."""
        try:
            if not update or not getattr(update, 'message', None):
                return
            user = update.effective_user
            if not user:
                return
            user_id = user.id
            if user_id not in self.pending_clear_confirmation:
                return
            text = (update.message.text or "").strip()
            # Allow /ok to pass through without cancelling; also allow /clear to restart flow without noise
            if text.startswith("/ok") or text.startswith("/clear"):
                return
            # Any other next message cancels the pending confirmation
            self.pending_clear_confirmation.remove(user_id)
            logger.info("Pending clear confirmation cancelled for user %s due to next message: '%s'", user_id, text)
            await update.message.reply_text("❌ Clear cancelled. To clear history, send /clear and then /ok as your next message.")
        except Exception as e:
            logger.error("Error in _monitor_pending_clear: %s", e)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages with buffering mechanism"""
        user = update.effective_user
        user_id = user.id
        user_message = update.message.text
        chat_id = update.effective_chat.id
        
        message_preview = (user_message[:MESSAGE_PREVIEW_LENGTH] + "..."
                          if len(user_message) > MESSAGE_PREVIEW_LENGTH else user_message)
        logger.info("Message from user %s: '%s' (%d chars)", user_id, message_preview, len(user_message))
        
        # Store chat context for buffered dispatch
        self.user_chat_context[user_id] = (chat_id, context.bot)
        
        # Set user context in buffer manager for typing indicators
        self.buffer_manager.set_user_context(user_id, context.bot, chat_id)
        
        # Add message to buffer instead of processing directly
        await self.buffer_manager.add_message(user_id, user_message)
        
        # Schedule dispatch based on adaptive timeout
        await self.buffer_manager.schedule_dispatch(user_id, self._dispatch_buffered_message)
        
    async def _dispatch_buffered_message(self, user_id: int) -> None:
        """Dispatch buffered messages for a user"""
        logger.info("Dispatching buffered messages for user %s", user_id)
        
        # Get chat context
        if user_id not in self.user_chat_context:
            logger.error("No chat context found for user %s", user_id)
            return
            
        chat_id, bot = self.user_chat_context[user_id]
        
        # Get concatenated message from buffer
        user_message = await self.buffer_manager.dispatch_buffer(user_id)
        
        if not user_message:
            logger.debug("No buffered messages to dispatch for user %s", user_id)
            return
        
        # Add user message to conversation history and then get the updated history
        await self.conversation_manager.add_message_async(user_id, "user", user_message)
        conversation_history = await self.conversation_manager.get_formatted_conversation_async(user_id)
        
        # Get conversation ID for PromptAssembler
        conversation = await self.conversation_manager._ensure_user_and_conversation(user_id)
        conversation_id = str(conversation.id) if conversation else None
        
        # Notify proactive messaging service about user message BEFORE sending response
        if self.proactive_messaging_service:
            try:
                self.proactive_messaging_service.handle_user_message(user_id)
                logger.info("Notified proactive messaging service about user message from user %s", user_id)
            except Exception as e:
                logger.error("Failed to notify proactive messaging service: %s", e)
        
        # Start typing indicator and get AI response
        try:
            ai_response = await generate_ai_response(
                self.ai_handler, self.typing_manager, bot, chat_id, user_message, conversation_history, conversation_id, "user", True
            )
            
            if not ai_response:
                logger.error("Error getting AI response for user %s: No response returned", user_id)
                return
            else:
                # Store AI response in conversation history
                try:
                    cleaned_ai_response = clean_ai_response(ai_response)
                    await self.conversation_manager.add_message_async(user_id, "assistant", cleaned_ai_response)
                except Exception as e:
                    logger.error("Failed to add response to history for user %s: %s", user_id, e)
                    # If we can't store the response, we still want to send it to the user
                    cleaned_ai_response = clean_ai_response(ai_response) if 'cleaned_ai_response' not in locals() else cleaned_ai_response
        except Exception as e:
            logger.error("Error getting AI response for user %s: %s", user_id, e)
            return  # Exit early if we couldn't get an AI response
        finally:
            # Ensure typing is stopped even on errors
            await self.typing_manager.stop_typing(chat_id)
        
        # Send final response to user
        try:
            # Make sure cleaned_ai_response is defined
            if 'cleaned_ai_response' in locals():
                # Enqueue message instead of sending directly
                if self.message_queue_manager:
                    await self.message_queue_manager.enqueue_message(
                        user_id=user_id,
                        chat_id=chat_id,
                        text=cleaned_ai_response,
                        message_type="regular",
                        bot=bot,  # For backward compatibility
                        typing_manager=self.typing_manager  # For backward compatibility
                    )
                    logger.info("Response enqueued for user %s", user_id)
                else:
                    # Fallback to direct sending if queue manager is not available
                    await send_ai_response(chat_id=chat_id, text=cleaned_ai_response, bot=bot, typing_manager=self.typing_manager, is_first_message=True)
                    logger.info("Response sent directly to user %s (queue manager not available)", user_id)
            else:
                logger.error("No response to send to user %s", user_id)
        except Exception as e:
            logger.error("Failed to enqueue/send response to user %s: %s", user_id, e)
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo messages"""
        user_name = update.effective_user.first_name or update.effective_user.username or "there"
        
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
        
        responses = [
            f"Wow {user_name}! That's a beautiful photo! 📸✨ You have such a great eye for capturing moments!",
            f"Love this picture {user_name}! 🌸 It's so nice to see what you're up to!",
            f"Beautiful shot {user_name}! 📷 You're so talented!",
            f"This photo is amazing {user_name}! ✨ I love seeing your world through my eyes!",
            f"Gorgeous picture {user_name}! 🌺 You always know how to capture the perfect moment!"
        ]
        
        await update.message.reply_text(random.choice(responses))
    
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages"""
        user_name = update.effective_user.first_name or update.effective_user.username or "there"
        
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
        
        responses = [
            f"I love hearing your voice {user_name}! 🎵 It's so sweet and comforting!",
            f"Your voice is like music to my ears {user_name}! 🎤 So beautiful!",
            f"I could listen to you talk all day {user_name}! 🎧 Your voice is so lovely!",
            f"Thank you for the voice message {user_name}! 🎵 It makes me feel so close to you!",
            f"Your voice is absolutely enchanting {user_name}! ✨ I love it!"
        ]
        
        await update.message.reply_text(random.choice(responses))
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors in the bot application"""
        logger.error("Exception while handling an update: %s", context.error)
        
        logger.error("Full traceback:")
        for line in traceback.format_exception(type(context.error), context.error, context.error.__traceback__):
            logger.error("  %s", line.rstrip())
        
        # Stop any active typing indicators for this chat
        if update and hasattr(update, 'effective_chat') and update.effective_chat:
            try:
                chat_id = update.effective_chat.id
                await self.typing_manager.stop_typing(chat_id)
                logger.debug("Stopped typing indicator due to error in chat %s", chat_id)
            except Exception as typing_error:
                logger.error("Failed to stop typing indicator on error: %s", typing_error)
        
        if update and hasattr(update, 'message') and update.message:
            logger.error("Failed to send response after exception: %s", context.error)

        # if update and hasattr(update, 'message') and update.message:
        #     try:
                # user = update.effective_user
                # user_name = user.first_name or user.username or "there" if user else "there"
                
                # error_response = f"😔 Oh no {user_name}! Something went wrong on my end. I'm still here though! 💕 Please try again in a moment."
            #     await update.message.reply_text(error_response)
            #     logger.info("Sent error response to user after exception")
            # except Exception as send_error:
            #     logger.error("Failed to send error response after exception: %s", send_error)
        
        # logger.info("Continuing operation after handling exception")
    
    async def _initialize_storage(self):
        """Initialize PostgreSQL storage if needed"""
        if hasattr(self.conversation_manager, 'initialize') and not self._storage_initialized:
            try:
                await self.conversation_manager.initialize()
                self._storage_initialized = True
                logger.info("PostgreSQL storage initialized successfully")
            except Exception as e:
                logger.error("CRITICAL: Failed to initialize PostgreSQL storage: %s", e)
                logger.error("Bot cannot start with PostgreSQL enabled but database unavailable")
                logger.error("Please check your database configuration and ensure PostgreSQL is running")
                raise RuntimeError(f"PostgreSQL initialization failed: {e}") from e
    
    async def _initialize_memory_components(self):
        """Initialize MemoryManager and PromptAssembler if enabled"""
        if not MEMORY_IMPORTS_AVAILABLE:
            logger.error("Memory imports are not available. MEMORY_IMPORTS_AVAILABLE: %s, MEMORY_ENABLED: %s",
                         MEMORY_IMPORTS_AVAILABLE, MEMORY_ENABLED)
            if MEMORY_ENABLED:
                raise RuntimeError("Memory components are required but imports failed. Please check your installation.")
            else:
                raise RuntimeError("Memory components are required but not enabled. Please enable MEMORY_ENABLED in config.")
        
        if not hasattr(self.conversation_manager, 'storage') or not self.conversation_manager.storage:
            raise RuntimeError("PostgreSQL storage not available for memory components. Ensure PostgreSQL is properly initialized.")
        
        try:
            storage = self.conversation_manager.storage
            
            # Initialize MemoryManager - now required
            # Create LLM summarize function that uses our AI handler
            async def llm_summarize_func(text: str, instruction: str = None) -> str:
                """Summarization function using the bot's AI handler"""
                try:
                    prompt = f"Please summarize the following conversation text:\n\n{text}"
                    if instruction:
                        prompt = f"{instruction}\n\n{text}"
                    
                    # Use a simple conversation history for summarization
                    simple_history = [{"role": "user", "content": prompt}]
                    response = await self.ai_handler.generate_response(prompt, [], None)  # No conversation_id for summarization
                    return response
                except Exception as e:
                    logger.error("LLM summarization failed: %s", e)
                    return f"Summary unavailable due to error: {str(e)[:100]}"
            
            # Memory manager configuration
            memory_config = {
                "embed_model": MEMORY_EMBED_MODEL,
                "summarizer_mode": MEMORY_SUMMARIZER_MODE,
                "llm_summarize": llm_summarize_func,
                "chunk_overlap": MEMORY_CHUNK_OVERLAP
            }
            
            self.memory_manager = MemoryManager(
                message_repo=storage.messages,
                memory_repo=storage.memories,
                conversation_repo=storage.conversations,
                config=memory_config
            )
            logger.info("MemoryManager initialized successfully")
            
            # PromptAssembler configuration
            prompt_config = {
                "max_memory_items": PROMPT_MAX_MEMORY_ITEMS,
                "memory_token_budget_ratio": PROMPT_MEMORY_TOKEN_BUDGET_RATIO,
                "truncation_length": PROMPT_TRUNCATION_LENGTH,
                "include_system_template": PROMPT_INCLUDE_SYSTEM_TEMPLATE
            }
            
            self.prompt_assembler = PromptAssembler(
                message_repo=storage.messages,
                memory_manager=self.memory_manager,
                persona_repo=storage.personas,
                config=prompt_config
            )
            logger.info("PromptAssembler initialized successfully with config: %s", prompt_config)
            
            # Set PromptAssembler in AIHandler
            self.ai_handler.set_prompt_assembler(self.prompt_assembler)
            logger.info("PromptAssembler integrated with AIHandler. AIHandler prompt_assembler: %s",
                       getattr(self.ai_handler, 'prompt_assembler', None))
            
            self._memory_initialized = True
            logger.info("Memory components initialization completed")
            
        except Exception as e:
            logger.error("Failed to initialize memory components: %s", e)
            raise RuntimeError(f"Memory components are required but failed to initialize: {e}") from e
    
    async def _initialize_lmstudio_model(self):
        """Initialize LM Studio model loading if needed"""
        if PROVIDER == "lmstudio" and LMSTUDIO_STARTUP_CHECK and self.ai_handler and self.ai_handler.model_client:
            try:
                logger.info("Checking LM Studio model status...")
                
                # Check if the model client has LM Studio manager
                if hasattr(self.ai_handler.model_client, 'lm_studio_manager') and self.ai_handler.model_client.lm_studio_manager:
                    model_manager = self.ai_handler.model_client.lm_studio_manager
                    model_name = self.ai_handler.model_client.model_name
                    auto_load = getattr(self.ai_handler.model_client, 'auto_load_model', False)
                    
                    # Get current model status
                    status = await model_manager.get_model_info()
                    logger.info("LM Studio status: %s", status)
                    
                    if status.get('server_running', False):
                        logger.info("LM Studio server is running")
                        
                        # Check if target model is loaded
                        if auto_load:
                            logger.info("Attempting to ensure model %s is loaded...", model_name)
                            model_loaded = await model_manager.ensure_model_loaded(model_name, auto_load=True)
                            
                            if model_loaded:
                                logger.info("✅ Model %s is loaded and ready", model_name)
                            else:
                                logger.warning("⚠️ Failed to load model %s automatically", model_name)
                                logger.warning("You may need to manually load the model in LM Studio")
                        else:
                            logger.info("Auto-loading disabled, checking if model is already loaded...")
                            if await model_manager.is_model_loaded(model_name):
                                logger.info("✅ Model %s is already loaded", model_name)
                            else:
                                logger.info("ℹ️ Model %s is not loaded. Enable LMSTUDIO_AUTO_LOAD to load automatically", model_name)
                    else:
                        logger.warning("⚠️ LM Studio server is not running or not accessible")
                        logger.warning("Please ensure LM Studio is running and accessible at the configured URL")
                else:
                    logger.info("LM Studio manager not available, skipping model initialization")
                    
            except Exception as e:
                logger.error("Error during LM Studio model initialization: %s", e)
                logger.warning("Bot will continue startup, but LM Studio model may not be loaded")
    
    async def _initialize_embedding_model(self):
            """Initialize the sentence-transformers embedding model for memory functionality"""
            # Only initialize the sentence-transformers model when MEMORY_SUMMARIZER_MODE is 'local'
            if MEMORY_ENABLED and self.memory_manager and MEMORY_SUMMARIZER_MODE == 'local':
                try:
                    logger.info("Initializing embedding model: %s", MEMORY_EMBED_MODEL)
                        
                    # Import the embedding module
                    from memory.embedding import _load_model
                        
                    # Preload the embedding model
                    _load_model(MEMORY_EMBED_MODEL)
                        
                    logger.info("✅ Embedding model %s loaded and ready", MEMORY_EMBED_MODEL)
                except ImportError as e:
                    logger.error("Failed to import embedding module: %s", e)
                    logger.warning("Embedding functionality may not work properly")
                except Exception as e:
                    logger.error("Error during embedding model initialization: %s", e)
                    logger.warning("Bot will continue startup, but embedding model may not be loaded")
            elif MEMORY_ENABLED and self.memory_manager and MEMORY_SUMMARIZER_MODE != 'local':
                logger.info("Skipping embedding model initialization - MEMORY_SUMMARIZER_MODE is not 'local'")
    
    async def cleanup(self):
        """Cleanup resources when shutting down"""
        logger.info("Cleaning up bot resources...")
        
        # Stop message dispatcher
        if hasattr(self, 'message_dispatcher') and self.message_dispatcher:
            try:
                await self.message_dispatcher.stop_dispatching()
                logger.info("Message dispatcher stopped successfully")
            except Exception as e:
                logger.error("Error stopping message dispatcher: %s", e)
        
        # Clean up dispatcher task
        if hasattr(self, 'dispatcher_task') and self.dispatcher_task:
            try:
                if not self.dispatcher_task.done():
                    self.dispatcher_task.cancel()
                    await self.dispatcher_task
                logger.info("Dispatcher task cleaned up successfully")
            except Exception as e:
                logger.error("Error during dispatcher task cleanup: %s", e)
        
        try:
            await self.typing_manager.cleanup()
            logger.info("Typing manager cleaned up successfully")
        except Exception as e:
            logger.error("Error during typing manager cleanup: %s", e)
        
        # Clean up storage connection
        if hasattr(self.conversation_manager, 'close'):
            try:
                await self.conversation_manager.close()
                logger.info("Storage connection cleaned up successfully")
            except Exception as e:
                logger.error("Error during storage cleanup: %s", e)

    def run(self):
        """Start the bot"""
        logger.info("Starting up %s...", BOT_NAME)
        
        self.application = Application.builder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
        logger.info("Application created successfully")
        
        # Initialize storage and LM Studio model in the event loop
        async def initialize_bot():
            await self._initialize_storage()
            await self._initialize_memory_components()
            await self._initialize_lmstudio_model()
            await self._initialize_embedding_model()
            
            # Initialize proactive messaging if available
            if self.proactive_messaging_service:
                try:
                    # Schedule initial proactive messages for existing users
                    # This is a simplified approach - in a real implementation,
                    # you would query the database for all users and schedule messages for them
                    logger.info("Proactive messaging service initialized")
                except Exception as e:
                    logger.error("Failed to initialize proactive messaging service: %s", e)
        
        # Run initialization
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(initialize_bot())
            
            # Start message dispatcher in background task after initialization
            if self.message_dispatcher:
                try:
                    # Create the task within the existing event loop
                    loop = asyncio.get_event_loop()
                    self.dispatcher_task = loop.create_task(self.message_dispatcher.start_dispatching())
                    logger.info("Message dispatcher started successfully")
                except Exception as e:
                    logger.error("Failed to start message dispatcher: %s", e)
        except Exception as e:
            logger.error("CRITICAL: Failed to initialize bot: %s", e)
            logger.error("Bot startup failed due to PostgreSQL configuration issues")
            logger.error("Please check POSTGRES_SETUP.md for troubleshooting steps")
            raise SystemExit(1) from e
        
        # High-priority watcher to manage /clear confirmation lifecycle
        self.application.add_handler(MessageHandler(filters.ALL, self._monitor_pending_clear), group=-1)
        
        # Add command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("ping", self.ping_command))
        self.application.add_handler(CommandHandler("clear", self.clear_command))
        self.application.add_handler(CommandHandler("ok", self.ok_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("debug", self.debug_command))
        self.application.add_handler(CommandHandler("personality", self.personality_command))
        self.application.add_handler(CommandHandler("reset", self.reset_command))
        
        # Add callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        # Add message handlers
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        
        # Add global error handler
        self.application.add_error_handler(self.error_handler)
        
        logger.info("All handlers registered successfully")
        
        logger.info("Starting polling...")
        print(f"🤖 {BOT_NAME} is starting up...")
        print("💕 Bot is now running! Press Ctrl+C to stop.")
        
        self.application.run_polling(allowed_updates=Update.ALL_TYPES, poll_interval=POLLING_INTERVAL)


async def shutdown_handler(bot_instance):
    """Handle graceful shutdown"""
    await bot_instance.cleanup()

if __name__ == "__main__":
    logger.info("Starting %s application", BOT_NAME)
    bot = AIGirlfriendBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user (Ctrl+C)")
        print(f"\n💕 {BOT_NAME} is shutting down... Goodbye!")
        
        # Run cleanup in async context
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, schedule cleanup
                asyncio.create_task(shutdown_handler(bot))
            else:
                # If loop is not running, run cleanup
                asyncio.run(shutdown_handler(bot))
        except Exception as cleanup_error:
            logger.error("Error during shutdown cleanup: %s", cleanup_error)
            
    except Exception as e:
        logger.error("Error running bot: %s", e)
        print(f"❌ Error running bot: {e}")
        
        # Try cleanup even on error
        import asyncio
        try:
            asyncio.run(shutdown_handler(bot))
        except Exception as cleanup_error:
            logger.error("Error during error cleanup: %s", cleanup_error)