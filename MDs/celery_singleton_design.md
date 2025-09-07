# Celery Singleton Pattern Design for Proactive Messaging System

## Current Issues Analysis

After analyzing the current implementation, I've identified several key issues:

1. **Multiple Celery App Instances**: The `celery_app` is created as a module-level instance in `proactive_messaging.py`, but there's potential for duplication in tests and other modules.

2. **Component Duplication**: In the `send_proactive_message` Celery task, new instances of components are created on every task execution:
   - `AIHandler()` 
   - `TypingIndicatorManager()`
   - `PostgresConversationManager()`
   - Memory components (`MemoryManager`, `PromptAssembler`)

3. **Inefficient Memory Component Imports**: Memory components are imported inside the task function rather than at the module level or during initialization.

4. **Initialization During Task Execution**: Components that should be initialized at startup are instead created during task execution, causing unnecessary overhead.

5. **No Consistent State Management**: Each task creates its own instances, leading to inconsistent state across tasks.

## Proposed Solution: CelerySingleton Class

I propose creating a `CelerySingleton` class that manages all Celery-related components as singletons, ensuring:

1. Single instance of Celery app across the application
2. Centralized component management
3. Proper initialization at startup
4. Consistent state across worker processes
5. Efficient memory component handling

## Design Overview

### Class Structure

```python
class CelerySingleton:
    _instance = None
    _lock = threading.Lock()
    
    # Core components
    celery_app: Celery
    proactive_service: ProactiveMessagingService
    
    # Shared components
    ai_handler: AIHandler
    typing_manager: TypingIndicatorManager
    conversation_manager: PostgresConversationManager
    
    # Memory components (optional)
    memory_manager: Optional[MemoryManager]
    prompt_assembler: Optional[PromptAssembler]
    
    def __new__(cls):
        # Thread-safe singleton implementation
        pass
        
    @classmethod
    def get_instance(cls) -> 'CelerySingleton':
        # Get singleton instance
        pass
        
    def initialize_components(self):
        # Initialize all components at startup
        pass
        
    def get_celery_app(self) -> Celery:
        # Get Celery app instance
        pass
        
    def get_proactive_service(self) -> ProactiveMessagingService:
        # Get proactive messaging service
        pass
        
    # Similar getters for other components...
```

### Key Design Principles

1. **Thread-Safe Singleton**: Using double-checked locking pattern for thread safety
2. **Lazy Initialization**: Components are initialized only when needed
3. **Startup Initialization**: Critical components are initialized at application startup
4. **Distributed Locking**: For multi-worker environments, use Redis-based locking
5. **Graceful Degradation**: Memory components are optional and won't break the system if unavailable

## Implementation Plan

### 1. CelerySingleton Class Implementation

The `CelerySingleton` class will manage:

- Celery app instance
- Proactive messaging service
- Shared AI components (AIHandler, TypingIndicatorManager, PostgresConversationManager)
- Memory components (MemoryManager, PromptAssembler) - if available

### 2. Initialization Flow

```
Application Startup
    ↓
Celery Worker Ready Signal
    ↓
CelerySingleton.initialize_components()
    ↓
Component Initialization (with distributed locking)
    ↓
Register Celery Tasks
    ↓
Ready for Task Execution
```

### 3. Component Lifecycle

- **At Startup**: Initialize shared components
- **During Tasks**: Reuse existing component instances
- **Error Handling**: Graceful recovery from component failures
- **Cleanup**: Proper resource cleanup when shutting down

## Distributed Locking Mechanism

For multi-worker environments, we'll implement a Redis-based distributed lock:

```python
class DistributedLock:
    def __init__(self, redis_client, lock_key, timeout=30):
        self.redis_client = redis_client
        self.lock_key = f"celery_singleton_init:{lock_key}"
        self.timeout = timeout
        self.identifier = str(uuid.uuid4())
        
    def acquire(self) -> bool:
        # Acquire lock with timeout
        pass
        
    def release(self):
        # Release lock
        pass
        
    def __enter__(self):
        # Context manager implementation
        pass
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Context manager cleanup
        pass
```

This ensures only one worker process initializes the components, while others wait.

## Memory Component Optimization

Instead of importing memory components inside tasks, we'll:

1. Try to import at module level
2. Set flags for availability
3. Initialize only if imports succeed
4. Reuse instances across tasks

## Benefits of This Approach

1. **Performance**: Eliminates redundant component creation
2. **Consistency**: Ensures consistent state across tasks
3. **Resource Efficiency**: Reduces memory and CPU usage
4. **Maintainability**: Centralized component management
5. **Scalability**: Works well in multi-worker environments
6. **Reliability**: Proper error handling and graceful degradation

## Implementation Steps

1. Create `CelerySingleton` class with thread-safe singleton pattern
2. Implement distributed locking mechanism
3. Move component initialization to startup
4. Refactor `proactive_messaging.py` to use singleton
5. Update tests to work with new architecture
6. Add proper error handling and logging
7. Document the new architecture

This design will address all the identified issues while maintaining backward compatibility and ensuring robust operation in distributed environments.