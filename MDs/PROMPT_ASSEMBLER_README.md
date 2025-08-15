# PromptAssembler System

The PromptAssembler is a sophisticated system for building LLM chat prompts with integrated memory retrieval, conversation history, and token budgeting. It orchestrates the assembly of context-aware prompts by combining system templates, relevant memories, conversation history, and persona configurations while respecting token limits.

## Features

- **Memory Integration**: Automatically retrieves and includes relevant episodic memories and user profile summaries
- **Token Budgeting**: Precise token accounting using tiktoken (with fallback heuristics) to respect LLM context windows
- **Smart Truncation**: Handles long messages with intelligent truncation and tracking
- **Persona Support**: Configurable personality templates for different AI characters
- **Async Architecture**: Fully async implementation for high-performance applications
- **Comprehensive Testing**: Extensive unit tests covering edge cases and token budgeting scenarios

## Installation

```bash
# Required dependencies
pip install tiktoken  # For accurate token counting (optional but recommended)
```

## Basic Usage

### Simple Prompt Building

```python
import asyncio
from prompt.assembler import PromptAssembler
from storage.repos import PostgresMessageRepo, PostgresMemoryRepo
from memory.manager import MemoryManager

# Initialize repositories (using your existing storage system)
message_repo = PostgresMessageRepo(session_maker)
memory_repo = PostgresMemoryRepo(session_maker) 
memory_manager = MemoryManager(message_repo, memory_repo, conversation_repo, config)

# Create PromptAssembler
assembler = PromptAssembler(
    message_repo=message_repo,
    memory_manager=memory_manager,
    config={
        "max_memory_items": 3,
        "memory_token_budget_ratio": 0.4,
        "include_system_template": True
    }
)

# Build a prompt
async def build_chat_prompt():
    messages = await assembler.build_prompt(
        conversation_id="550e8400-e29b-41d4-a716-446655440000",
        current_user_message="What should I cook for dinner tonight?",
        reply_token_budget=800,  # Reserve 800 tokens for LLM response
        history_budget=5000      # Use up to 5000 tokens for context
    )
    
    # Use messages with your LLM client
    return messages

# Example output:
[
    {
        "role": "system",
        "content": "You are Cath, an AI girlfriend with access to conversation memories..."
    },
    {
        "role": "system", 
        "content": "USER PROFILE:\nUser is a friendly software engineer who loves pizza and hiking..."
    },
    {
        "role": "system",
        "content": "RELEVANT MEMORIES:\n• MEMORY [abc123 | 2024-01-15 | episodic]: User prefers Italian cuisine..."
    },
    {
        "role": "user",
        "content": "Hello, how are you?"
    },
    {
        "role": "assistant",
        "content": "I'm doing great! How can I help you today?"
    },
    {
        "role": "user",
        "content": "What should I cook for dinner tonight?"
    }
]
```

### Advanced Usage with Metadata

```python
async def build_prompt_with_metadata():
    messages, metadata = await assembler.build_prompt_and_metadata(
        conversation_id="550e8400-e29b-41d4-a716-446655440000",
        current_user_message="Tell me about healthy recipes",
        reply_token_budget=800,
        history_budget=5000
    )
    
    # Access detailed metadata
    print(f"Total tokens used: {metadata['total_tokens']}")
    print(f"Included memories: {metadata['included_memory_ids']}")
    print(f"Token breakdown: {metadata['token_counts']}")
    
    # Example metadata:
    {
        "included_memory_ids": ["mem-123", "mem-456"],
        "token_counts": {
            "system_tokens": 245,
            "memory_tokens": 156, 
            "history_tokens": 892,
            "reply_reserved": 800
        },
        "truncated_message_ids": [],
        "total_tokens": 2093,
        "conversation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
    
    return messages, metadata
```

### Custom Configuration

```python
# Advanced configuration
config = {
    # Memory settings
    "max_memory_items": 5,              # Max memories to include (capped by token budget)
    "memory_token_budget_ratio": 0.3,   # 30% of history budget for memories
    
    # Message handling
    "truncation_length": 300,           # Truncate messages longer than 600 chars
    "include_system_template": True,    # Include base system template
    
    # Custom settings
    "prefer_recent_memories": True,     # Prioritize newer memories
    "debug_token_usage": False          # Log detailed token usage
}

assembler = PromptAssembler(
    message_repo=message_repo,
    memory_manager=memory_manager,
    persona_repo=persona_repo,  # Optional persona support
    tokenizer=custom_tokenizer, # Optional custom tokenizer
    config=config
)
```

### Using with Custom Tokenizer

```python
import tiktoken

# Using tiktoken directly
encoding = tiktoken.get_encoding("cl100k_base")

class TiktokenWrapper:
    def __init__(self, encoding):
        self._encoding = encoding
    
    def count_tokens(self, text: str) -> int:
        return len(self._encoding.encode(text))

custom_tokenizer = TiktokenWrapper(encoding)

assembler = PromptAssembler(
    message_repo=message_repo,
    memory_manager=memory_manager,
    tokenizer=custom_tokenizer,  # More accurate token counting
    config=config
)
```

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `max_memory_items` | int | 3 | Maximum number of memory items to include |
| `memory_token_budget_ratio` | float | 0.4 | Fraction of history budget allocated to memories |
| `truncation_length` | int | 200 | Character length threshold for message truncation |
| `include_system_template` | bool | True | Whether to include the base system template |
| `prefer_recent_memories` | bool | False | Prioritize newer memories over relevance score |
| `debug_token_usage` | bool | False | Enable detailed token usage logging |

## Token Budgeting

The system uses a sophisticated token budgeting approach:

1. **Reply Budget**: Reserved tokens for the LLM's response (default: 800)
2. **History Budget**: Available tokens for context (default: 5000)
3. **Memory Budget**: Calculated as `history_budget * memory_token_budget_ratio`
4. **Remaining Budget**: Used for conversation history after memory allocation

### Budget Flow:
```
Total Context Window (e.g., 20,000 tokens)
├── System Template (~200-400 tokens)
├── User Profile (~100-300 tokens) 
├── Memory Context (~30-40% of history budget)
├── Conversation History (~60-70% of history budget)
└── Reply Reserved (~800 tokens)
```

## Memory Integration

The system integrates with the existing MemoryManager:

- **Episodic Memories**: Retrieved based on semantic similarity to current message
- **Summary Memories**: User profile/conversation summary included as system context
- **Token-Aware**: Memories are included until token budget is exhausted
- **Metadata Tracking**: All included memory IDs are tracked for auditing

## Error Handling

The system gracefully handles various error scenarios:

- **Invalid UUIDs**: Raises `ValueError` with clear message
- **Repository Errors**: Logs warnings and continues with available data
- **Empty Inputs**: Validates and raises appropriate exceptions
- **Token Overflow**: Prioritizes recent/important content within budget

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
pytest tests/test_prompt_assembler.py -v

# Run specific test categories
pytest tests/test_prompt_assembler.py::TestPromptAssembler::test_build_prompt_basic -v
pytest tests/test_prompt_assembler.py::TestTokenCounter -v

# Run with coverage
pytest tests/test_prompt_assembler.py --cov=prompt --cov-report=html
```

## Performance Considerations

- **Memory Retrieval**: Limited to top-k memories to avoid expensive full-corpus search
- **Token Counting**: Uses tiktoken when available for accuracy, falls back to heuristic
- **Async Operations**: All database operations are async for better concurrency
- **Caching**: Consider implementing memory caching for frequently accessed conversations

## Integration Example

```python
# Full integration with your LLM handler
class LLMHandler:
    def __init__(self, prompt_assembler):
        self.assembler = prompt_assembler
    
    async def generate_response(self, conversation_id: str, user_message: str):
        # Build context-aware prompt
        messages, metadata = await self.assembler.build_prompt_and_metadata(
            conversation_id=conversation_id,
            current_user_message=user_message
        )
        
        # Log token usage for monitoring
        logger.info(f"Prompt built: {metadata['total_tokens']} tokens, "
                   f"{len(metadata['included_memory_ids'])} memories")
        
        # Send to LLM API
        response = await self.llm_client.chat_completion(
            messages=messages,
            max_tokens=metadata['token_counts']['reply_reserved']
        )
        
        return response, metadata
```

## Best Practices

1. **Token Budgeting**: Monitor token usage and adjust budgets based on your LLM's context window
2. **Memory Management**: Regularly update conversation summaries for better context
3. **Error Handling**: Always handle potential repository errors gracefully
4. **Testing**: Use the provided test suite to validate your configuration
5. **Monitoring**: Track memory inclusion rates and token usage for optimization

## Troubleshooting

### Common Issues:

**Q: Memories not being included**
- Check `memory_token_budget_ratio` - may be too low
- Verify MemoryManager is properly configured and has memories stored
- Check similarity threshold in memory retrieval

**Q: Token count seems inaccurate**
- Install tiktoken for accurate counting: `pip install tiktoken`
- Verify your tokenizer matches your LLM's tokenizer

**Q: Messages being truncated unexpectedly**
- Adjust `truncation_length` configuration
- Check token budgets - may be too restrictive

**Q: System template not appearing**
- Verify `include_system_template: True` in configuration
- Check if persona configuration is overriding system template