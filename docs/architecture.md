graph TD
    subgraph "Взаимодействие с пользователем"
        User["Пользователь"] -- "Отправляет сообщение" --> TelegramAPI["API Телеграма"]
    end

    subgraph "Внешние сервисы"
        LLMServer["Сервер нейросети<br>Azure / LM Studio"]
    end

    subgraph "Обработка входящих сообщений"
        TelegramAPI -- "Получение сообщения" --> A["bot.py - Главный обработчик<br>Принимает команды и сообщения"]
        A -- "handle_message" --> B["BufferManager<br>Группирует быстрые сообщения в одно"]
        B -- "schedule_dispatch" --> C{"bot.py - _dispatch_buffered_message<br>Отправляет собранное сообщение на обработку"}
    end

    subgraph "Хранилище данных"
        Postgres[("База данных PostgreSQL<br>- Диалоги<br>- Сообщения")]
    end

    subgraph "Логика ИИ и Сборка Промпта"
        D["ai_handler.py - AIHandler<br>Главный мозг, управляет ИИ"]
        E["prompt/assembler.py - PromptAssembler<br>Составляет запрос для нейросети<br>из истории диалога"]
        G["ModelClient<br>Клиент для нейросети"]
    end

    %% --- Связи между модулями ---
    C -- "1. Сохраняет сообщение" --> Postgres
    C -- "2. Запускает генерацию ответа" --> D

    D -- "1. Собирает промпт" --> E
    D -- "2. Передает промпт клиенту" --> G
    
    G -- "API запрос" --> LLMServer
    LLMServer -- "Результат" --> G
    G -- "Возвращает ответ" --> D

    E -- "Берет историю диалога" --> Postgres

    subgraph "Отправка ответа пользователю"
        Redis["Очередь Redis<br>MessageQueueManager"]
        H["message_manager.py - MessageDispatcher<br>Достает ответы из очереди"]
        
        D -- "3. Ставит ответ в очередь" --> Redis
        Redis -- "1. Диспетчер забирает сообщение" --> H
        H -- "2. Отправляет в Telegram" --> TelegramAPI
    end

    subgraph "Фоновые службы"
        ProactiveTask["proactive_messaging.py<br>Отправляет сообщения по расписанию"]
        Celery["Celery Beat<br>Планировщик"] -- "Запускает задачу" --> ProactiveTask
        ProactiveTask -- "Ставит сообщение в очередь" --> Redis
    end

    style B fill:#f9f,stroke:#333,stroke-width:2px
    style H fill:#ccf,stroke:#333,stroke-width:2px
