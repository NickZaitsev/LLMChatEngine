import asyncio
import logging
import random
import time
import traceback

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from config import TELEGRAM_TOKEN, BOT_NAME
from conversation_manager import ConversationManager
from ai_handler import AIHandler

# Constants
RATE_LIMIT_DURATION = 60
REQUEST_TIMEOUT = 35.0
MESSAGE_PREVIEW_LENGTH = 50
SHORT_MESSAGE_THRESHOLD = 10

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class AIGirlfriendBot:
    def __init__(self):
        self.conversation_manager = ConversationManager()
        self.ai_handler = AIHandler()
        self.application = None
        self.rate_limit_cooldown = {}
        self.rate_limit_duration = RATE_LIMIT_DURATION
    
    def _is_user_rate_limited(self, user_id: int) -> bool:
        """Check if a user is currently rate limited"""
        if user_id in self.rate_limit_cooldown:
            cooldown_until = self.rate_limit_cooldown[user_id]
            if time.time() < cooldown_until:
                remaining = int(cooldown_until - time.time())
                logger.info("User %s rate limited for %d seconds", user_id, remaining)
                return True
            else:
                del self.rate_limit_cooldown[user_id]
        return False
    
    def _set_user_rate_limit(self, user_id: int, duration: int = None):
        """Set a rate limit cooldown for a user"""
        duration = duration or self.rate_limit_duration
        cooldown_until = time.time() + duration
        self.rate_limit_cooldown[user_id] = cooldown_until
        logger.info("Rate limit set for user %s, duration: %d seconds", user_id, duration)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        user_id = user.id
        user_name = user.first_name or user.username or "there"
        
        logger.info("Start command from user %s (%s)", user_id, user_name)
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        existing_conversation = self.conversation_manager.get_conversation(user_id)
        
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

I'm designed to be flexible and adapt to your preferences!

For now, just send me messages and I'll chat with you! I'm always learning and improving to be the best companion I can be! 💕"""
            await query.edit_message_text(settings_text)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages with proper timeout and fallback handling"""
        user = update.effective_user
        user_id = user.id
        user_message = update.message.text
        user_name = user.first_name or user.username or "there"
        
        message_preview = (user_message[:MESSAGE_PREVIEW_LENGTH] + "..." 
                          if len(user_message) > MESSAGE_PREVIEW_LENGTH else user_message)
        logger.info("Message from user %s: '%s' (%d chars)", user_id, message_preview, len(user_message))
        
        if self._is_user_rate_limited(user_id):
            remaining = int(self.rate_limit_cooldown[user_id] - time.time())
            await update.message.reply_text(
                f"😔 I'm a bit overwhelmed right now! Please wait {remaining} seconds before sending another message. 💕"
            )
            return
        
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        self.conversation_manager.add_message(user_id, "user", user_message)
        conversation_history = self.conversation_manager.get_formatted_conversation(user_id)
        
        ai_response = await self._get_ai_response(user_id, user_message, conversation_history)
        
        if not ai_response:
            ai_response = self._get_fallback_response(user_message, user_name)
        
        try:
            self.conversation_manager.add_message(user_id, "assistant", ai_response)
        except Exception as e:
            logger.error("Failed to add response to history for user %s: %s", user_id, e)
        
        try:
            await update.message.reply_text(ai_response)
            logger.info("Response sent to user %s", user_id)
        except Exception as e:
            logger.error("Failed to send response to user %s: %s", user_id, e)
            try:
                await update.message.reply_text("😔 I'm having trouble sending my response. Please try again! 💕")
            except Exception:
                logger.error("Failed to send error message to user %s", user_id)
    
    async def _get_ai_response(self, user_id: int, user_message: str, conversation_history: list) -> str:
        """Get AI response with proper error handling"""
        try:
            logger.info("Generating AI response for user %s", user_id)
            ai_response = await asyncio.wait_for(
                self.ai_handler.generate_response(user_message, conversation_history),
                timeout=REQUEST_TIMEOUT
            )
            logger.info("AI response received for user %s (%d chars)", user_id, len(ai_response))
            return ai_response
            
        except asyncio.TimeoutError:
            logger.warning("AI request timeout for user %s", user_id)
            return None
            
        except Exception as e:
            logger.error("AI request failed for user %s: %s", user_id, e)
            error_message = str(e).lower()
            
            if any(pattern in error_message for pattern in ["rate limit", "429", "ratelimitreached", "too many requests"]):
                logger.warning("Rate limit error for user %s, setting cooldown", user_id)
                self._set_user_rate_limit(user_id, 60)
            
            return None
    
    def _get_fallback_response(self, user_message: str, user_name: str = None) -> str:
        """Generate a fallback response when AI service is unavailable"""
        user_message_lower = user_message.lower()
        name = user_name or 'there'
        
        if any(word in user_message_lower for word in ["привет", "hello", "hi", "hey", "ку"]):
            return f"Привет {name}! 💕 I'm here but my AI brain is taking a break right now. How are you doing?"
        elif any(word in user_message_lower for word in ["как дела", "how are you", "how are u"]):
            return f"I'm doing okay {name}! 💕 Just having some technical difficulties with my AI service. How about you?"
        elif any(word in user_message_lower for word in ["спасибо", "thank", "thanks"]):
            return f"You're welcome {name}! 💕 I'm glad I could help, even in this limited way!"
        elif any(word in user_message_lower for word in ["пока", "bye", "goodbye", "see you"]):
            return f"Goodbye {name}! 💕 I'll be back to full AI power soon! Take care!"
        elif "?" in user_message:
            return f"That's an interesting question {name}! 💕 I'd love to give you a proper AI-powered answer, but my service is down right now. Can you ask again later?"
        elif len(user_message) < SHORT_MESSAGE_THRESHOLD:
            return f"Hey {name}! 💕 I'm here but my AI service is temporarily unavailable. I can still chat with you in a basic way though!"
        else:
            return f"I hear you {name}! 💕 I'm having trouble with my AI service right now, but I'm still here listening. Can you try again in a few minutes?"
    
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
        
        if update and hasattr(update, 'message') and update.message:
            try:
                user = update.effective_user
                user_name = user.first_name or user.username or "there" if user else "there"
                
                error_response = f"😔 Oh no {user_name}! Something went wrong on my end. I'm still here though! 💕 Please try again in a moment."
                await update.message.reply_text(error_response)
                logger.info("Sent error response to user after exception")
            except Exception as send_error:
                logger.error("Failed to send error response after exception: %s", send_error)
        
        logger.info("Continuing operation after handling exception")
    
    def run(self):
        """Start the bot"""
        logger.info("Starting up %s...", BOT_NAME)
        
        self.application = Application.builder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
        logger.info("Application created successfully")
        
        # Add command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        
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
        print(f"{BOT_NAME} is starting up...")
        print("Bot is now running! Press Ctrl+C to stop.")
        
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    logger.info("Starting %s application", BOT_NAME)
    bot = AIGirlfriendBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user (Ctrl+C)")
        print(f"\n{BOT_NAME} is shutting down... Goodbye!")
    except Exception as e:
        logger.error("Error running bot: %s", e)
        print(f"Error running bot: {e}")