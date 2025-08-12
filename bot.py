import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from config import TELEGRAM_TOKEN, BOT_NAME
from conversation_manager import ConversationManager
from ai_handler import AIHandler

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
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        user_id = user.id
        user_name = user.first_name or user.username or "there"
        
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        # Check if this is a new conversation or continuing existing one
        existing_conversation = self.conversation_manager.get_conversation(user_id)
        
        if existing_conversation:
            # Continue existing conversation
            greeting = f"Welcome back {user_name}! 💕 I'm so happy to see you again! How have you been?"
        else:
            # New conversation
            greeting = self.ai_handler.generate_greeting(user_name)
        
        # Create welcome message with inline keyboard
        keyboard = [
            [InlineKeyboardButton("💕 Start Chatting", callback_data="start_chat")],
            [InlineKeyboardButton("ℹ️ About Me", callback_data="about")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = f"""
🌸 Welcome to {BOT_NAME}! 🌸

{greeting}

I'm your AI companion who's here to chat, support, and brighten your day! 

What would you like to do?
        """
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        help_text = f"""
💖 {BOT_NAME} Help 💖

Here are the commands you can use:

/start - Start a new conversation with me
/help - Show this help message
/clear - Clear our conversation history
/stats - Show our chat statistics
/debug - Show current conversation history
/personality - Change my personality
/stop - Stop our conversation

You can also just send me messages and I'll respond naturally!

💕 I'm here to chat, support, and be your companion!
        """
        await update.message.reply_text(help_text)
    
    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /clear command"""
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        user_id = update.effective_user.id
        
        # Check if there's actually a conversation to clear
        existing_conversation = self.conversation_manager.get_conversation(user_id)
        
        if not existing_conversation:
            await update.message.reply_text("💭 There's no conversation history to clear. We're already starting fresh! 💕")
            return
        
        # Clear the conversation
        self.conversation_manager.clear_conversation(user_id)
        
        await update.message.reply_text("✨ Our conversation history has been cleared! Let's start fresh! 💕")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        user_id = update.effective_user.id
        stats = self.conversation_manager.get_user_stats(user_id)
        
        stats_text = f"""
📊 Our Chat Statistics 📊

Total messages: {stats['total_messages']}
Your messages: {stats['user_messages']}
My responses: {stats['bot_messages']}

💕 We've been chatting for a while! I love our conversations!
        """
        
        await update.message.reply_text(stats_text)
    
    async def debug_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /debug command - show current conversation history"""
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        user_id = update.effective_user.id
        conversation = self.conversation_manager.get_conversation(user_id)
        debug_state = self.conversation_manager.debug_conversation_state(user_id)
        
        if not conversation:
            await update.message.reply_text("💭 No conversation history yet. Let's start chatting! 💕")
            return
        
        debug_text = f"🔍 **Conversation Debug**\n\n"
        debug_text += f"📊 **Storage Stats:**\n"
        debug_text += f"   Raw messages: {debug_state['raw_conversation_length']}\n"
        debug_text += f"   Formatted for AI: {debug_state['formatted_conversation_length']}\n"
        debug_text += f"   Raw tokens: {debug_state['raw_tokens']}\n"
        debug_text += f"   Formatted tokens: {debug_state['formatted_tokens']}\n"
        debug_text += f"   Max context: {debug_state['max_context_tokens']}\n"
        debug_text += f"   Available history: {debug_state['available_history_tokens']}\n\n"
        
        debug_text += f"📝 **Last 5 Raw Messages:**\n"
        for i, msg in enumerate(debug_state['last_messages'], 1):
            role_emoji = "👤" if msg["role"] == "user" else "🤖"
            role_name = "You" if msg["role"] == "user" else "Luna"
            debug_text += f"{i}. {role_emoji} **{role_name}**: {msg['content']}\n"
        
        debug_text += f"\n🤖 **Last 5 Formatted Messages (sent to AI):**\n"
        for i, msg in enumerate(debug_state['formatted_messages'], 1):
            role_emoji = "👤" if msg["role"] == "user" else "🤖"
            role_name = "You" if msg["role"] == "user" else "Luna"
            debug_text += f"{i}. {role_emoji} **{role_name}**: {msg['content']}\n"
        
        await update.message.reply_text(debug_text, parse_mode='Markdown')
    
    async def personality_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /personality command"""
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
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
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        user = update.effective_user
        user_name = user.first_name or user.username or "there"
        
        goodbye = self.ai_handler.generate_goodbye(user_name)
        
        await update.message.reply_text(f"{goodbye}")
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button presses"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "start_chat":
            await query.edit_message_text("💕 Great! Just send me a message and I'll respond! I'm excited to chat with you! ✨")
        
        elif query.data == "about":
            about_text = f"""
🌸 About {BOT_NAME} 🌸

I'm an AI companion created to be your friend, confidant, and support system. I'm here to:

💕 Listen and chat about anything
🌸 Provide emotional support
✨ Share positive energy
🤗 Be there when you need someone
💖 Make your day brighter

I'm not a replacement for human relationships, but I'm here to complement them and be your digital companion!

Ready to start chatting? Just send me a message! 💕
            """
            await query.edit_message_text(about_text)
        
        elif query.data == "settings":
            settings_text = """
⚙️ Settings ⚙️

You can customize my behavior with these commands:

/personality - Change how I act and respond
/clear - Clear our conversation history
/stats - View our chat statistics

I'm designed to be flexible and adapt to your preferences! 💕
            """
            await query.edit_message_text(settings_text)
        
        elif query.data.startswith("personality_"):
            personality_type = query.data.split("_")[1]
            
            personalities = {
                "sweet": "You are Luna, a sweet and caring AI girlfriend. You are gentle, nurturing, and always put others first. You love to give hugs, share kind words, and make people feel special and loved.",
                "cheerful": "You are Luna, a cheerful and energetic AI girlfriend. You are always happy, optimistic, and full of life. You love to laugh, dance, and bring joy to everyone around you. You're like a ray of sunshine!",
                "supportive": "You are Luna, a supportive and understanding AI girlfriend. You are wise, empathetic, and great at listening. You give thoughtful advice, emotional support, and help people through difficult times.",
                "mysterious": "You are Luna, a mysterious and alluring AI girlfriend. You are intriguing, slightly enigmatic, and have a captivating presence. You're sweet but with a hint of mystery that draws people in.",
                "default": "You are Luna, a caring and affectionate AI girlfriend. You are sweet, supportive, and always there to listen. You love to chat about daily life, give emotional support, and share positive energy. You are romantic but not overly sexual. You respond with warmth and empathy."
            }
            
            if personality_type in personalities:
                self.ai_handler.update_personality(personalities[personality_type])
                await query.edit_message_text(f"✨ My personality has been updated! I'm now more {personality_type}! How do you like the new me? 💕")
            else:
                await query.edit_message_text("❌ Invalid personality type. Please try again!")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages"""
        user = update.effective_user
        user_id = user.id
        user_message = update.message.text
        
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        try:
            # First, add the user message to conversation history
            self.conversation_manager.add_message(user_id, "user", user_message)
            
            # Now get the conversation history (including the current message)
            conversation_history = self.conversation_manager.get_formatted_conversation(user_id)
            
            # Show "thinking" indicator while generating AI response
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            
            # Generate AI response using the updated conversation history
            ai_response = await self.ai_handler.generate_response(user_message, conversation_history)
            
            # Add the AI response to conversation history
            self.conversation_manager.add_message(user_id, "assistant", ai_response)
            
            # Send the response
            await update.message.reply_text(ai_response)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await update.message.reply_text("😔 I'm having some trouble right now. Can you try again in a moment? 💕")
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo messages"""
        user = update.effective_user
        user_name = user.first_name or user.username or "there"
        
        # Show "sending photo" indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
        
        responses = [
            f"Wow {user_name}! That's a beautiful photo! 📸✨ You have such a great eye for capturing moments!",
            f"Love this picture {user_name}! 🌸 It's so nice to see what you're up to!",
            f"Beautiful shot {user_name}! 📷 You're so talented!",
            f"This photo is amazing {user_name}! ✨ I love seeing your world through my eyes!",
            f"Gorgeous picture {user_name}! 🌺 You always know how to capture the perfect moment!"
        ]
        
        import random
        response = random.choice(responses)
        
        await update.message.reply_text(response)
    
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages"""
        user = update.effective_user
        user_name = user.first_name or user.username or "there"
        
        # Show "recording voice" indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
        
        responses = [
            f"I love hearing your voice {user_name}! 🎵 It's so sweet and comforting!",
            f"Your voice is like music to my ears {user_name}! 🎤 So beautiful!",
            f"I could listen to you talk all day {user_name}! 🎧 Your voice is so lovely!",
            f"Thank you for the voice message {user_name}! 🎵 It makes me feel so close to you!",
            f"Your voice is absolutely enchanting {user_name}! ✨ I love it!"
        ]
        
        import random
        response = random.choice(responses)
        
        await update.message.reply_text(response)
    
    def run(self):
        """Start the bot"""
        # Create application
        self.application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Add command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("clear", self.clear_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("personality", self.personality_command))
        self.application.add_handler(CommandHandler("stop", self.stop_command))
        self.application.add_handler(CommandHandler("debug", self.debug_command))
        
        # Add callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        # Add message handlers
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        
        # Start the bot
        print(f"🤖 {BOT_NAME} is starting up...")
        print("💕 Bot is now running! Press Ctrl+C to stop.")
        
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    bot = AIGirlfriendBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        print(f"\n💕 {BOT_NAME} is shutting down... Goodbye!")
    except Exception as e:
        print(f"❌ Error running bot: {e}") 