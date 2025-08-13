import asyncio
import logging
import random
from typing import List, Dict

from config import BOT_PERSONALITY, MAX_TOKENS, TEMPERATURE

# Import OpenAI clients (v1+)
try:
    from openai import OpenAI, AzureOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None
    AzureOpenAI = None

# Constants
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 60.0
DEFAULT_REQUEST_TIMEOUT = 30.0
RETRYABLE_ERROR_PATTERNS = [
    "rate limit", "429", "ratelimitreached", "too many requests",
    "timeout", "timed out", "request timeout",
    "service unavailable", "503", "unavailable", "down",
    "connection", "network", "unreachable", "refused"
]

logger = logging.getLogger(__name__)


class ModelClient:
    """Abstracts interaction with different LLM providers"""
    
    def __init__(self, provider="azure"):
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI package not available. Install with: pip install openai")
        
        self.provider = provider
        
        if provider == "azure":
            from config import AZURE_ENDPOINT, AZURE_API_KEY, AZURE_MODEL
            
            if not all([AZURE_ENDPOINT, AZURE_API_KEY, AZURE_MODEL]):
                raise ValueError("Azure provider requires AZURE_ENDPOINT, AZURE_API_KEY, and AZURE_MODEL to be set in .env")
            
            self.client = AzureOpenAI(
                azure_endpoint=AZURE_ENDPOINT,
                api_key=AZURE_API_KEY,
                api_version="2024-06-01",
            )
            self.model_name = AZURE_MODEL
            logger.info("ModelClient initialized with Azure provider - Model: %s", AZURE_MODEL)
            
        elif provider == "lmstudio":
            from config import LMSTUDIO_MODEL
            
            self.client = OpenAI(
                base_url="http://localhost:1234/v1",
                api_key="lm-studio",
            )
            self.model_name = LMSTUDIO_MODEL
            logger.info("ModelClient initialized with LM Studio provider - Model: %s", LMSTUDIO_MODEL)
            
        else:
            raise ValueError(f"Unsupported provider: {provider}. Supported providers: 'azure', 'lmstudio'")
    
    def ask(self, messages):
        """Send a message to the LLM and get a response"""
        try:
            logger.debug("Sending request to %s provider", self.provider)
            
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages
            )
            
            content = resp.choices[0].message.content
            logger.debug("Received response from %s provider (%d chars)", self.provider, len(content))
            return content
            
        except Exception as e:
            logger.error("Error in %s provider: %s", self.provider, e)
            raise e
    
    def get_provider_info(self):
        """Get information about the current provider configuration"""
        info = {
            "provider": self.provider,
            "model_name": self.model_name,
        }
        
        try:
            if hasattr(self.client, "base_url") and self.client.base_url:
                info["base_url"] = str(self.client.base_url)
            if hasattr(self.client, "azure_endpoint") and self.client.azure_endpoint:
                info["azure_endpoint"] = self.client.azure_endpoint
            if hasattr(self.client, "api_version") and self.client.api_version:
                info["api_version"] = self.client.api_version
        except Exception:
            pass
            
        return info


class AIHandler:
    def __init__(self):
        self.personality = BOT_PERSONALITY
        self.max_tokens = MAX_TOKENS
        self.temperature = TEMPERATURE
        
        # Retry configuration
        self.max_retries = DEFAULT_MAX_RETRIES
        self.base_delay = DEFAULT_BASE_DELAY
        self.max_delay = DEFAULT_MAX_DELAY
        self.request_timeout = DEFAULT_REQUEST_TIMEOUT
        
        # Initialize ModelClient
        try:
            from config import PROVIDER
            self.model_client = ModelClient(provider=PROVIDER)
            logger.info("AIHandler initialized with %s provider via ModelClient", PROVIDER)
        except Exception as e:
            logger.error("Failed to initialize ModelClient: %s", e)
            self.model_client = None
    
    async def generate_response(self, user_message: str, conversation_history: List[Dict]) -> str:
        """Generate a response using ModelClient with proper timeout handling."""
        if not self.model_client:
            logger.error("ModelClient not available; cannot generate AI response")
            return "I'm having technical difficulties right now. Please check my configuration! 💕"

        try:
            logger.info("Generating response for message (%d chars), history: %d messages", 
                       len(user_message), len(conversation_history))

            # Build messages in OpenAI format
            messages = [{"role": "system", "content": self.personality}]
            for msg in conversation_history:
                role = msg.get("role")
                content = msg.get("content", "")
                if role in ["user", "assistant"]:
                    messages.append({"role": role, "content": content})

            logger.info("Sending %d messages to LLM (including system message)", len(messages))
            
            # Retry logic with exponential backoff and proper timeout
            for attempt in range(self.max_retries):
                logger.info("Attempt %d/%d", attempt + 1, self.max_retries)
                
                try:
                    response = await asyncio.wait_for(
                        self._make_ai_request(messages),
                        timeout=self.request_timeout
                    )
                    
                    if attempt > 0:
                        logger.info("Success on retry attempt %d/%d", attempt + 1, self.max_retries)
                    
                    logger.info("Response received (%d chars)", len(response))
                    return response
                    
                except asyncio.TimeoutError:
                    logger.warning("Request timed out on attempt %d/%d after %.1f seconds", 
                                 attempt + 1, self.max_retries, self.request_timeout)
                    
                    if attempt < self.max_retries - 1:
                        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                        logger.info("Retrying in %.1f seconds...", delay)
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error("Max retries reached due to timeouts")
                        raise Exception("AI service is taking too long to respond. Please try again later.")
                        
                except Exception as e:
                    error_message = str(e).lower()
                    
                    # Check if this is a retryable error
                    is_retryable = any(pattern in error_message for pattern in RETRYABLE_ERROR_PATTERNS)
                    
                    if is_retryable and attempt < self.max_retries - 1:
                        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                        logger.warning("Retryable error on attempt %d/%d, retrying in %.1f seconds: %s", 
                                     attempt + 1, self.max_retries, delay, e)
                        await asyncio.sleep(delay)
                        continue
                    else:
                        if attempt >= self.max_retries - 1:
                            logger.error("Max retries (%d) reached. Final error: %s", self.max_retries, e)
                        else:
                            logger.error("Non-retryable error on attempt %d: %s", attempt + 1, e)
                        raise e
            
            raise Exception("Max retries exceeded")
        
        except Exception as e:
            logger.exception("Error in AI generation: %s", e)
            return self._get_error_response(str(e))
    
    def _get_error_response(self, error_message: str) -> str:
        """Generate appropriate error response based on error type"""
        error_lower = error_message.lower()
        
        if any(pattern in error_lower for pattern in ["rate limit", "429", "ratelimitreached"]):
            return "😔 I'm getting a bit overwhelmed right now! Too many people are chatting with me at once. Please wait a few minutes and try again! 💕"
        elif any(pattern in error_lower for pattern in ["timeout", "timed out"]):
            return "⏰ I'm taking longer than usual to think! The AI service is a bit slow right now. Please try again in a moment! 💕"
        elif any(pattern in error_lower for pattern in ["unauthorized", "401"]):
            return "🔑 I'm having trouble with my credentials right now. Please check my configuration! 💕"
        elif any(pattern in error_lower for pattern in ["quota exceeded", "quota"]):
            return "💳 I've reached my conversation limit for today! Please try again tomorrow! 💕"
        elif any(pattern in error_lower for pattern in ["service unavailable", "503"]):
            return "🔧 The AI service is temporarily unavailable! Please try again in a few minutes! 💕"
        elif any(pattern in error_lower for pattern in ["network", "connection"]):
            return "🌐 I'm having trouble connecting to my brain right now! Please check your internet connection and try again! 💕"
        else:
            return "😔 I'm having some technical difficulties right now. Please try again later! 💕"
    
    async def _make_ai_request(self, messages):
        """Make the actual AI API request using ModelClient"""
        try:
            logger.info("Making LLM API call via ModelClient")
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                self.model_client.ask, 
                messages
            )
            
            logger.info("LLM API call completed successfully")
            return response
            
        except Exception as e:
            logger.error("Error in _make_ai_request: %s (%s)", e, type(e).__name__)
            raise e
    
    def get_personality(self) -> str:
        """Get the current bot personality"""
        return self.personality
    
    def update_personality(self, new_personality: str) -> None:
        """Update the bot personality"""
        self.personality = new_personality
    
    def get_provider_info(self) -> Dict:
        """Get information about the current LLM provider"""
        if self.model_client:
            return self.model_client.get_provider_info()
        else:
            return {"error": "ModelClient not available"}
    
    def update_provider(self, new_provider: str) -> bool:
        """Update the LLM provider"""
        try:
            self.model_client = ModelClient(provider=new_provider)
            logger.info("Provider updated to: %s", new_provider)
            return True
        except Exception as e:
            logger.error("Failed to update provider to %s: %s", new_provider, e)
            return False
    
    def get_retry_config(self) -> Dict:
        """Get current retry configuration"""
        return {
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "max_delay": self.max_delay,
            "request_timeout": self.request_timeout
        }
    
    def update_retry_config(self, max_retries: int = None, base_delay: float = None, 
                           max_delay: float = None, request_timeout: float = None) -> None:
        """Update retry configuration"""
        if max_retries is not None:
            self.max_retries = max_retries
        if base_delay is not None:
            self.base_delay = base_delay
        if max_delay is not None:
            self.max_delay = max_delay
        if request_timeout is not None:
            self.request_timeout = request_timeout
        
        logger.info("Updated retry config: max_retries=%d, base_delay=%.1fs, max_delay=%.1fs, timeout=%.1fs", 
                   self.max_retries, self.base_delay, self.max_delay, self.request_timeout)
    
    def is_available(self) -> bool:
        """Check if the AI handler is available and ready"""
        return self.model_client is not None
    
    def get_model_info(self) -> Dict:
        """Get information about the current model and configuration"""
        if not self.model_client:
            return {"error": "ModelClient not available"}
        
        provider_info = self.model_client.get_provider_info()
        return {
            "provider": provider_info.get("provider"),
            "model": provider_info.get("model_name"),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "personality": self.personality,
            "retry_config": self.get_retry_config()
        }
    
    def generate_greeting(self, user_name: str = None) -> str:
        """Generate a personalized greeting"""
        if user_name:
            greetings = [
                f"Hey {user_name}! 💕 How are you doing today?",
                f"Hi {user_name}! 🌸 I've been thinking about you!",
                f"Hello {user_name}! ✨ I'm so happy to chat with you!",
                f"Hey there {user_name}! 💖 How's your day going?",
                f"Hi beautiful {user_name}! 🌺 I missed you!"
            ]
            return random.choice(greetings)
        else:
            return random.choice([
                "Hey there! 💕 How are you doing today?",
                "Hi! 🌸 I'm so happy to chat with you!",
                "Hello! ✨ How's your day going?",
                "Hey! 💖 I'm here for you!"
            ])
    
    def generate_goodbye(self, user_name: str = None) -> str:
        """Generate a personalized goodbye"""
        if user_name:
            goodbyes = [
                f"Goodbye {user_name}! 💕 Take care and I'll be here when you want to chat again!",
                f"See you later {user_name}! 🌸 I'll miss you!",
                f"Bye {user_name}! ✨ Have a wonderful day!",
                f"Take care {user_name}! 💖 I'll be thinking of you!",
                f"Until next time {user_name}! 🌺 Stay safe and happy!"
            ]
            return random.choice(goodbyes)
        else:
            return random.choice([
                "Goodbye! 💕 Take care and I'll be here when you want to chat again!",
                "See you later! 🌸 I'll miss you!",
                "Bye! ✨ Have a wonderful day!",
                "Take care! 💖 I'll be thinking of you!"
            ])