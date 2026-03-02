"""
Admin Bot for managing multi-bot configuration.

This bot allows administrators to:
- Add, edit, and remove user bots
- Change bot personalities on the fly
- Toggle feature flags
- Monitor bot status
"""

import asyncio
import logging
import uuid
from typing import Optional, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes

from token_encryption import encrypt_token, decrypt_token
from features import BotFeature, DEFAULT_FEATURE_FLAGS, has_feature

logger = logging.getLogger(__name__)


# Conversation states for multi-step commands
(
    WAITING_TOKEN,
    WAITING_NAME,
    WAITING_PERSONALITY,
    WAITING_EDIT_FIELD,
    WAITING_EDIT_VALUE,
    WAITING_NEW_PERSONALITY,
) = range(6)


class AdminBot:
    """
    Admin bot for configuring and managing user bots.
    
    This bot is separate from user-facing bots and provides
    administrative commands for managing the multi-bot system.
    """
    
    def __init__(self, admin_token: str, admin_user_ids: list, db_url: str):
        """
        Initialize the admin bot.
        
        Args:
            admin_token: Telegram bot token for admin bot
            admin_user_ids: List of Telegram user IDs allowed to use admin commands
            db_url: Database URL for PostgreSQL
        """
        self.admin_token = admin_token
        self.admin_user_ids = set(admin_user_ids)
        self.db_url = db_url
        self.application: Optional[Application] = None
        self.storage = None
        self._pending_bot_data: Dict[int, Dict[str, Any]] = {}  # user_id -> pending data
        
        # Reference to bot manager for hot-reload
        self.bot_manager = None
    
    def set_bot_manager(self, bot_manager):
        """Set reference to bot manager for hot-reload functionality."""
        self.bot_manager = bot_manager

    def _session_key(self, update: Update) -> tuple[int, int]:
        """Scope pending admin workflows to user and chat."""
        return (update.effective_user.id, update.effective_chat.id)
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if user is an admin."""
        return user_id in self.admin_user_ids
    
    async def _init_storage(self):
        """Initialize database storage."""
        if self.storage is None:
            from storage import create_storage
            self.storage = await create_storage(self.db_url)
            logger.info("Admin bot storage initialized")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user_id = update.effective_user.id
        
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return
        
        welcome_text = """🤖 **Admin Bot Control Panel**

Welcome to the multi-bot administration system.

**Available Commands:**
/addbot - Add a new bot
/listbots - List all configured bots
/editbot - Edit bot settings
/setprompt - Change bot personality
/togglefeature - Enable/disable features
/removebot - Deactivate a bot
/botstatus - Show running status
/reloadbot - Hot-reload bot config
/help - Show this help message

Use these commands to manage your bot fleet."""
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        await self.start_command(update, context)
    
    async def addbot_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the add bot flow."""
        user_id = update.effective_user.id
        
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return ConversationHandler.END
        
        await self._init_storage()
        
        self._pending_bot_data[self._session_key(update)] = {}
        
        await update.message.reply_text(
            "🤖 **Add New Bot**\n\n"
            "Please send me the bot token from @BotFather.\n\n"
            "Send /cancel to abort.",
            parse_mode='Markdown'
        )
        return WAITING_TOKEN
    
    async def addbot_token(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive bot token."""
        user_id = update.effective_user.id
        token = update.message.text.strip()
        
        # Validate token format (basic check)
        if ':' not in token or len(token) < 30:
            await update.message.reply_text(
                "❌ Invalid token format. Please send a valid bot token from @BotFather."
            )
            return WAITING_TOKEN
        
        # Store encrypted token
        self._pending_bot_data[self._session_key(update)]['token'] = token
        
        # Delete the message containing the token for security
        try:
            await update.message.delete()
        except Exception:
            pass
        
        await update.message.reply_text(
            "✅ Token received (message deleted for security).\n\n"
            "Now send me the **display name** for this bot (e.g., 'Luna', 'Max'):",
            parse_mode='Markdown'
        )
        return WAITING_NAME
    
    async def addbot_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive bot name."""
        user_id = update.effective_user.id
        name = update.message.text.strip()
        
        if len(name) < 1 or len(name) > 100:
            await update.message.reply_text("❌ Name must be 1-100 characters.")
            return WAITING_NAME
        
        self._pending_bot_data[self._session_key(update)]['name'] = name
        
        await update.message.reply_text(
            f"✅ Name set to **{name}**.\n\n"
            "Now send me the **personality prompt** for this bot.\n"
            "This is the system message that defines how the bot behaves.\n\n"
            "Example:\n"
            "_You are Luna, a caring and affectionate AI girlfriend..._",
            parse_mode='Markdown'
        )
        return WAITING_PERSONALITY
    
    async def addbot_personality(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive bot personality and create the bot."""
        user_id = update.effective_user.id
        personality = update.message.text.strip()
        
        if len(personality) < 10:
            await update.message.reply_text("❌ Personality must be at least 10 characters.")
            return WAITING_PERSONALITY
        
        pending = self._pending_bot_data.get(self._session_key(update), {})
        token = pending.get('token')
        name = pending.get('name')
        
        if not token or not name:
            await update.message.reply_text("❌ Session expired. Please start again with /addbot")
            return ConversationHandler.END
        
        try:
            # Encrypt token and create bot in database
            encrypted_token = encrypt_token(token)
            
            # Create bot using repository
            from storage.models import Bot
            from sqlalchemy import select
            from sqlalchemy.ext.asyncio import AsyncSession
            
            async with self.storage.session_maker() as session:
                new_bot = Bot(
                    token_encrypted=encrypted_token,
                    name=name,
                    personality=personality,
                    is_active=True,
                    feature_flags=DEFAULT_FEATURE_FLAGS.copy(),
                    llm_config={}  # Will use global config
                )
                session.add(new_bot)
                await session.commit()
                await session.refresh(new_bot)
                bot_id = new_bot.id
            
            # Clean up pending data
            del self._pending_bot_data[self._session_key(update)]
            
            # Build feature list for display
            features_text = "\n".join([
                f"  • `{f.value}`: ✅" for f in BotFeature
            ])
            
            await update.message.reply_text(
                f"✅ **Bot Created Successfully!**\n\n"
                f"**ID:** `{bot_id}`\n"
                f"**Name:** {name}\n"
                f"**Status:** Active\n\n"
                f"**Enabled Features:**\n{features_text}\n\n"
                f"Use /reloadbot {bot_id} if you need to restart it later.",
                parse_mode='Markdown'
            )
            
            # Try to hot-reload if bot manager is available
            if self.bot_manager:
                try:
                    await self.bot_manager.start_bot(bot_id)
                    await update.message.reply_text("🚀 Bot started successfully!")
                except Exception as e:
                    logger.error(f"Failed to hot-start bot: {e}")
                    await update.message.reply_text(f"⚠️ Bot created but couldn't start: {e}")
            
        except Exception as e:
            logger.error(f"Failed to create bot: {e}")
            await update.message.reply_text(f"❌ Failed to create bot: {e}")
        
        return ConversationHandler.END
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel current operation."""
        user_id = update.effective_user.id
        session_key = self._session_key(update)
        if session_key in self._pending_bot_data:
            del self._pending_bot_data[session_key]
        
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END
    
    async def listbots_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all configured bots."""
        user_id = update.effective_user.id
        
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return
        
        await self._init_storage()
        
        try:
            from storage.models import Bot
            from sqlalchemy import select
            
            async with self.storage.session_maker() as session:
                result = await session.execute(select(Bot).order_by(Bot.created_at.desc()))
                bots = result.scalars().all()
            
            if not bots:
                await update.message.reply_text("📭 No bots configured yet. Use /addbot to add one.")
                return
            
            text = "🤖 **Configured Bots:**\n\n"
            for bot in bots:
                status = "🟢 Active" if bot.is_active else "🔴 Inactive"
                enabled_features = sum(1 for f in BotFeature if has_feature(bot.feature_flags or {}, f))
                text += (
                    f"**`{bot.name}`** ({status})\n"
                    f"  ID: `{bot.id}`\n"
                    f"  Features: {enabled_features}/{len(BotFeature)}\n"
                    f"  Created: {bot.created_at.strftime('%Y-%m-%d')}\n\n"
                )
            
            await update.message.reply_text(text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Failed to list bots: {e}")
            await update.message.reply_text(f"❌ Error listing bots: {e}")
    
    async def setprompt_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the setprompt flow."""
        user_id = update.effective_user.id
        
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return ConversationHandler.END
        
        await self._init_storage()
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "Usage: /setprompt <bot_id>\n"
                "Example: /setprompt 12345678-1234-1234-1234-123456789abc"
            )
            return ConversationHandler.END
        
        bot_id = args[0]
        
        try:
            from storage.models import Bot
            from sqlalchemy import select
            
            async with self.storage.session_maker() as session:
                result = await session.execute(select(Bot).where(Bot.id == uuid.UUID(bot_id)))
                bot = result.scalar_one_or_none()
            
            if not bot:
                await update.message.reply_text(f"❌ Bot not found: {bot_id}")
                return ConversationHandler.END
            
            # Store bot_id for next message
            self._pending_bot_data[self._session_key(update)] = {'edit_bot_id': bot_id, 'bot_name': bot.name}
            
            await update.message.reply_text(
                f"📝 **Editing: {bot.name}**\n\n"
                f"Current personality:\n_{bot.personality[:200]}{'...' if len(bot.personality) > 200 else ''}_\n\n"
                "Send the new personality prompt (or /cancel):",
                parse_mode='Markdown'
            )
            return WAITING_NEW_PERSONALITY
            
        except Exception as e:
            logger.error(f"Failed to get bot: {e}")
            await update.message.reply_text(f"❌ Error: {e}")
            return ConversationHandler.END
    
    async def receive_new_personality(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive and save the new personality prompt."""
        user_id = update.effective_user.id
        new_personality = update.message.text.strip()
        
        if len(new_personality) < 10:
            await update.message.reply_text("❌ Personality must be at least 10 characters. Please try again or /cancel.")
            return WAITING_NEW_PERSONALITY
        
        pending = self._pending_bot_data.get(self._session_key(update), {})
        bot_id = pending.get('edit_bot_id')
        bot_name = pending.get('bot_name', 'Unknown')
        
        if not bot_id:
            await update.message.reply_text("❌ Session expired. Please start again with /setprompt <bot_id>")
            return ConversationHandler.END
        
        try:
            from storage.models import Bot
            from sqlalchemy import select
            
            async with self.storage.session_maker() as session:
                result = await session.execute(select(Bot).where(Bot.id == uuid.UUID(bot_id)))
                bot = result.scalar_one_or_none()
                
                if not bot:
                    await update.message.reply_text(f"❌ Bot not found: {bot_id}")
                    return ConversationHandler.END
                
                # Update personality in database
                bot.personality = new_personality
                await session.commit()
            
            # Clean up pending data
            del self._pending_bot_data[self._session_key(update)]
            
            await update.message.reply_text(
                f"✅ **Personality updated for {bot_name}!**\n\n"
                f"New personality:\n_{new_personality[:200]}{'...' if len(new_personality) > 200 else ''}_\n\n"
                f"Use /reloadbot {bot_id} to apply changes to the running bot.",
                parse_mode='Markdown'
            )
            
            # Try to hot-reload if bot manager is available
            if self.bot_manager:
                try:
                    await self.bot_manager.reload_bot_config(uuid.UUID(bot_id))
                    await update.message.reply_text("🔄 Bot config reloaded automatically!")
                except Exception as e:
                    logger.error(f"Failed to hot-reload bot: {e}")
                    await update.message.reply_text(f"⚠️ Personality saved but hot-reload failed: {e}")
            
        except Exception as e:
            logger.error(f"Failed to update personality: {e}")
            await update.message.reply_text(f"❌ Error updating personality: {e}")
        
        return ConversationHandler.END
    
    async def togglefeature_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Toggle a feature for a bot."""
        user_id = update.effective_user.id
        
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return
        
        await self._init_storage()
        
        args = context.args
        if len(args) < 2:
            features_list = "\n".join([f"  • {f.value}" for f in BotFeature])
            await update.message.reply_text(
                f"Usage: /togglefeature <bot_id> <feature>\n\n"
                f"Available features:\n{features_list}"
            )
            return
        
        bot_id = args[0]
        feature_name = args[1].lower()
        
        # Validate feature
        valid_features = [f.value for f in BotFeature]
        if feature_name not in valid_features:
            await update.message.reply_text(f"❌ Invalid feature: {feature_name}")
            return
        
        try:
            from storage.models import Bot
            from sqlalchemy import select
            
            async with self.storage.session_maker() as session:
                result = await session.execute(select(Bot).where(Bot.id == uuid.UUID(bot_id)))
                bot = result.scalar_one_or_none()
                
                if not bot:
                    await update.message.reply_text(f"❌ Bot not found: {bot_id}")
                    return
                
                # Toggle the feature
                feature = BotFeature(feature_name)
                current_value = has_feature(bot.feature_flags or {}, feature)
                new_value = not current_value
                
                # Update feature flags
                new_flags = bot.feature_flags.copy()
                new_flags[feature_name] = new_value
                bot.feature_flags = new_flags
                
                await session.commit()
                
                status = "✅ Enabled" if new_value else "❌ Disabled"
                await update.message.reply_text(
                    f"🔧 **`{bot.name}`**\n\n"
                    f"Feature `{feature_name}`: {status}\n\n"
                    f"Use /reloadbot {bot_id} to apply changes.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Failed to toggle feature: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def editbot_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show editable settings for a bot and direct the admin to supported edit commands."""
        user_id = update.effective_user.id

        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return

        await self._init_storage()

        args = context.args
        if not args:
            await update.message.reply_text("Usage: /editbot <bot_id>")
            return

        bot_id = args[0]

        try:
            from storage.models import Bot
            from sqlalchemy import select

            async with self.storage.session_maker() as session:
                result = await session.execute(select(Bot).where(Bot.id == uuid.UUID(bot_id)))
                bot = result.scalar_one_or_none()

            if not bot:
                await update.message.reply_text(f"❌ Bot not found: {bot_id}")
                return

            enabled_features = [f.value for f in BotFeature if has_feature(bot.feature_flags or {}, f)]
            features_text = ", ".join(enabled_features) if enabled_features else "None"

            await update.message.reply_text(
                f"🛠 **Edit Bot: {bot.name}**\n\n"
                f"**ID:** `{bot.id}`\n"
                f"**Active:** {'Yes' if bot.is_active else 'No'}\n"
                f"**Enabled Features:** {features_text}\n\n"
                f"**Edit Commands:**\n"
                f"`/setprompt {bot.id}` to change personality\n"
                f"`/togglefeature {bot.id} <feature>` to toggle a feature\n"
                f"`/reloadbot {bot.id}` to apply or restart\n"
                f"`/removebot {bot.id}` to deactivate",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to edit bot: {e}")
            await update.message.reply_text(f"❌ Error: {e}")
    
    async def botstatus_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show status of all bots."""
        user_id = update.effective_user.id
        
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return
        
        await self._init_storage()
        
        try:
            from storage.models import Bot, Conversation
            from sqlalchemy import select, func
            
            async with self.storage.session_maker() as session:
                result = await session.execute(select(Bot))
                bots = result.scalars().all()
                
                if not bots:
                    await update.message.reply_text("📭 No bots configured.")
                    return
                
                text = "📊 **Bot Status Report**\n\n"
                
                for bot in bots:
                    db_status = "🟢" if bot.is_active else "🔴"
                    
                    # Check if running in bot manager
                    running_status = "⚪ Unknown"
                    if self.bot_manager:
                        if bot.id in self.bot_manager.bots:
                            running_status = "🟢 Running"
                        else:
                            running_status = "🔴 Stopped"
                    
                    # Count unique users for this bot
                    user_count_result = await session.execute(
                        select(func.count(func.distinct(Conversation.user_id)))
                        .where(Conversation.bot_id == bot.id)
                    )
                    user_count = user_count_result.scalar() or 0
                    
                    text += (
                        f"**{bot.name}**\n"
                        f"  DB Status: {db_status} {'Active' if bot.is_active else 'Inactive'}\n"
                        f"  Runtime: {running_status}\n"
                        f"  👥 Users: {user_count}\n\n"
                    )
            
            await update.message.reply_text(text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            await update.message.reply_text(f"❌ Error: {e}")
    
    async def reloadbot_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Hot-reload a bot's configuration."""
        user_id = update.effective_user.id
        
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return
        
        args = context.args
        if not args:
            await update.message.reply_text("Usage: /reloadbot <bot_id>")
            return
        
        bot_id = args[0]
        
        if not self.bot_manager:
            await update.message.reply_text("⚠️ Bot manager not available. Restart required.")
            return
        
        try:
            bot_uuid = uuid.UUID(bot_id)
            await self.bot_manager.reload_bot_config(bot_uuid)
            await update.message.reply_text(f"✅ Bot `{bot_id}` reloaded successfully!", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to reload bot: {e}")
            await update.message.reply_text(f"❌ Failed to reload: {e}")
    
    async def removebot_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Deactivate a bot."""
        user_id = update.effective_user.id
        
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return
        
        await self._init_storage()
        
        args = context.args
        if not args:
            await update.message.reply_text("Usage: /removebot <bot_id>")
            return
        
        bot_id = args[0]
        
        try:
            from storage.models import Bot
            from sqlalchemy import select
            
            async with self.storage.session_maker() as session:
                result = await session.execute(select(Bot).where(Bot.id == uuid.UUID(bot_id)))
                bot = result.scalar_one_or_none()
                
                if not bot:
                    await update.message.reply_text(f"❌ Bot not found: {bot_id}")
                    return
                
                bot.is_active = False
                await session.commit()
                
                await update.message.reply_text(
                    f"✅ Bot **`{bot.name}`** has been deactivated.\n\n"
                    "The bot will stop on next restart, or use /reloadbot to stop it now.",
                    parse_mode='Markdown'
                )
                
                # Try to stop if manager available
                if self.bot_manager and bot.id in self.bot_manager.bots:
                    await self.bot_manager.stop_bot(bot.id)
                    await update.message.reply_text("Bot stopped successfully.")
                    
        except Exception as e:
            logger.error(f"Failed to remove bot: {e}")
            await update.message.reply_text(f"❌ Error: {e}")
    
    def build_application(self) -> Application:
        """Build the Telegram application with handlers."""
        self.application = Application.builder().token(self.admin_token).build()
        
        # Add conversation handler for addbot
        addbot_handler = ConversationHandler(
            entry_points=[CommandHandler('addbot', self.addbot_start)],
            states={
                WAITING_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.addbot_token)],
                WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.addbot_name)],
                WAITING_PERSONALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.addbot_personality)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
        )
        
        self.application.add_handler(addbot_handler)
        
        # Add conversation handler for setprompt
        setprompt_handler = ConversationHandler(
            entry_points=[CommandHandler('setprompt', self.setprompt_start)],
            states={
                WAITING_NEW_PERSONALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_new_personality)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
        )
        self.application.add_handler(setprompt_handler)
        
        self.application.add_handler(CommandHandler('start', self.start_command))
        self.application.add_handler(CommandHandler('help', self.help_command))
        self.application.add_handler(CommandHandler('listbots', self.listbots_command))
        self.application.add_handler(CommandHandler('editbot', self.editbot_command))
        self.application.add_handler(CommandHandler('togglefeature', self.togglefeature_command))
        self.application.add_handler(CommandHandler('botstatus', self.botstatus_command))
        self.application.add_handler(CommandHandler('reloadbot', self.reloadbot_command))
        self.application.add_handler(CommandHandler('removebot', self.removebot_command))
        
        return self.application
    
    async def run(self):
        """Run the admin bot."""
        app = self.build_application()
        
        logger.info("Starting Admin Bot...")
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        # Keep running
        while True:
            await asyncio.sleep(1)
    
    async def stop(self):
        """Stop the admin bot."""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
