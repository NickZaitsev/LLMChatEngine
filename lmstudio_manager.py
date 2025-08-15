import asyncio
import logging
import requests
import json
from typing import Optional, Dict, List
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class LMStudioManager:
    """Manager for LM Studio model operations including automatic loading"""
    
    def __init__(self, base_url: str = "http://localhost:1234", timeout: int = 30):
        """
        Initialize LM Studio Manager
        
        Args:
            base_url: LM Studio server base URL (without /v1)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.api_base = f"{self.base_url}/v1"
        self.timeout = timeout
        logger.info("LMStudioManager initialized with base URL: %s", self.base_url)
    
    async def is_server_running(self) -> bool:
        """Check if LM Studio server is running"""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.get(f"{self.api_base}/models", timeout=5)
            )
            return response.status_code == 200
        except Exception as e:
            logger.debug("LM Studio server not responding: %s", e)
            return False
    
    async def get_available_models(self) -> List[Dict]:
        """Get list of available models from LM Studio"""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(f"{self.api_base}/models", timeout=self.timeout)
            )
            
            if response.status_code == 200:
                data = response.json()
                models = data.get('data', [])
                logger.info("Found %d available models in LM Studio", len(models))
                return models
            else:
                logger.error("Failed to get models from LM Studio: HTTP %d", response.status_code)
                return []
                
        except Exception as e:
            logger.error("Error getting available models: %s", e)
            return []
    
    async def get_loaded_model(self) -> Optional[str]:
        """Get the currently loaded model name"""
        models = await self.get_available_models()
        
        # In LM Studio, loaded models typically appear in the models list
        # We can also check for any model that's actually loaded by trying to use it
        if models:
            # Return the first model found, or implement logic to detect which is loaded
            loaded_models = [model['id'] for model in models if model.get('id')]
            if loaded_models:
                current_model = loaded_models[0]
                logger.info("Currently loaded model: %s", current_model)
                return current_model
        
        return None
    
    async def is_model_loaded(self, model_name: str) -> bool:
        """Check if a specific model is loaded"""
        try:
            # Try to make a simple completion request to test if model is loaded
            loop = asyncio.get_event_loop()
            test_payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1,
                "temperature": 0
            }
            
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.api_base}/chat/completions", 
                    json=test_payload, 
                    timeout=10
                )
            )
            
            if response.status_code == 200:
                logger.info("Model %s is loaded and ready", model_name)
                return True
            else:
                logger.debug("Model %s test failed: HTTP %d", model_name, response.status_code)
                return False
                
        except Exception as e:
            logger.debug("Error testing model %s: %s", model_name, e)
            return False
    
    async def load_model(self, model_name: str, wait_for_load: bool = True, max_wait_time: int = 300) -> bool:
        """
        Load a model into LM Studio
        
        Args:
            model_name: Name/path of the model to load
            wait_for_load: Whether to wait for the model to finish loading
            max_wait_time: Maximum time to wait for model loading (seconds)
            
        Returns:
            True if model was loaded successfully, False otherwise
        """
        try:
            logger.info("Attempting to load model: %s", model_name)
            
            # Check if model is already loaded
            if await self.is_model_loaded(model_name):
                logger.info("Model %s is already loaded", model_name)
                return True
            
            # Try LM Studio specific model loading endpoint
            # Note: LM Studio's API varies by version, so we'll try multiple approaches
            success = await self._try_load_model_methods(model_name)
            
            if not success:
                logger.error("Failed to load model %s using available methods", model_name)
                return False
            
            if wait_for_load:
                logger.info("Waiting for model %s to finish loading (max %ds)...", model_name, max_wait_time)
                start_time = asyncio.get_event_loop().time()
                
                while (asyncio.get_event_loop().time() - start_time) < max_wait_time:
                    if await self.is_model_loaded(model_name):
                        logger.info("Model %s loaded successfully", model_name)
                        return True
                    
                    await asyncio.sleep(2)
                
                logger.warning("Model %s did not load within %d seconds", model_name, max_wait_time)
                return False
            
            return success
            
        except Exception as e:
            logger.error("Error loading model %s: %s", model_name, e)
            return False
    
    async def _try_load_model_methods(self, model_name: str) -> bool:
        """Try different methods to load a model"""
        loop = asyncio.get_event_loop()
        
        # Method 1: Try LM Studio's load-model endpoint (if available)
        try:
            payload = {"model": model_name}
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.base_url}/api/load-model",
                    json=payload,
                    timeout=self.timeout
                )
            )
            
            if response.status_code in [200, 201, 202]:
                logger.info("Model loading initiated via /api/load-model")
                return True
                
        except Exception as e:
            logger.debug("Method 1 failed: %s", e)
        
        # Method 2: Try alternative endpoint
        try:
            payload = {"model_path": model_name}
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.base_url}/load",
                    json=payload,
                    timeout=self.timeout
                )
            )
            
            if response.status_code in [200, 201, 202]:
                logger.info("Model loading initiated via /load endpoint")
                return True
                
        except Exception as e:
            logger.debug("Method 2 failed: %s", e)
        
        # Method 3: Try making a request which might trigger auto-loading
        try:
            test_payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1
            }
            
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.api_base}/chat/completions",
                    json=test_payload,
                    timeout=30  # Longer timeout for potential model loading
                )
            )
            
            # Even if the request fails, it might trigger model loading
            logger.info("Attempted to trigger model loading via completion request")
            return True
            
        except Exception as e:
            logger.debug("Method 3 failed: %s", e)
        
        return False
    
    async def unload_model(self) -> bool:
        """Unload the currently loaded model"""
        try:
            loop = asyncio.get_event_loop()
            
            # Try unload endpoint
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(f"{self.base_url}/api/unload-model", timeout=self.timeout)
            )
            
            if response.status_code in [200, 201, 202]:
                logger.info("Model unloaded successfully")
                return True
            else:
                logger.warning("Model unload returned HTTP %d", response.status_code)
                return False
                
        except Exception as e:
            logger.error("Error unloading model: %s", e)
            return False
    
    async def get_model_info(self) -> Dict:
        """Get information about the LM Studio server and loaded models"""
        try:
            server_running = await self.is_server_running()
            available_models = await self.get_available_models() if server_running else []
            loaded_model = await self.get_loaded_model() if server_running else None
            
            return {
                "server_running": server_running,
                "base_url": self.base_url,
                "api_base": self.api_base,
                "loaded_model": loaded_model,
                "available_models": [model.get('id', 'unknown') for model in available_models],
                "model_count": len(available_models)
            }
            
        except Exception as e:
            logger.error("Error getting model info: %s", e)
            return {
                "server_running": False,
                "error": str(e)
            }
    
    async def ensure_model_loaded(self, model_name: str, auto_load: bool = True) -> bool:
        """
        Ensure a specific model is loaded, optionally loading it automatically
        
        Args:
            model_name: The model to ensure is loaded
            auto_load: Whether to automatically load the model if not loaded
            
        Returns:
            True if model is loaded (or was successfully loaded), False otherwise
        """
        try:
            logger.info("Ensuring model %s is loaded (auto_load=%s)", model_name, auto_load)
            
            # First check if server is running
            if not await self.is_server_running():
                logger.error("LM Studio server is not running")
                return False
            
            # Check if model is already loaded
            if await self.is_model_loaded(model_name):
                logger.info("Model %s is already loaded and ready", model_name)
                return True
            
            if not auto_load:
                logger.info("Model %s is not loaded and auto_load is disabled", model_name)
                return False
            
            # Attempt to load the model
            logger.info("Model %s not loaded, attempting to load...", model_name)
            success = await self.load_model(model_name, wait_for_load=True)
            
            if success:
                logger.info("Successfully loaded model %s", model_name)
            else:
                logger.error("Failed to load model %s", model_name)
            
            return success
            
        except Exception as e:
            logger.error("Error ensuring model %s is loaded: %s", model_name, e)
            return False