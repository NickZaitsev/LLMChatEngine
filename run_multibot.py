"""
Multi-bot entry point.

Runs the admin bot and all configured user bots concurrently.
Usage: python run_multibot.py
"""

import asyncio
import logging
import os
import signal
import sys

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def main():
    """Main entry point for multi-bot system."""
    from admin_bot import AdminBot
    from bot_manager import BotManager
    
    # Get configuration from environment
    admin_token = os.getenv('ADMIN_BOT_TOKEN')
    admin_user_ids_str = os.getenv('ADMIN_USER_IDS', '')
    db_url = os.getenv('DATABASE_URL')
    
    if not admin_token:
        logger.error("ADMIN_BOT_TOKEN is required")
        sys.exit(1)
    
    if not db_url:
        logger.error("DATABASE_URL is required")
        sys.exit(1)
    
    # Parse admin user IDs
    admin_user_ids = []
    if admin_user_ids_str:
        try:
            admin_user_ids = [int(x.strip()) for x in admin_user_ids_str.split(',') if x.strip()]
        except ValueError as e:
            logger.error(f"Invalid ADMIN_USER_IDS format: {e}")
            sys.exit(1)
    
    if not admin_user_ids:
        logger.warning("No ADMIN_USER_IDS configured. Admin bot will reject all users.")
    
    logger.info(f"Starting multi-bot system with {len(admin_user_ids)} admin users")
    
    # Initialize admin bot
    admin_bot = AdminBot(
        admin_token=admin_token,
        admin_user_ids=admin_user_ids,
        db_url=db_url
    )
    
    # Initialize bot manager
    bot_manager = BotManager(db_url=db_url)
    
    # Connect admin bot to bot manager for hot-reload
    admin_bot.set_bot_manager(bot_manager)
    
    # Load bots from database
    try:
        logger.info("Loading bots from database...")
        await bot_manager.load_bots_from_db()
        logger.info("Bots loaded successfully")
    except Exception as e:
        logger.exception(f"Failed to load bots: {e}")
        # Continue running admin bot even if user bots fail

    
    # Handle shutdown signals
    shutdown_event = asyncio.Event()
    
    def signal_handler():
        logger.info("Shutdown signal received")
        shutdown_event.set()
    
    # Register signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, lambda s, f: signal_handler())
    
    # Create tasks for both admin bot and bot manager
    async def run_admin():
        try:
            await admin_bot.run()
        except asyncio.CancelledError:
            await admin_bot.stop()
            raise
        finally:
            try:
                await admin_bot.stop()
            except Exception as e:
                logger.error("Failed to stop admin bot cleanly: %s", e)
    
    async def run_bots():
        try:
            await bot_manager.run_all()
        except asyncio.CancelledError:
            await bot_manager.stop_all()
            raise
        finally:
            try:
                await bot_manager.stop_all()
            except Exception as e:
                logger.error("Failed to stop bot manager cleanly: %s", e)
    
    admin_task = asyncio.create_task(run_admin(), name="admin_bot")
    bots_task = asyncio.create_task(run_bots(), name="bot_manager")

    def monitor_task(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error("Background task %s crashed: %s", task.get_name(), error)
            shutdown_event.set()

    admin_task.add_done_callback(monitor_task)
    bots_task.add_done_callback(monitor_task)
    
    logger.info("Multi-bot system started")
    logger.info("Press Ctrl+C to stop")
    
    # Wait for shutdown
    await shutdown_event.wait()
    
    # Cancel tasks
    logger.info("Shutting down...")
    admin_task.cancel()
    bots_task.cancel()
    
    try:
        await asyncio.gather(admin_task, bots_task, return_exceptions=True)
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    
    logger.info("Multi-bot system stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
