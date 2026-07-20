# LLMChatEngine

LLMChatEngine — это модульный движок Telegram-чатов для создания контекстных LLM-ассистентов с постоянным хранилищем, семантической памятью, управлением несколькими ботами и фоновой обработкой задач.

Проект построен как production-сервис на Python, а не как одиночный скрипт-бот: он использует асинхронный SQLAlchemy, PostgreSQL с pgvector, очереди на базе Redis, воркеры Celery, миграции Alembic, Docker Compose и детерминированные тесты в CI.

## Что демонстрирует проект

- Интеграцию с несколькими LLM-провайдерами: Azure OpenAI, LM Studio и Gemini.
- Семантическую память на базе LlamaIndex поверх PostgreSQL и pgvector.
- Книжные базы знаний в рамках отдельного бота для RAG под автора/персону.
- Многоботовый рантайм Telegram, управляемый центральным админ-ботом.
- Упорядоченную доставку сообщений через очереди Redis и диспетчер сообщений.
- Буферизацию сообщений для объединения быстрого ввода пользователя в связные реплики.
- Проактивные сообщения по расписанию через Celery Beat и очереди воркеров.
- Суммаризацию диалогов для длинных чатов и контроля контекста.
- Развёртывание в Docker с PostgreSQL, Redis, воркерами Celery и сервисом резервного копирования.
- Асинхронный слой репозиториев с точечными тестами для хранилища, памяти, промптов и потока сообщений.

## Архитектура

```text
Сообщение пользователя
  -> TelegramChatBot
  -> BufferManager
  -> StorageConversationManager
  -> AIHandler
  -> PromptAssembler
  -> MemoryManager / PostgreSQL + pgvector
  -> LLM-провайдер
  -> MessageQueueManager / Redis
  -> MessageDispatcher
  -> Telegram API
```

В репозитории также есть диаграмма архитектуры [docs/architecture.png](docs/architecture.png) и исходный Mermaid-файл [docs/architecture.md](docs/architecture.md).

Правила идентификации пользователя описаны в [docs/user-identity.md](docs/user-identity.md). Рантайм-код использует «сырые» целочисленные Telegram ID на границах; внутренние UUID остаются внутри репозиториев хранилища и реляционных строк.

## Основные компоненты

- `bot.py`: рантайм и обработчики команд со стороны Telegram.
- `ai_handler.py`: оркестрация LLM-провайдеров, ретраи и генерация ответов.
- `memory/manager.py`: менеджер памяти на LlamaIndex и семантический поиск.
- `knowledge/`: разбор книг, чанкинг, векторное хранилище, задачи ингеста и поиск.
- `prompt/assembler.py`: сборка промпта с историей, суммаризациями и бюджетированием памяти.
- `storage/`: модели SQLAlchemy, интерфейсы репозиториев и реализация персистентности.
- `messaging/`: постановка в очередь Redis, упорядоченная диспетчеризация, индикаторы набора текста и ретраи доставки.
- `buffer_manager.py`: буферизация сообщений пользователя и адаптивный тайминг отправки.
- `proactive_messaging.py`: проактивная рассылка на базе Celery.
- `admin_bot.py` и `bot_manager.py`: администрирование нескольких ботов и управление рантаймом.

## Быстрый старт

### Требования

- Python 3.11+
- Docker Engine 20.10+
- Docker Compose v2+
- Токен Telegram-бота
- Учётные данные LLM-провайдера или доступный сервер LM Studio

### Настройка

```bash
git clone https://github.com/NickZaitsev/LLMChatEngine.git
cd LLMChatEngine
cp env_example.txt .env
```

Отредактируйте `.env`, указав настройки базы данных, Telegram и провайдера:

```env
DB_PASSWORD=your_secure_password_here
USE_PGVECTOR=true

ADMIN_BOT_TOKEN=your_admin_bot_token_here
ADMIN_USER_IDS=123456789
TOKEN_ENCRYPTION_KEY=your_fernet_key_here

PROVIDER=lmstudio
LMSTUDIO_MODEL=your_model
LMSTUDIO_BASE_URL=http://host-machine:1234/v1
```

Внутри Docker Compose строка подключения `DATABASE_URL` собирается автоматически из `DB_PASSWORD` и указывает на сервис `postgres`; отдельно её задавать не нужно. Для Azure или Gemini установите `PROVIDER=azure` или `PROVIDER=gemini` и заполните соответствующие ключи из `env_example.txt`.

### Запуск

```bash
docker compose up --build -d
docker compose logs -f llm-chat-engine
```

Стек запускает:

- Основной движок Telegram-чата.
- PostgreSQL с pgvector.
- Redis.
- Одноразовый сервис миграций (`migrate`), выполняющий `alembic upgrade head` до старта остальных сервисов.
- Воркер Celery для проактивных сообщений.
- Планировщик Celery Beat.
- Воркер Celery для задач памяти.
- Сервис резервного копирования PostgreSQL.

Остановить стек:

```bash
docker compose down
```

> Тома и сеть Compose закреплены под именами с префиксом `llmchatengine_` (например, `llmchatengine_postgres_data`). Они совпадают с именами, которые Compose уже создавал по умолчанию, поэтому миграция данных при обновлении не требуется.

## Настройка нескольких ботов

1. Создайте админ-бота через [@BotFather](https://t.me/BotFather).
2. Узнайте свой Telegram user ID у [@userinfobot](https://t.me/userinfobot).
3. Сгенерируйте ключ Fernet:

```python
from cryptography.fernet import Fernet

print(Fernet.generate_key().decode())
```

Добавьте значения в `.env`:

```env
ADMIN_BOT_TOKEN=your_admin_bot_token_here
ADMIN_USER_IDS=123456789,987654321
TOKEN_ENCRYPTION_KEY=your_generated_key_here
```

Команды админ-бота:

- `/addbot`: добавить управляемого Telegram-бота с собственным токеном, именем и промптом персоны.
- `/listbots`: показать управляемых ботов и их статус в рантайме.
- `/setprompt <bot_id>`: обновить промпт персоны бота.
- `/togglefeature <bot_id> <feature>`: включить/выключить функции, например `VOICE_MESSAGES` или `MEMORY`.
- `/addbook <bot_id>`: загрузить книгу `.txt`, `.pdf`, `.epub` или `.fb2` для этого бота.
- `/listbooks <bot_id>`: показать статус ингеста и число чанков книг бота.
- `/removebook <book_id>`: удалить книгу и её векторные чанки.
- `/removebot <bot_id>`: остановить и удалить управляемого бота.

## Книги персон-авторов

Чтобы «заземлить» бота-персону на книгах автора:

1. Создайте бота-персону через `/addbot` с сильным системным промптом в стиле автора.
2. Включите книжный поиск: `/togglefeature <bot_id> book_knowledge`.
3. Загрузите каждую книгу через `/addbook <bot_id>`.
4. Проверьте готовность через `/listbooks <bot_id>`.

Файлы книг хранятся в `BOOKS_STORAGE_DIR` до завершения ингеста. В Docker этот путь смонтирован на общий том `book_files`, чтобы и админ-бот, и воркер памяти Celery имели доступ к загрузкам.

Полное руководство (пример промпта персоны, поддерживаемые форматы, статусы ингеста, диагностика, замечания об авторском праве и размерности эмбеддингов) — в [docs/persona-bots.md](docs/persona-bots.md).

## Резервное копирование и восстановление

Сервис `postgres-backup` ежедневно в 02:00 создаёт сжатый дамп в общий том `backups`, проверяет его целостность через `gzip -t` и обновляет файл-маркер `last_success`. Health-check контейнера считается здоровым, только если существует проверенный бэкап не старше 26 часов. Хранятся последние 14 дней дампов.

Восстановление базы из дампа (замените имя файла на нужный):

```bash
gunzip -c backups/ai_bot_backup_YYYYMMDD_HHMMSS.sql.gz \
  | docker compose exec -T postgres psql -U ai_bot -d ai_bot
```

> Важно: расширение pgvector устанавливается init-скриптом `init-pgvector.sql` только при первом запуске на пустом каталоге данных. При восстановлении в уже существующую базу убедитесь, что расширение создано (`CREATE EXTENSION IF NOT EXISTS vector;`) до заливки дампа, либо восстанавливайте в чистый том.

## Разработка

Создайте закреплённое локальное окружение:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-lock.txt -r requirements-dev.txt
```

`requirements.txt` содержит только рантайм-зависимости (в production-образ не попадают инструменты тестирования). Средства разработки (`pytest`, `ruff`, `mypy`, `black`, `pre-commit`) устанавливаются из `requirements-dev.txt`.

Запуск детерминированного набора тестов по умолчанию:

```powershell
.\.venv\Scripts\python -m pytest -q
```

Запуск всех собираемых тестов, включая категории external/manual/performance:

```powershell
.\.venv\Scripts\python -m pytest -q -o addopts=
```

Запуск только недефолтных категорий:

```powershell
.\.venv\Scripts\python -m pytest -q -o addopts= -m "external or performance or manual"
```

Покрытие для детерминированного набора:

```powershell
.\.venv\Scripts\python -m pytest --cov=. --cov-report=term-missing
```

Проверки качества кода:

```powershell
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy messaging --ignore-missing-imports
.\.venv\Scripts\pre-commit run --all-files
```

## Стратегия тестирования

Команда `pytest` по умолчанию исключает тесты с маркерами:

- `external`: требуют сервисов вроде LM Studio, Redis, PostgreSQL или Telegram.
- `performance`: бенчмарки или нагрузочные проверки.
- `manual`: проверки в стиле скриптов.

Это сохраняет детерминированность CI, оставляя более глубокие локальные команды для разработки и проверки развёртывания.

## Замечания по безопасности

- `.env` и локальное состояние рантайма игнорируются Git.
- Токены управляемых ботов шифруются перед сохранением ключом `TOKEN_ENCRYPTION_KEY`.
- `TOKEN_ENCRYPTION_KEY` должен быть сгенерированным ключом Fernet, а не человекочитаемой парольной фразой.
- Каждый контейнер получает только необходимые ему переменные окружения; секреты не выгружаются в контейнеры целым файлом `.env`.
- Не коммитьте локальные файлы базы данных, состояние Celery, состояние Redis, дампы эмбеддингов и учётные данные провайдеров.

## Лицензия

Проект распространяется под лицензией MIT. См. [LICENSE](LICENSE).
