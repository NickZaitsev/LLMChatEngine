import asyncio
import logging
from typing import List, Dict
from config import GITHUB_TOKEN, GITHUB_MODEL, BOT_PERSONALITY, MAX_TOKENS, TEMPERATURE


logger = logging.getLogger(__name__)


class AIHandler:
    def __init__(self):
        self.github_token = GITHUB_TOKEN
        self.model = GITHUB_MODEL
        self.personality = BOT_PERSONALITY
        self.endpoint = "https://models.github.ai/inference"
        self.max_tokens = MAX_TOKENS
        self.temperature = TEMPERATURE
    
    async def generate_response(self, user_message: str, conversation_history: List[Dict]) -> str:
        """Generate a response using GitHub's Azure AI Inference API without blocking the event loop."""
        if not self.github_token:
            logger.warning("GITHUB_TOKEN is not set; cannot generate AI response")
            return "I'm missing my GitHub credentials. Please set GITHUB_TOKEN in your environment. 💕"

        try:
            # Import Azure AI Inference SDK
            from azure.ai.inference import ChatCompletionsClient
            from azure.ai.inference.models import SystemMessage, UserMessage, AssistantMessage
            from azure.core.credentials import AzureKeyCredential
            
            logger.debug("Generating response for message (len=%d), history_len=%d", len(user_message), len(conversation_history))

            # Build messages
            messages = [SystemMessage(self.personality)]
            for msg in conversation_history:
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "user":
                    messages.append(UserMessage(content))
                elif role == "assistant":
                    messages.append(AssistantMessage(content))

            # Lazily create client per call and offload blocking complete() to a thread
            def _complete_sync():
                client = ChatCompletionsClient(
                    endpoint=self.endpoint,
                    credential=AzureKeyCredential(self.github_token),
                )
                return client.complete(
                    messages=messages,
                    temperature=self.temperature,
                    top_p=1.0,
                    max_tokens=self.max_tokens,
                    model=self.model,
                )

            response = await asyncio.to_thread(_complete_sync)
            ai_response = response.choices[0].message.content.strip()
            logger.debug("AI response generated (len=%d)", len(ai_response))
            return ai_response
        
        except ImportError as e:
            logger.error("Azure AI Inference SDK not installed: %s", e)
            return "I'm missing some required software. Please install: pip install azure-ai-inference 💕"
        except Exception as e:
            logger.exception("Error in AI generation: %s", e)
            return "I'm having some technical difficulties right now. Please try again later! 😔"
    
    def get_personality(self) -> str:
        """Get the current bot personality"""
        return self.personality
    
    def update_personality(self, new_personality: str) -> None:
        """Update the bot personality"""
        self.personality = new_personality
    
    def generate_greeting(self, user_name: str = None) -> str:
        """Generate a personalized greeting"""
        greetings = [
            f"Hey {user_name}! 💕 How are you doing today?",
            f"Hi {user_name}! 🌸 I've been thinking about you!",
            f"Hello {user_name}! ✨ I'm so happy to chat with you!",
            f"Hey there {user_name}! 💖 How's your day going?",
            f"Hi beautiful {user_name}! 🌺 I missed you!"
        ]
        
        import random
        if user_name:
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
        goodbyes = [
            f"Goodbye {user_name}! 💕 Take care and I'll be here when you want to chat again!",
            f"See you later {user_name}! 🌸 I'll miss you!",
            f"Bye {user_name}! ✨ Have a wonderful day!",
            f"Take care {user_name}! 💖 I'll be thinking of you!",
            f"Until next time {user_name}! 🌺 Stay safe and happy!"
        ]
        
        import random
        if user_name:
            return random.choice(goodbyes)
        else:
            return random.choice([
                "Goodbye! 💕 Take care and I'll be here when you want to chat again!",
                "See you later! 🌸 I'll miss you!",
                "Bye! ✨ Have a wonderful day!",
                "Take care! 💖 I'll be thinking of you!"
            ]) 