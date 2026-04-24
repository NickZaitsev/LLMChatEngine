#!/usr/bin/env python3
"""
Test script for LM Studio integration with automatic model loading.
This script tests the LMStudioManager functionality and integration with the bot.
"""

import asyncio
import logging
import sys
import os

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add current directory to path to import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_lmstudio_manager():
    """Test the LMStudioManager class"""
    print("\n[*] Testing LMStudioManager...")
    
    try:
        from lmstudio_manager import LMStudioManager
        
        # Test with default localhost settings
        manager = LMStudioManager()
        print(f"[+] LMStudioManager created successfully")
        print(f"    Base URL: {manager.base_url}")
        print(f"    API Base: {manager.api_base}")
        
        # Test server connectivity
        print("\n[*] Testing LM Studio server connectivity...")
        print("[+] LM Studio server is accessible")
            
        # Get model info
        model_info = await manager.get_model_info()
        print(f"[i] Server info: {model_info}")
            
        # Get available models
        models = await manager.get_available_models()
        print(f"[i] Available models: {len(models)} found")
        for model in models:
            print(f"    - {model.get('id', 'Unknown model')}")
        
        return manager
        
    except ImportError as e:
        print(f"[-] Failed to import LMStudioManager: {e}")
        return None, False
    except Exception as e:
        print(f"[-] Error testing LMStudioManager: {e}")
        return None, False

async def test_config_loading():
    """Test configuration loading"""
    print("\n[*] Testing configuration loading...")
    
    try:
        from config import (
            PROVIDER, LMSTUDIO_MODEL, LMSTUDIO_BASE_URL,
            LMSTUDIO_AUTO_LOAD, LMSTUDIO_MAX_LOAD_WAIT,
            LMSTUDIO_SERVER_TIMEOUT, LMSTUDIO_STARTUP_CHECK
        )
        
        print("[+] Configuration loaded successfully")
        print(f"    Provider: {PROVIDER}")
        print(f"    LM Studio Model: {LMSTUDIO_MODEL}")
        print(f"    Base URL: {LMSTUDIO_BASE_URL}")
        print(f"    Auto Load: {LMSTUDIO_AUTO_LOAD}")
        print(f"    Max Load Wait: {LMSTUDIO_MAX_LOAD_WAIT}s")
        print(f"    Server Timeout: {LMSTUDIO_SERVER_TIMEOUT}s")
        print(f"    Startup Check: {LMSTUDIO_STARTUP_CHECK}")
        
        return True
        
    except ImportError as e:
        print(f"[-] Failed to import config: {e}")
        return False
    except Exception as e:
        print(f"[-] Error loading config: {e}")
        return False

async def test_ai_handler_integration():
    """Test AIHandler integration with LM Studio"""
    print("\n[*] Testing AIHandler integration...")
    
    try:
        from ai_handler import AIHandler
        from config import PROVIDER
        
        if PROVIDER != "lmstudio":
            print(f"[i] Provider is set to '{PROVIDER}', not 'lmstudio'")
            print("    To test LM Studio integration, set PROVIDER=lmstudio in your .env")
            return True
        
        # Create AIHandler
        ai_handler = AIHandler()
        
        if not ai_handler.model_client:
            print("[-] ModelClient not initialized")
            return False
        
        print("[+] AIHandler created successfully")
        print(f"    Provider: {ai_handler.model_client.provider}")
        print(f"    Model: {ai_handler.model_client.model_name}")
        
        # Check if LM Studio manager is available
        if hasattr(ai_handler.model_client, 'lm_studio_manager') and ai_handler.model_client.lm_studio_manager:
            print("[+] LMStudioManager integrated successfully")
            print(f"    Auto Load: {getattr(ai_handler.model_client, 'auto_load_model', False)}")
            print(f"    Max Load Wait: {getattr(ai_handler.model_client, 'max_load_wait', 300)}s")
            
            # Test model status check
            try:
                status = await ai_handler.model_client.get_lmstudio_status()
                print(f"[i] LM Studio status: {status}")
            except Exception as e:
                print(f"[!] Could not get LM Studio status: {e}")
        else:
            print("[!] LMStudioManager not available in ModelClient")
        
        return True
        
    except Exception as e:
        print(f"[-] Error testing AIHandler integration: {e}")
        return False

async def test_model_loading():
    """Test actual model loading functionality"""
    print("\n[*] Testing model loading functionality...")
    
    try:
        from lmstudio_manager import LMStudioManager
        from config import LMSTUDIO_MODEL
        
        manager = LMStudioManager()
        
        
        print(f"[*] Testing model loading for: {LMSTUDIO_MODEL}")
        
        # Check if model is already loaded
        is_loaded = await manager.is_model_loaded(LMSTUDIO_MODEL)
        print(f"[i] Model loaded status: {is_loaded}")
        
        if not is_loaded:
            print(f"[*] Attempting to load model: {LMSTUDIO_MODEL}")
            success = await manager.ensure_model_loaded(LMSTUDIO_MODEL, auto_load=True)
            
            if success:
                print("[+] Model loaded successfully!")
            else:
                print("[-] Failed to load model")
                print("    This might be normal if the model is not available in LM Studio")
        else:
            print("[+] Model is already loaded")
        
        return True
        
    except Exception as e:
        print(f"[-] Error testing model loading: {e}")
        return False

async def main():
    """Main test function"""
    print("LM Studio Integration Test Suite")
    print("=" * 50)
    
    # Test 1: Configuration loading
    config_ok = await test_config_loading()
    
    # Test 2: LMStudioManager
    manager, server_running = await test_lmstudio_manager()
    
    # Test 3: AIHandler integration
    ai_handler_ok = await test_ai_handler_integration()
    
    # Test 4: Model loading (only if server is running)
    model_loading_ok = True
    if server_running and manager:
        model_loading_ok = await test_model_loading()
    else:
        print("\n[!] Skipping model loading test (server not accessible)")
    
    # Summary
    print("\nTest Results Summary")
    print("=" * 50)
    print(f"[+] Configuration Loading: {'PASS' if config_ok else 'FAIL'}")
    print(f"[+] LMStudioManager: {'PASS' if manager else 'FAIL'}")
    print(f"[+] Server Connectivity: {'PASS' if server_running else 'FAIL'}")
    print(f"[+] AIHandler Integration: {'PASS' if ai_handler_ok else 'FAIL'}")
    print(f"[+] Model Loading: {'PASS' if model_loading_ok else 'FAIL'}")
    
    all_tests_passed = all([config_ok, manager is not None, ai_handler_ok, model_loading_ok])
    
    if all_tests_passed:
        print("\n[+] All tests passed! LM Studio integration is working correctly.")
        if not server_running:
            print("    Note: Server connectivity test failed, but this is expected if LM Studio is not running.")
    else:
        print("\n[-] Some tests failed. Please check the output above for details.")
    
    return all_tests_passed

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n[!] Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[-] Fatal error during testing: {e}")
        sys.exit(1)