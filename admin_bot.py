"""
Admin Bot for managing multi-bot configuration.

This bot allows administrators to:
- Add, edit, and remove user bots
- Change bot personalities on the fly
- Toggle feature flags
- Monitor bot status
"""

import asyncio
import hashlib
import logging
from pathlib import Path
import uuid
from typing import Optional, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes

from token_encryption import encrypt_token, decrypt_token
from features import BotFeature, DEFAULT_FEATURE_FLAGS, has_feature
from config import BOOKS_STORAGE_DIR, MEMORY_EMBED_DIM
from knowledge.manager import BookKnowledgeManager
from knowledge.store import BookVectorStore
from memory.embedding_factory import build_embedding_model

logger = logging.getLogger(__name__)

MAX_BOOK_FILE_SIZE = 20 * 1024 * 1024
SUPPORTED_BOOK_FORMATS = {"txt", "pdf", "epub", "fb2"}


# Conversation states for multi-step commands
(
    WAITING_TOKEN,
    WAITING_NAME,
    WAITING_PERSONALITY,
    WAITING_EDIT_FIELD,
    WAITING_EDIT_VALUE,
    WAITING_NEW_PERSONALITY,
    WAITING_BOOK_FILE,
    WAITING_BOOK_META,
) = range(8)


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
/addbook - Attach a book to a bot
/listbooks - List a bot's books
/removebook - Remove a book
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
            "_You are Luna, a caring and attentive AI companion..._",
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

            new_bot = await self.storage.bots.create_bot(
                token_encrypted=encrypted_token,
                name=name,
                personality=personality,
                feature_flags=DEFAULT_FEATURE_FLAGS.copy(),
                llm_config={}
            )
            bot_id = new_bot.id

            # Clean up pending data
            del self._pending_bot_data[self._session_key(update)]

            # Build feature list for display
            features_text = "\n".join([
                f"  • `{f.value}`: {'✅' if has_feature(DEFAULT_FEATURE_FLAGS, f) else '❌'}"
                for f in BotFeature
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
        session_key = self._session_key(update)
        pending = self._pending_bot_data.get(session_key, {})
        temp_path = pending.get("temp_path")
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
        if session_key in self._pending_bot_data:
            del self._pending_bot_data[session_key]

        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END

    async def addbook_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the add book flow."""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return ConversationHandler.END

        await self._init_storage()

        if not context.args:
            await update.message.reply_text("Usage: /addbook <bot_id>")
            return ConversationHandler.END

        bot_id = context.args[0]
        try:
            bot = await self.storage.bots.get_bot(bot_id)
        except Exception as e:
            logger.error("Failed to load bot for addbook: %s", e)
            await update.message.reply_text(f"❌ Error loading bot: {e}")
            return ConversationHandler.END

        if not bot:
            await update.message.reply_text(f"❌ Bot not found: {bot_id}")
            return ConversationHandler.END

        self._pending_bot_data[self._session_key(update)] = {
            "flow": "addbook",
            "bot_id": str(bot.id),
            "bot_name": bot.name,
        }
        await update.message.reply_text(
            "Send me the book file (.txt, .pdf, .epub, .fb2, max 20 MB). /cancel to abort."
        )
        return WAITING_BOOK_FILE

    async def addbook_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive and persist a book upload."""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return ConversationHandler.END

        pending = self._pending_bot_data.get(self._session_key(update), {})
        bot_id = pending.get("bot_id")
        if not bot_id:
            await update.message.reply_text("❌ Session expired. Please start again with /addbook <bot_id>")
            return ConversationHandler.END

        document = update.message.document
        filename = document.file_name or "book"
        file_format = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if file_format not in SUPPORTED_BOOK_FORMATS:
            await update.message.reply_text("❌ Unsupported file type. Send .txt, .pdf, .epub, or .fb2.")
            return WAITING_BOOK_FILE
        if document.file_size and document.file_size > MAX_BOOK_FILE_SIZE:
            await update.message.reply_text("❌ File is too large. Telegram book uploads are limited to 20 MB.")
            return WAITING_BOOK_FILE

        storage_dir = Path(BOOKS_STORAGE_DIR)
        storage_dir.mkdir(parents=True, exist_ok=True)
        temp_path = storage_dir / f"upload-{self._session_key(update)[0]}-{self._session_key(update)[1]}.{file_format}"

        telegram_file = await context.bot.get_file(document.file_id)
        await telegram_file.download_to_drive(custom_path=str(temp_path))
        file_hash = _sha256_file(temp_path)

        duplicate = await self.storage.books.find_by_hash(bot_id, file_hash)
        if duplicate:
            temp_path.unlink(missing_ok=True)
            await update.message.reply_text(
                f"❌ This book is already attached to that bot as **{duplicate.title}**.",
                parse_mode='Markdown',
            )
            return ConversationHandler.END

        title = Path(filename).stem
        book = await self.storage.books.create_book(
            bot_id=bot_id,
            title=title,
            author=None,
            source_filename=filename,
            file_format=file_format,
            file_hash=file_hash,
        )
        final_path = storage_dir / f"{book.id}.{file_format}"
        temp_path.replace(final_path)

        pending.update(
            {
                "book_id": str(book.id),
                "source_filename": filename,
                "file_format": file_format,
                "final_path": str(final_path),
                "default_title": title,
            }
        )
        await update.message.reply_text(
            "Send the book title and author as `Title — Author`, or /skip to use the filename.",
            parse_mode='Markdown',
        )
        return WAITING_BOOK_META

    async def addbook_meta(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive book metadata and enqueue ingestion."""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return ConversationHandler.END

        pending = self._pending_bot_data.get(self._session_key(update), {})
        book_id = pending.get("book_id")
        if not book_id:
            await update.message.reply_text("❌ Session expired. Please start again with /addbook <bot_id>")
            return ConversationHandler.END

        title, author = _parse_book_meta(update.message.text, pending.get("default_title", "Book"))
        await self.storage.books.update_metadata(book_id, title, author)

        from knowledge.tasks import ingest_book

        ingest_book.delay(book_id)
        del self._pending_bot_data[self._session_key(update)]
        await update.message.reply_text("📚 Book queued for processing. Check /listbooks for status.")
        return ConversationHandler.END

    async def addbook_skip_meta(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Use default file-derived metadata for a book upload."""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return ConversationHandler.END

        pending = self._pending_bot_data.get(self._session_key(update), {})
        book_id = pending.get("book_id")
        if not book_id:
            await update.message.reply_text("❌ Session expired. Please start again with /addbook <bot_id>")
            return ConversationHandler.END

        from knowledge.tasks import ingest_book

        ingest_book.delay(book_id)
        del self._pending_bot_data[self._session_key(update)]
        await update.message.reply_text("📚 Book queued for processing. Check /listbooks for status.")
        return ConversationHandler.END

    async def listbots_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all configured bots."""
        user_id = update.effective_user.id

        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return

        await self._init_storage()

        try:
            bots = await self.storage.bots.list_bots()

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
            bot = await self.storage.bots.get_bot(bot_id)

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
            bot = await self.storage.bots.update_personality(bot_id, new_personality)
            if not bot:
                await update.message.reply_text(f"❌ Bot not found: {bot_id}")
                return ConversationHandler.END

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
            bot = await self.storage.bots.get_bot(bot_id)
            if not bot:
                await update.message.reply_text(f"❌ Bot not found: {bot_id}")
                return

            feature = BotFeature(feature_name)
            current_value = has_feature(bot.feature_flags or {}, feature)
            new_value = not current_value

            new_flags = (bot.feature_flags or {}).copy()
            new_flags[feature_name] = new_value
            bot = await self.storage.bots.update_flags(bot_id, new_flags)

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
            bot = await self.storage.bots.get_bot(bot_id)

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
                f"`/addbook {bot.id}` to attach a book\n"
                f"`/listbooks {bot.id}` to list books\n"
                f"`/reloadbot {bot.id}` to apply or restart\n"
                f"`/removebot {bot.id}` to deactivate",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to edit bot: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def listbooks_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List books attached to a bot."""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return

        await self._init_storage()
        if not context.args:
            await update.message.reply_text("Usage: /listbooks <bot_id>")
            return

        bot_id = context.args[0]
        bot = await self.storage.bots.get_bot(bot_id)
        if not bot:
            await update.message.reply_text(f"❌ Bot not found: {bot_id}")
            return

        books = await self.storage.books.list_books(bot_id)
        if not books:
            await update.message.reply_text(f"📭 No books attached to **{bot.name}**.", parse_mode='Markdown')
            return

        lines = [f"📚 **Books for {bot.name}:**", ""]
        for book in books:
            status_icon = {
                "pending": "⏳",
                "processing": "🔄",
                "ready": "✅",
                "failed": "❌",
            }.get(book.status, "•")
            author = book.author or "Unknown author"
            lines.append(
                f"{status_icon} **{book.title}** — {author} | "
                f"{book.chunk_count} chunks | ID: `{book.id}`"
            )
            if book.error:
                lines.append(f"   Error: `{book.error[:120]}`")

        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

    async def removebook_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove a book and its vector chunks."""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return

        await self._init_storage()
        if not context.args:
            await update.message.reply_text("Usage: /removebook <book_id>")
            return

        book_id = context.args[0]
        book = await self.storage.books.get_book(book_id)
        if not book:
            await update.message.reply_text(f"❌ Book not found: {book_id}")
            return

        try:
            book_knowledge_manager = BookKnowledgeManager(
                store=BookVectorStore(
                    db_url=self.db_url,
                    table_name="book_chunks",
                    embed_dim=MEMORY_EMBED_DIM,
                ),
                embedding_model=build_embedding_model(),
            )
            await book_knowledge_manager.delete_book(str(book.id))
            source_path = Path(BOOKS_STORAGE_DIR) / f"{book.id}.{book.file_format}"
            source_path.unlink(missing_ok=True)
            await self.storage.books.delete_book(str(book.id))
            await update.message.reply_text(f"✅ Removed **{book.title}**.", parse_mode='Markdown')
        except Exception as e:
            logger.error("Failed to remove book %s: %s", book_id, e, exc_info=True)
            await update.message.reply_text(f"❌ Error removing book: {e}")

    async def botstatus_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show status of all bots."""
        user_id = update.effective_user.id

        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return

        await self._init_storage()

        try:
            from storage.models import Conversation
            from sqlalchemy import select, func

            bots = await self.storage.bots.list_bots()
            if not bots:
                await update.message.reply_text("📭 No bots configured.")
                return

            async with self.storage.session_maker() as session:
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
            bot = await self.storage.bots.set_active(bot_id, False)
            if not bot:
                await update.message.reply_text(f"❌ Bot not found: {bot_id}")
                return

            await update.message.reply_text(
                f"✅ Bot **`{bot.name}`** has been deactivated.\n\n"
                "The running instance will be stopped now if the bot manager is connected.",
                parse_mode='Markdown'
            )

            # Reload config so BotManager sees the inactive state and stops the runtime cleanly.
            if self.bot_manager:
                await self.bot_manager.reload_bot_config(bot.id)
                await update.message.reply_text("Bot deactivated in runtime successfully.")

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

        addbook_handler = ConversationHandler(
            entry_points=[CommandHandler('addbook', self.addbook_start)],
            states={
                WAITING_BOOK_FILE: [MessageHandler(filters.Document.ALL, self.addbook_file)],
                WAITING_BOOK_META: [
                    CommandHandler('skip', self.addbook_skip_meta),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.addbook_meta),
                ],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
        )
        self.application.add_handler(addbook_handler)

        self.application.add_handler(CommandHandler('start', self.start_command))
        self.application.add_handler(CommandHandler('help', self.help_command))
        self.application.add_handler(CommandHandler('listbots', self.listbots_command))
        self.application.add_handler(CommandHandler('listbooks', self.listbooks_command))
        self.application.add_handler(CommandHandler('removebook', self.removebook_command))
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_book_meta(text: str, default_title: str) -> tuple[str, Optional[str]]:
    value = (text or "").strip()
    if not value:
        return default_title, None
    for separator in (" — ", " - "):
        if separator in value:
            title, author = value.split(separator, 1)
            return title.strip() or default_title, author.strip() or None
    return value, None
