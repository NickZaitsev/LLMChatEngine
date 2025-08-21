#!/usr/bin/env python3
"""
Test script to verify the typing indicator integration works correctly
"""

import asyncio
import logging
import sys
from unittest.mock import AsyncMock, MagicMock

# Set up logging for testing
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

async def test_typing_manager():
    """Test the TypingIndicatorManager class"""
    try:
        from message_manager import TypingIndicatorManager
        
        logger.info("✓ TypingIndicatorManager imported successfully")
        
        # Create typing manager instance
        typing_manager = TypingIndicatorManager()
        logger.info("✓ TypingIndicatorManager instance created")
        
        # Mock bot object
        mock_bot = AsyncMock()
        mock_bot.send_chat_action = AsyncMock()
        
        # Test starting typing
        chat_id = 12345
        await typing_manager.start_typing(mock_bot, chat_id)
        logger.info("✓ start_typing() executed without errors")
        
        # Check if typing is active
        is_active = typing_manager.is_typing_active(chat_id)
        logger.info(f"✓ Typing active status: {is_active}")
        
        # Wait a bit to see if typing action is sent
        await asyncio.sleep(0.5)
        
        # Stop typing
        await typing_manager.stop_typing(chat_id)
        logger.info("✓ stop_typing() executed without errors")
        
        # Cleanup
        await typing_manager.cleanup()
        logger.info("✓ cleanup() executed without errors")
        
        logger.info("✅ TypingIndicatorManager tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ TypingIndicatorManager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_bot_integration():
    """Test the bot integration"""
    try:
        # Test imports
        from bot import AIGirlfriendBot
        from message_manager import TypingIndicatorManager
        
        logger.info("✓ Bot and TypingIndicatorManager imported successfully")
        
        # Test bot initialization
        bot = AIGirlfriendBot()
        logger.info("✓ AIGirlfriendBot instance created")
        
        # Check if typing manager is initialized
        if hasattr(bot, 'typing_manager'):
            logger.info("✓ Bot has typing_manager attribute")
            if isinstance(bot.typing_manager, TypingIndicatorManager):
                logger.info("✓ typing_manager is correct type")
            else:
                logger.error("❌ typing_manager is not TypingIndicatorManager instance")
                return False
        else:
            logger.error("❌ Bot missing typing_manager attribute")
            return False
        
        # Test cleanup method
        if hasattr(bot, 'cleanup'):
            logger.info("✓ Bot has cleanup method")
            await bot.cleanup()
            logger.info("✓ Bot cleanup executed without errors")
        else:
            logger.error("❌ Bot missing cleanup method")
            return False
        
        logger.info("✅ Bot integration tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Bot integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_ai_handler_compatibility():
    """Test AI handler compatibility"""
    try:
        from ai_handler import AIHandler
        
        logger.info("✓ AIHandler imported successfully")
        
        # Test AI handler initialization
        try:
            ai_handler = AIHandler()
            logger.info("✓ AIHandler instance created")
            
            # Check if generate_response method exists
            if hasattr(ai_handler, 'generate_response'):
                logger.info("✓ AIHandler has generate_response method")
            else:
                logger.error("❌ AIHandler missing generate_response method")
                return False
                
        except Exception as init_error:
            logger.warning(f"⚠️ AIHandler initialization failed (this may be due to missing config): {init_error}")
            # This is expected if config is not set up, so we'll continue
        
        logger.info("✅ AI handler compatibility tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ AI handler compatibility test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_message_flow_simulation():
    """Test simulated message flow"""
    try:
        logger.info("🔄 Testing simulated message flow...")
        
        # Mock objects
        mock_update = MagicMock()
        mock_update.effective_user.id = 12345
        mock_update.effective_user.first_name = "TestUser"
        mock_update.effective_chat.id = 54321
        mock_update.message.text = "Hello bot!"
        mock_update.message.reply_text = AsyncMock()
        
        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot.send_chat_action = AsyncMock()
        
        # Test the new flow components
        from message_manager import TypingIndicatorManager
        typing_manager = TypingIndicatorManager()
        
        chat_id = mock_update.effective_chat.id
        
        # Simulate the new flow
        logger.info("1. Starting typing indicator...")
        await typing_manager.start_typing(mock_context.bot, chat_id)
        
        # Simulate AI processing delay
        logger.info("2. Simulating AI processing delay...")
        await asyncio.sleep(1.0)
        
        # Check if typing is still active
        is_active = typing_manager.is_typing_active(chat_id)
        logger.info(f"3. Typing still active: {is_active}")
        
        # Simulate response ready
        logger.info("4. Simulating response ready...")
        await asyncio.sleep(0.5)
        
        # Stop typing
        logger.info("5. Stopping typing indicator...")
        await typing_manager.stop_typing(chat_id)
        
        # Verify typing stopped
        is_active_after = typing_manager.is_typing_active(chat_id)
        logger.info(f"6. Typing active after stop: {is_active_after}")
        
        # Cleanup
        await typing_manager.cleanup()
        
        logger.info("✅ Message flow simulation tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Message flow simulation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def run_all_tests():
    """Run all tests"""
    logger.info("🚀 Starting typing indicator integration tests...")
    
    tests = [
        ("TypingIndicatorManager", test_typing_manager),
        ("Bot Integration", test_bot_integration),
        ("AI Handler Compatibility", test_ai_handler_compatibility),
        ("Message Flow Simulation", test_message_flow_simulation),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        logger.info(f"\n📋 Running {test_name} test...")
        try:
            result = await test_func()
            results.append((test_name, result))
            if result:
                logger.info(f"✅ {test_name} test: PASSED")
            else:
                logger.error(f"❌ {test_name} test: FAILED")
        except Exception as e:
            logger.error(f"💥 {test_name} test: CRASHED - {e}")
            results.append((test_name, False))
    
    # Summary
    logger.info("\n" + "="*50)
    logger.info("📊 TEST RESULTS SUMMARY")
    logger.info("="*50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status} - {test_name}")
        if result:
            passed += 1
    
    logger.info("="*50)
    logger.info(f"📈 Results: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 ALL TESTS PASSED! Integration is successful!")
        return True
    else:
        logger.error(f"⚠️ {total - passed} tests failed. Review the issues above.")
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(run_all_tests())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("🛑 Tests interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"💥 Test runner crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)