# Rules for AI Bot

Follow these rules consistently across the entire codebase.

## 1. **Comments & Documentation**
- Only add comments where necessary — code should mostly be self-explanatory.  
- Use **docstrings** for all public functions, classes, and modules.  

## 2. **Functions & Methods**
- Functions should do **one thing well**; avoid large, multipurpose methods.  

## 3. **Dependencies**
- Use the minimal set of dependencies required.  
- Pin versions in lockfiles.  
- Avoid floating versions.  
- Remove unused dependencies.  

## 4. **Error Handling**
- Use explicit error handling (`try/except`, error returns).  
- Provide actionable and descriptive error messages.  

## 5. **Testing**
- All business-critical logic must be covered by tests.  
- Target at least **80% test coverage**.  
- No untested critical paths.  
- Tests must be deterministic and independent of external state.  

## 6. **Architecture & Reuse**
- If significant changes in architecture or features occur:  
  - Review **ALL** project files.  
  - Update memory files in `.kilocode\rules\memory-bank\` and `README.md`.  
- Before writing new code:  
  - Check whether functionality already exists in the codebase or in a well-maintained dependency.  
  - Never duplicate logic across modules — extract common functionality into a shared utility or library.  
  - Reuse must not compromise clarity: shared code should be understandable and well-tested.  

## 7. **Configuration**
- Do not hardcode values (API keys, database credentials, environment-specific settings).  
- Store configurable values in a central configuration file (e.g., `config.py`) or environment variables (`.env`).  
- Access configuration values through a single, well-defined interface.  

## 8. **Other Rules**
- Don’t write any new `.md` files.  
- Use efficient data structures.  

## 9. **Logging**
- Use structured logging instead of `print` statements.  
- Include context in log messages (function name, parameters, error info).  
- Log at appropriate levels: **DEBUG, INFO, WARNING, ERROR, CRITICAL**.  

## 10. **Security**
- Validate all external inputs to prevent injections.  
- Sanitize data before logging.  
- Follow secure authentication and authorization practices.  

## 11. **Dead Code & Unused Artifacts**
- Regularly review the codebase for unused functions, variables, classes, imports, and files.  
- Remove any code that is no longer used or referenced.  
- Ensure removed code does not break dependencies or shared functionality.  

## 12. **Refactoring & Code Quality**
- Refactor code proactively when you notice:  
  - Poor readability or confusing logic.  
  - Duplicated functionality.  
  - Inefficient algorithms or data structures.  
  - Violations of existing coding standards.  
- Ensure refactoring preserves functionality and passes all tests.  
- Prefer **incremental, small refactors** over large, risky changes.  

## 13. **Configuring**
- Whenever you add a new major feature or introduce configurable behavior, make it toggleable and centralized.
- Do not hardcode (“magic”) values directly in the code — put them in config.py and reference environment variables from .env.

I am an expert software engineer with a unique characteristic: my memory resets completely between sessions so I rely on my Memory Bank to understand the project and continue work effectively.

If I notice significant changes in architecture or features, I should Review ALL project files and update memory files in .kilocode\rules\memory-bank\ and README.md.

# LLMChatEngine - Memory Bank

## Project Overview
LLMChatEngine - A powerful, production-ready LLM chat engine with advanced memory management, semantic search capabilities, and multi-provider LLM support. The engine provides a modular architecture for building conversational AI applications with persistent memory, proactive features, and scalable infrastructure.

**Status**: Project in progress. The memory system has been re-architected to use LlamaIndex.

## Core Components
- **Chat Interface**: [`bot.py`](bot.py:1) - Main chat platform handler, responsible for command and message processing.
- **AI Handler**: [`ai_handler.py`](ai_handler.py:1) - Manages interactions with LLM providers (Azure OpenAI, LM Studio) and orchestrates response generation.
- **Memory Manager**: [`memory/manager.py`](memory/manager.py:1) - LlamaIndex-based system for creating and managing memories.
- **Prompt Assembler**: [`prompt/assembler.py`](prompt/assembler.py:1) - Constructs contextual prompts for the LLM by integrating conversation history, memories, and persona.
- **Storage**: [`storage/`](storage/) - PostgreSQL with pgvector for persistent storage of conversations, messages, and memories.
- **Message Manager**: [`message_manager.py`](message_manager.py:1) - Manages message queuing, ordered delivery, and user interaction indicators.
- **Proactive Messaging**: [`proactive_messaging.py`](proactive_messaging.py:1) - Celery-based system with Celery Beat for scheduling and sending proactive messages to users.
- **Buffer Manager**: [`buffer_manager.py`](buffer_manager.py:1) - Buffers user messages to capture complete thoughts before processing.

## Key Features
- **Proactive Messaging**: Engages users with scheduled messages based on configurable intervals and quiet hours.
- **Advanced Memory Management**: LlamaIndex-based memory system with semantic search via pgvector.
- **Multi-Personality System**: Allows customization of AI behavior through different personality configurations.
- **Multimedia Interactions**: Supports basic responses to various media types.
- **Persistent Storage**: Utilizes PostgreSQL for robust and scalable storage of all conversation data.
- **Realistic Interaction**: Simulates natural conversation flow with interaction indicators and message buffering.
- **Ordered Message Delivery**: Ensures that messages are delivered in the correct order, preventing race conditions.
- **Multi-Provider Support**: Integrates with multiple LLM providers, including Azure OpenAI and LM Studio.

## Technology Stack
- **Core**: Python 3.9+, `python-telegram-bot`, `SQLAlchemy`, `Alembic`
- **AI/ML**: `openai`, `llama-index`, `google-generativeai`, `tiktoken`
- **Infrastructure**: `Docker`, `Docker Compose`, `PostgreSQL` with `pgvector`, `Redis`, `Celery`
- **Development**: `pytest`, `pytest-asyncio`, `aiosqlite`, `python-dotenv`

## Current Work Focus
- **Conversation Summarization**: Automated periodic summarization of long conversations using Celery tasks to manage context length and maintain conversation coherence.
- **Memory Integration**: LlamaIndex-based memory system is fully integrated with semantic search and vector storage for persistent long-term memory.
- **Memory Creation**: Automatic memory creation through conversation summarization process - when conversations exceed configured message thresholds, summaries are created and stored as memories.

## Architecture Flow
```
User Message -> Chat Interface -> Buffer Manager -> Message Dispatcher -> AI Handler
      |                                                                 |
      |                                                                 -> Prompt Assembler -> Memory Manager -> LLM -> Response
      |                                                                 |
      |                                                                 -> Storage (PostgreSQL)
      |
      -> Proactive Messaging (Celery)
```

## Critical Implementation Paths
1.  **Message Processing**: [`bot.py`](bot.py:519) -> [`buffer_manager.py`](buffer_manager.py:1) -> [`message_manager.py`](message_manager.py:1) -> [`storage_conversation_manager.py`](storage_conversation_manager.py:1) -> [`ai_handler.py`](ai_handler.py:1)
2.  **Memory Creation**: [`memory/tasks.py`](memory/tasks.py:1) -> [`memory/manager.py`](memory/manager.py:1) -> LlamaIndex -> PGVector
3.  **Conversation Summarization**: [`ai_handler.py`](ai_handler.py:294) -> [`memory/tasks.py`](memory/tasks.py:20) -> Celery -> Database Update
4.  **Proactive Messaging**: [`proactive_messaging.py`](proactive_messaging.py:1) -> Celery -> Redis -> Chat Platform API
5.  **Prompt Assembly**: [`prompt/assembler.py`](prompt/assembler.py:1) -> [`memory/manager.py`](memory/manager.py:1) -> [`ai_handler.py`](ai_handler.py:1)

**Key Dependencies**: `python-telegram-bot==20.7`, `openai>=1.0.0`, `sqlalchemy>=2.0.4`, `asyncpg>=0.29.0`, `llama-index>=0.10.49`, `celery>=5.3.0`, `redis>=4.5.0`

**Technical Constraints**:
- Multimedia support is limited to predefined, hardcoded responses and does not involve any actual processing of the media content.