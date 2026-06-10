# Master Plan: Codebase Refactoring + Author-Persona Bots with Book-Based RAG

Audience: implementation agent (Codex). This document merges two workstreams into one ordered plan:

- **Part 1 — Refactoring**: real bugs (P0), dead code (P1), architecture (P2), async/runtime hygiene (P3), decomposition & logging (P4).
- **Part 2 — Book RAG feature**: persona bots (e.g. "Friedrich Nietzsche") whose replies are grounded in the author's books, with book upload/management in the admin bot.

Part 2 deliberately depends on several Part 1 items (shared token counter, embedding-model factory, `BotRepo`), so follow the **Unified Execution Order** at the end — refactoring steps 1–4 land before the feature, the riskiest refactoring (composition root, schema migrations) lands after.

Ground rules for every step:
- Run the test suite (`!pytests.bat` / `pytest`) before starting and after every step — it must stay green.
- Do not mix behavior fixes with code moves in one commit.
- Each item below lists problem, evidence (file:line), fix, and acceptance criteria.

---

# Part 1 — Refactoring

## P0 — Behavior bugs (small, isolated diffs, fix first)

### 0.1 `temperature` / `max_tokens` are never sent to the LLM
`AIHandler` stores `self.temperature` / `self.max_tokens` (`ai_handler.py:232-233`) and `apply_llm_config` updates them (`ai_handler.py:497-500`), but `ModelClient.ask` calls
`self.client.chat.completions.create(model=..., messages=messages)` with **no generation parameters** (`ai_handler.py:174-177`); the Gemini path likewise calls `generate_content(gemini_messages)` with no `generation_config` (`ai_handler.py:171`). Per-bot `llm_config.temperature` / `max_tokens` is a silent no-op.

**Fix:** pass `temperature` and `max_tokens` through `ask(messages, temperature=..., max_tokens=...)` for OpenAI/Azure/LM Studio, and `genai.types.GenerationConfig(temperature=..., max_output_tokens=...)` for Gemini. `AIHandler._make_ai_request` forwards its current values.
**Accept:** unit test with a fake client asserting the params arrive; a bot with `llm_config={"temperature": 0.2}` sends 0.2.

### 0.2 `/personality` switch changes personality for ALL users of the bot
`handle_callback_query` does `self.ai_handler.update_personality(...)` (`bot.py:624`), which mutates the bot-instance-wide personality (and `prompt_assembler.personality`). Any user tapping a button changes how the bot talks to every other user.

**Fix (pick one, smallest first):** store the choice in `UserBotSettings.settings["personality_override"]` (table and repo already exist: `storage/models.py:170`, `storage/repos.py:1352`) and have `PromptAssembler` prefer a per-user override when building the system message; or remove the `/personality` feature until per-user support exists. Do **not** keep the global mutation.
**Accept:** test: two users, one switches personality, the other's prompt is unchanged.

### 0.3 Sync Redis calls block the event loop; one user's delays block everyone
All Redis usage in async code is the **sync** `redis` client: `MessageQueueManager` (`message_manager.py:183`), `MessageDispatcher` (`message_manager.py:360`), proactive service (`proactive_messaging.py:78`). Worst case: `blpop([queue_key], timeout=1)` inside `process_user_queue` (`message_manager.py:690`) freezes the entire event loop — all bots in the process — for up to 1 s per empty poll. Additionally the dispatcher iterates active users **sequentially** (`message_manager.py:609-636`), and `send_ai_response` sleeps a humanized typing delay per part (`message_manager.py:939-954`), so one user's multi-part reply with delays stalls delivery for every other user.

**Fix:** migrate the three classes to `redis.asyncio` (same API, `await` calls); in the dispatcher process each active user as its own task (`asyncio.gather` with a bounded semaphore, e.g. 20) so per-user ordering is preserved but users are concurrent.
**Accept:** existing dispatcher/queue tests pass; new test: two users enqueued, slow send for user A does not delay user B (use fake clock or small delays).

### 0.4 New `telegram.Bot` instance created per message part
`MessageDispatcher.process_message` builds `Bot(token=bot_token)` for every part (`message_manager.py:828`) — a fresh HTTPX connection pool per message. Also `MessageDispatcher.__init__` unconditionally creates `Bot(token=TELEGRAM_TOKEN)` (`message_manager.py:370`), which breaks when `TELEGRAM_TOKEN` is unset in pure multibot deployments.

**Fix:** add an LRU cache `{bot_token -> Bot}` in the dispatcher (bounded, e.g. 50); create the default `Bot` lazily only when a message has no `bot_token`.
**Accept:** test asserting the same `Bot` object is reused for consecutive messages with the same token; dispatcher constructible with `TELEGRAM_TOKEN=''`.

### 0.5 Nested timeout kills the inner retry logic
`generate_ai_response` wraps `ai_handler.generate_response(...)` in `asyncio.wait_for(..., timeout=REQUEST_TIMEOUT)` (`message_manager.py:1005-1011`), while `AIHandler.generate_response` internally runs up to 3 attempts each with `request_timeout=360s` and exponential backoff (`ai_handler.py:346-419`). The outer timeout cancels the whole retry loop, so retries effectively never happen unless `REQUEST_TIMEOUT > 3 × 360s`.

**Fix:** one owner of timeout+retry — keep it in `AIHandler` (it has the retry classification) and delete the outer `wait_for`; `generate_ai_response` keeps only typing-indicator management. Validate at startup that config values are coherent.
**Accept:** test with a fake client failing once with a retryable error: the retry actually executes and succeeds.

### 0.6 Silent `return None` from `generate_response`
The final `except` in `AIHandler.generate_response` logs and falls off the end of the function (`ai_handler.py:423-425`), implicitly returning `None`; `ModelClient` absence returns `""` (`ai_handler.py:274`). Callers must guess between `None`/`""`/text, and the user gets nothing with no feedback.

**Fix:** make the contract explicit: return `Optional[str]` documented as "None = generation failed", or raise a dedicated `AIGenerationError` and let `_generate_and_send_response` (`bot.py:190-192`) decide on a user-facing fallback message. Remove the dead commented `_get_error_response` block (`ai_handler.py:428-445`) as part of this.
**Accept:** simulated provider failure produces a logged error and a deliberate user-facing message (or deliberate silence — one documented behavior, not an accident).

### 0.7 Wrong validation: `chat_id` must allow negative values
`enqueue_message` rejects `chat_id <= 0` (`message_manager.py:235`), and `process_message` repeats it (`message_manager.py:802`). Telegram group/supergroup chat ids are negative; this hard-blocks any future group support and is duplicated validation anyway.

**Fix:** validate only `isinstance(chat_id, int)`; keep validation in one place (enqueue side).

### 0.8 Naive vs aware datetimes mixed
`_disable_proactive_messaging_for_user` uses `datetime.now()` (`message_manager.py:906,916`) while enqueue uses `datetime.now(timezone.utc)` (`message_manager.py:264`); proactive_messaging mixes both throughout. Comparisons between stored ISO strings can be off by the server's UTC offset.

**Fix:** `datetime.now(timezone.utc)` everywhere a timestamp is stored or compared; grep `datetime.now()` and fix all hits in non-test code.

---

## P1 — Dead code and duplication (deletions, no behavior change)

### 1.1 Remove the orphaned `PostgresMemoryRepo` subsystem
The `memories` table was **dropped** by migration `20251025_1505_87cdcd5520f9_drop_memories_table.py`, yet all of this still exists:
- `Memory` model (`storage/models.py:581-664`) — dangerous: any `Base.metadata.create_all` (used for SQLite in `storage/__init__.py:171-174`) or future Alembic autogenerate resurrects the table;
- `PostgresMemoryRepo` with a JSON-file embedding fallback writing `memories_embeddings.json` into the repo root (`storage/repos.py:638-910`, `storage/repos.py:651`);
- `Storage.memories` wiring (`storage/__init__.py:50,179`), interfaces (`storage/interfaces.py:171-175`), `tests/test_memory_repo.py`, and the committed `memories_embeddings.json` file.

**Fix:** delete model, repo, interface methods, Storage field, tests, and the JSON artifact. Real memory lives in the LlamaIndex pgvector table — untouched.
**Accept:** suite green; `grep -r "PostgresMemoryRepo\|store_memory\|memories_embeddings"` only hits git history.

### 1.2 Remove sync wrappers from `PostgresConversationManager`
`add_message`, `get_conversation`, `clear_conversation`, `get_formatted_conversation`, `get_user_stats`, `debug_conversation_state`, `get_conversation_summary` are `asyncio.run`/`get_event_loop` shims (`storage_conversation_manager.py:193-209, 256-275, 307-318, 357-375, 409-427, 472-476, 502-538`). All production callers use the `*_async` variants. While here, collapse the duplicate layer `get_X_async() -> _get_X_async()` into single public async methods.
**Accept:** grep shows no callers of removed methods; suite green.

### 1.3 Deduplicate small copy-paste utilities  *(prerequisite for Part 2)*
- `BotConfig` dataclass defined twice: `multibot_adapter.py:20-29` and `bot_manager.py:24-33` → one definition in a shared module (e.g. `core/bot_config.py`).
- `_mask_db_url` defined three times: `bot.py:67-79`, `storage_conversation_manager.py:595-607`, `storage/__init__.py:212-232` → one `core/utils.py:mask_db_url`.
- Token counting duplicated: `TokenCounter` + tiktoken wrapper (`prompt/assembler.py:35-94`) and `TokenEstimator` (`storage/repos.py:49-93`) → one **`core/tokens.py`** used by both. The book chunker in Part 2 §B.3 imports from here.
- Embedding-provider selection if/elif duplicated: `bot.py:887-895` and `app_context.py:140-151` → one factory **`memory/embedding_factory.py:build_embedding_model()`**. Part 2 (book ingestion and retrieval) uses this factory as its only way to obtain an embedding model.

### 1.4 Delete dead code
- `self.user_states = {}` — written once, never read (`bot.py:107`).
- Commented-out blocks: `_get_error_response` (`ai_handler.py:428-445`), error_handler reply block (`bot.py:838-849`), commented UUID validation (`prompt/assembler.py:219-224`).
- Duplicate import `from llama_index.llms.lmstudio import LMStudio` twice in `app_context.py` (lines 16 and 29); it is never used there — delete both. Same import in `bot.py:55` is also unused.
- `enqueue_message` back-compat params `bot`, `typing_manager` that lead to a no-op `pass` (`message_manager.py:215, 285-290`) — remove params and update callers.
- `AIHandler.get_response` builds a prompt with `conversation_id=user_id` (`ai_handler.py:257-263`) — a misuse; the only production caller (`memory/tasks.py:128`) passes no `user_id`, so the branch is dead. Remove the `user_id` parameter and branch.
- The `isinstance(route_key, int)` legacy shim in `_dispatch_buffered_message` (`bot.py:758-759`).

### 1.5 Resolve the Persona placeholder subsystem
`Conversation.persona_id` is `NOT NULL` (`storage/models.py:312-317`), forcing `_ensure_user_and_conversation` to fabricate a "Default Assistant" persona per user (`storage_conversation_manager.py:107-116`). Persona `config` is never read during prompt assembly — personality comes from `Bot.personality`. This is schema noise and a misleading concept next to `Bot`.

**Fix (conservative):** migration making `conversations.persona_id` nullable; stop auto-creating personas; keep the `personas` table for future use but remove `persona_repo` from `PromptAssembler.__init__` (it never uses it — `prompt/assembler.py:114`).
**Accept:** new conversations have `persona_id = NULL`; no persona rows created on first contact.

### 1.6 Investigate, then likely remove `messages_user`
Every message is written **three** times: `messages` (source of truth), `messages_log` (analytics), `messages_user` (`storage_conversation_manager.py:239-250` → `save_message` writes both history tables, `storage/repos.py:502-565`). `messages_user.get_user_history` has no production caller (only the unused `PostgresConversationManager.get_user_history`).

**Fix:** confirm with grep, then drop the `messages_user` table (migration), `MessageUser` model, and halve `save_message`. Keep `messages_log` if analytics value is real; otherwise flag it to the owner before dropping.

---

## P2 — Architecture

### 2.1 Replace config monkey-patching with constructor injection
`create_bot_with_config` temporarily mutates module globals `config.TELEGRAM_TOKEN/BOT_NAME/BOT_PERSONALITY`, constructs `TelegramChatBot()`, then restores them (`multibot_adapter.py:59-92`). This is fragile (any concurrent/async construction reads wrong values), and it only works because `TelegramChatBot.__init__` reads globals.

**Fix:** `TelegramChatBot.__init__(self, bot_config: Optional[BotConfig] = None)`; read token/name/personality from the argument, fall back to config for single-bot mode. Delete the patching from `multibot_adapter`; `build_application_for_bot`'s manual handler list (`multibot_adapter.py:110-140`) should be replaced by extracting handler registration from `bot.py:run()` into a reusable `register_handlers(app, bot)` used by both paths (today the two lists already diverge: multibot registers `/stop` and `/deps`, single-bot does not).
**Accept:** no writes to `config.*` anywhere outside config.py; both single- and multi-bot paths register identical handlers.

### 2.2 One composition root; share heavy resources across bots
Each `TelegramChatBot` builds its own `PostgresConversationManager` (own engine + pool of 10+20), `MessageQueueManager`, `BufferManager`, `MessageDispatcher`, `AIHandler`, plus its own `PgVectorStore` and embedding model (`bot.py:89-145, 876-902`). N bots = N DB pools, N Redis clients — and `bot_manager` additionally creates a shared dispatcher (`bot_manager.py:118-124`), so per-bot dispatchers in `bot.py:134-142` are redundant in multibot mode. Meanwhile `AppContext` (`app_context.py`) duplicates this entire wiring for Celery.

**Fix:** introduce a `ServiceContainer` (can evolve from `AppContext`) that owns: storage/engine, conversation manager, memory manager, embedding model, vector store, queue manager, typing manager, dispatcher — and, once Part 2 lands, the `BookKnowledgeManager`. `TelegramChatBot` receives the container plus its per-bot bits (token, personality, llm_config → its own `AIHandler`/`PromptAssembler`). `bot.py` keeps only Telegram handlers. Single-bot mode builds the container then one bot; `bot_manager` builds it once for all bots; Celery uses the same container.
**Accept:** with 3 bots running, exactly one DB engine and one Redis client per process; wiring code exists in exactly one module.

### 2.3 Add a `BotRepo`; stop inline SQL against the `bots` table  *(prerequisite for Part 2 admin commands)*
Raw `select(Bot)` with session boilerplate is copy-pasted in: `admin_bot.py` (6 sites: 208-220, 279-281, 328-330, 373-383, 442-460, 495-497, 536-562, 625-634), `bot_manager.py:78-82, 305-309`, `prompt/assembler.py:246-260`, `app_context.py:257-264`.

**Fix:** `storage/repos.py: PostgresBotRepo` with `create`, `get`, `list(active_only=False)`, `update_personality`, `update_flags`, `set_active`, `get_personality_and_flags`; add to `Storage`. Rewrite all call sites. Admin bot shrinks substantially. Part 2's new admin commands (§C.3) must use this repo, never inline SQL.
**Accept:** `from storage.models import Bot` appears only in `storage/` and migrations.

### 2.4 `PromptAssembler` must not query the DB for personality on every prompt
Step 2 of `build_prompt_and_metadata` runs a `select(BotModel.personality)` per request when `self.personality` is unset (`prompt/assembler.py:244-260`). It also reaches into `conversation_repo.session_maker` — a repo-abstraction leak.

**Fix:** in the bot process, `self.personality` is always set (multibot adapter does it) — keep that. For Celery, `get_ai_runtime_for_bot` already loads the Bot row (`app_context.py:257-268`); have it set `prompt_assembler.personality` there, then delete the in-assembler DB lookup. While in the file, split the 240-line `build_prompt_and_metadata` into `_resolve_personality`, `_build_memory_section`, `_build_history_section` — pure mechanical extraction (Part 2 §D.1 adds `_build_book_section` alongside these). Also fix `metadata.total_tokens` which currently includes `reply_reserved` (`prompt/assembler.py:411`), and drop the fake `included_memory_ids` (truncated text lines, not ids — `prompt/assembler.py:353-355`).
**Accept:** no SQL imports in `prompt/`; identical prompt output before/after (golden test).

### 2.5 Typed settings instead of a 300-line module of globals
`config.py` exposes ~100 module-level globals, imported piecemeal (`bot.py:12-26` imports 26 names; many files do scattered `from config import X` mid-function). Combined with 2.1's mutation this makes configuration untestable.

**Fix:** `pydantic-settings` `AppSettings` (grouped: `db`, `redis`, `llm`, `memory`, `prompts`, `proactive`, `queue`, and later `books` from Part 2), instantiated once in the composition root and injected. Keep `config.py` as a thin shim re-exporting from the settings instance during migration so the diff stays reviewable; convert `validate()` warnings into pydantic validators.
**Accept:** no mid-function `from config import X`; tests construct `AppSettings(...)` directly.

### 2.6 Unify the user identity scheme
Two encodings of the same Telegram user exist side by side: `users.username = str(telegram_id)` (`storage_conversation_manager.py:88-95`) and `uuid5(NAMESPACE_OID, f"telegram_user_{id}")` for history tables (`storage_conversation_manager.py:170, 189, 335`); vector-store metadata uses the raw telegram id string via `user.username` (`prompt/assembler.py:307-319`).

**Fix:** after 1.6 removes `messages_user`, the uuid5 scheme remains only for `messages_log` — store the raw telegram id (column rename/migration) or derive uuid5 inside the repo as an implementation detail. Document the canonical rule: "telegram_id (int) is the external id; `users.id` (UUID) is internal; nothing else."

---

## P3 — Async & runtime hygiene

### 3.1 Modernize `bot.py` startup/shutdown
`run()` uses deprecated `asyncio.get_event_loop()` + `run_until_complete`, then hands control to `run_polling` (`bot.py:1020-1034`); the `__main__` block has three nested fallback paths around cleanup (`bot.py:1080-1110`).

**Fix:** use PTB's lifecycle hooks: `Application.builder().post_init(self._on_startup).post_shutdown(self._on_shutdown)`; `_on_startup` does storage/memory/LM Studio init and starts the dispatcher task; `_on_shutdown` is the current `cleanup()`. `__main__` becomes `bot.run()` with a single `KeyboardInterrupt` handler.
**Accept:** no `get_event_loop` in bot.py; Ctrl+C performs one clean shutdown path.

### 3.2 Celery: persistent loop per worker instead of loop-change hacks
Every task calls `asyncio.run(...)` (`memory/tasks.py:72, 199`), creating and destroying a loop, which forces `AppContext` to detect loop changes and dispose engines with `dispose(close=False)`, leaking sockets by design (`app_context.py:62-117`).

**Fix:** create one long-lived event loop per worker process via the `worker_process_init` signal; tasks submit coroutines with `loop.run_until_complete` on that stable loop. Then delete `_dispose_old_resources` and the `_loop` tracking entirely. Part 2's `ingest_book_task` (§B.6) follows this same pattern.
**Accept:** AppContext has no loop-identity code; repeated task executions in one worker reuse the same engine (assert via log/id in a test).

### 3.3 `TypingIndicatorManager` unbounded growth & lock races
`_typing_locks` is never cleaned (`message_manager.py:62, 79-80`) — grows per user forever; `stop_typing` mutates `_active_typing_tasks` without holding the same lock that `start_typing` takes.

**Fix:** pop the lock in `stop_typing`; or simpler — drop the lock dict entirely and rely on single-loop discipline (document it), since all mutations happen on one event loop anyway.

### 3.4 `bot_manager` busy-wait loops
`run_bot` keeps the bot alive with `while bot_id in self.bots: await asyncio.sleep(1)` (`bot_manager.py:194-195`) and `run_all` polls every second (`bot_manager.py:345-351`). Replace with `asyncio.Event` per bot (`stop_event.wait()`) and an event-driven dispatcher-watchdog. Low risk, removes constant wakeups.

---

## P4 — Decomposition, logging, error policy

### 4.1 Split `message_manager.py` (1033 lines) into a package
```
messaging/
    formatting.py   # clean_ai_response, _split_ai_response
    typing.py       # TypingIndicatorManager
    queue.py        # MessageQueueManager
    dispatcher.py   # MessageDispatcher
    sending.py      # send_ai_response, generate_ai_response
```
Pure moves with re-exports from `message_manager.py` for one release, then delete the shim. Same treatment later for `bot.py` (1110 lines): handlers → `telegram_handlers/`, init → composition root (2.2 does most of this).

### 4.2 Logging: stop logging user content at INFO, cut noise
- User message text logged at INFO: `bot.py:660-662`, `message_manager.py:957`, prompt content `ai_handler.py:139-144` (INFO header + per-message DEBUG ok, but `logger.info("Sending request...")` per message ×4 layers).
- `memory/manager.py:145-172` and `memory/llamaindex/vector_store.py:90-112` dump every retrieved node with metadata at INFO.

**Fix:** content → DEBUG and truncated; per-request operational logs at most one INFO line per layer; node dumps → DEBUG. Privacy matters here: these are personal chats.

### 4.3 Exception policy
264 `except Exception` sites. Policy, applied to code touched in earlier phases (not a blind mass edit):
- **Boundaries keep broad catches**: Telegram handlers, Celery task entrypoints, dispatcher loop iterations — log with `exc_info=True` and continue.
- **Internal helpers must not swallow**: e.g. `_get_conversation_async` returning `[]` on any exception (`storage_conversation_manager.py:303-305`) hides DB outages as "empty history"; let it raise to the handler boundary.
- Never `except Exception: pass` (`admin_bot.py:151-152` is acceptable for message-delete; annotate it with a comment, the rest are not).

### 4.4 Canned photo/voice replies ignore the bot's persona
`handle_photo`/`handle_voice` return hardcoded girlfriend-flavored English strings with emoji (`bot.py:779-815`) regardless of `Bot.personality` — absurd for a Nietzsche persona bot (the whole point of Part 2).
**Fix:** route through the LLM as a system-role event ("user sent a photo; react in character"), or make the canned lists part of bot config; minimum viable: short neutral fallback. Product decision — flag to owner, default to the LLM route since the plumbing (`_generate_and_send_response` with `role="system"`) already exists.

### 4.5 Useless conversation cache
`_ensure_user_and_conversation` "caches" the conversation but re-fetches it from the DB on every hit anyway (`storage_conversation_manager.py:79-85`), so the cache saves nothing and adds invalidation code. Cache only the conversation **id** per `(user_id, bot_id)` and fetch the row when needed; `_user_cache` (`storage_conversation_manager.py:44`) is written but never read — delete it.

---
---

# Part 2 — Author Persona Bots with Book-Based RAG

## Goal

Allow an admin to create a persona bot (e.g. "Friedrich Nietzsche") and attach the author's books to that bot through the admin bot. At reply time the bot retrieves relevant passages from the attached books (RAG) and uses them to ground its answers, alongside the existing conversation memory.

Creating the persona itself requires **no new code** — `/addbot` with a Nietzsche personality prompt already works. What's missing is a per-bot **knowledge base**: book upload, ingestion (parse → chunk → embed → store), and retrieval injection into the prompt.

## Existing infrastructure to reuse (do not rebuild)

| Need | Already exists |
|---|---|
| Vector DB | PostgreSQL + pgvector, LlamaIndex `PGVectorStore` wrapper in `memory/llamaindex/vector_store.py` |
| Embeddings | `EmbeddingModel` abstraction (`core/abstractions.py`); after Part 1 §1.3 — the single factory `memory/embedding_factory.py` |
| Token counting | After Part 1 §1.3 — `core/tokens.py` |
| Background jobs | Celery + Redis (`memory/tasks.py`, `celeryconfig.py`); loop pattern per Part 1 §3.2 |
| Admin UI | `admin_bot.py` with `ConversationHandler` flows; DB access via `BotRepo` after Part 1 §2.3 |
| Per-bot config | `Bot` model, `feature_flags` JSON, `features.py` flag system |
| Prompt budgeting | `PromptAssembler` section builders (after Part 1 §2.4 split) |
| Migrations | Alembic, `migrations/versions/` |

The book knowledge base is intentionally **separate from conversation memory**: memory is scoped per `(user_id, bot_id)` and stores chat chunks; book knowledge is scoped per `bot_id` only (shared by all users of that bot) and is immutable reference material. Use a **separate pgvector table** (`data_book_chunks`) so the two corpora never mix and can be tuned independently.

---

## Phase A — Data Model & Storage

### A.1 New SQLAlchemy model: `Book` (in `storage/models.py`)

```python
class Book(Base):
    __tablename__ = 'books'

    id: uuid PK
    bot_id: uuid FK -> bots.id, ondelete CASCADE, nullable=False, indexed
    title: String(500), nullable=False
    author: String(255), nullable=True
    source_filename: String(500), nullable=False      # original upload name
    file_format: String(10), nullable=False           # txt | pdf | epub | fb2
    file_hash: String(64), nullable=False             # sha256 of raw file, for dedup
    status: String(20), nullable=False, default='pending'
        # pending -> processing -> ready | failed
    error: Text, nullable=True                        # failure reason for admin display
    chunk_count: Integer, nullable=False, default=0
    char_count: Integer, nullable=False, default=0
    created_at / updated_at: DateTime(timezone=True)

    __table_args__ = (
        Index('ix_books_bot_id', 'bot_id'),
        Index('ix_books_bot_hash', 'bot_id', 'file_hash', unique=True),  # no duplicate book per bot
    )
```

Add relationship `Bot.books` with `cascade="all, delete-orphan"`.

### A.2 Alembic migration

New file in `migrations/versions/` following the existing naming convention
(`YYYYMMDD_HHMM_<rev>_add_books_table.py`). Creates the `books` table and indexes.
The vector table `data_book_chunks` is auto-created by LlamaIndex `PGVectorStore.from_params` on first use — no migration needed for it (same pattern as the existing memory vector table).

### A.3 Repository: `BookRepo` (in `storage/repos.py`, interface in `storage/interfaces.py`)

Async methods, same style as existing repos:

- `create_book(bot_id, title, author, source_filename, file_format, file_hash) -> Book`
- `get_book(book_id) -> Optional[Book]`
- `list_books(bot_id) -> List[Book]`
- `update_status(book_id, status, error=None, chunk_count=None, char_count=None)`
- `delete_book(book_id)` (row only; chunk deletion handled by knowledge store, see B.4)
- `find_by_hash(bot_id, file_hash) -> Optional[Book]` (dedup check before ingestion)

---

## Phase B — Knowledge Vector Store & Ingestion Pipeline

### B.1 New module: `knowledge/` package

```
knowledge/
    __init__.py
    parser.py        # file -> plain text
    chunker.py       # plain text -> chunks
    store.py         # BookVectorStore (pgvector wrapper, bot-scoped)
    manager.py       # BookKnowledgeManager (ingest + retrieve orchestration)
    tasks.py         # Celery task: ingest_book
```

### B.2 `knowledge/parser.py` — text extraction

Function `extract_text(file_path: str, file_format: str) -> str`.

- **`.txt`**: read with encoding detection (`utf-8` → fallback `cp1251` for Russian texts → `charset-normalizer` as last resort).
- **`.pdf`**: `pypdf` (pure-python, no system deps).
- **`.epub`**: `ebooklib` + strip HTML with `beautifulsoup4`.
- **`.fb2`**: stdlib `xml.etree` — extract `<body>` text (FB2 is common for Russian-language classics, so worth including).
- Normalize: collapse repeated whitespace, preserve paragraph breaks (`\n\n`); page-header/page-number heuristics are **out of scope**.
- Raise `BookParseError` with a human-readable message on failure (shown to admin).

New deps in `requirements.txt`: `pypdf`, `ebooklib`, `beautifulsoup4`, `charset-normalizer`.

### B.3 `knowledge/chunker.py` — chunking

Books need different chunking than chat (existing `memory/adaptive_chunker.py` is message-pair based — do not reuse it).

- Split into paragraphs, then greedily pack paragraphs into chunks of `BOOK_CHUNK_TARGET_TOKENS` (default **400**) with `BOOK_CHUNK_OVERLAP_TOKENS` (default **50**) overlap between consecutive chunks. Use the shared token counter from **`core/tokens.py`** (Part 1 §1.3) — do not create another copy.
- Oversized single paragraphs are split on sentence boundaries.
- Output: `List[BookChunk]` dataclass: `text`, `chunk_index` (0-based, sequential through the whole book).

### B.4 `knowledge/store.py` — `BookVectorStore`

A sibling of `PgVectorStore` (`memory/llamaindex/vector_store.py`), backed by LlamaIndex `PGVectorStore.from_params(table_name="book_chunks", embed_dim=config.MEMORY_EMBED_DIM)`.

**Important:** reuse the same embedding model/dimension as memory (`MEMORY_EMBED_MODEL` / `MEMORY_EMBED_DIM`) — one embedding provider serves both corpora, obtained via `build_embedding_model()` (Part 1 §1.3).

Methods:

- `upsert(nodes: List[TextNode])` — bulk, same as memory store.
- `query(query_embedding, top_k, bot_id, min_score=None) -> List[NodeWithScore]` — filters `ExactMatchFilter(key="bot_id", value=bot_id)`. **No user_id filter** (knowledge is bot-global). Optionally drop results below `min_score`.
- `delete_book(book_id)` — `DELETE FROM public."data_book_chunks" WHERE metadata_->>'book_id' = :bid` (same raw-SQL pattern as `PgVectorStore.clear`).
- `fetch_neighbors(book_id, chunk_index, radius)` — same neighbor-expansion pattern as memory (`±1` chunk gives the model surrounding context of a matched passage).

Node metadata: `{"bot_id", "book_id", "book_title", "author", "chunk_index"}`.

Do **not** widen the existing `VectorStore` abstraction in `core/abstractions.py` to cover this; add a new small `KnowledgeStore` protocol there instead (query semantics differ: bot-scoped vs user-scoped).

### B.5 `knowledge/manager.py` — `BookKnowledgeManager`

Mirrors `LlamaIndexMemoryManager` structure:

- `__init__(store: BookVectorStore, embedding_model: EmbeddingModel, expand_neighbors: int)`
- `ingest_book(book_id, bot_id, title, author, text) -> int`
  1. chunk text (B.3)
  2. batch-embed chunk texts in batches of ~64 (one giant batch may exceed provider limits for a whole book — unlike memory chunks, a book is thousands of chunks)
  3. build `TextNode`s with metadata, bulk upsert
  4. return chunk count
- `get_context(bot_id, query, top_k, min_score) -> str`
  1. embed query
  2. vector query scoped to `bot_id`
  3. neighbor expansion, dedup, order by `(book_id, chunk_index)`
  4. format each excerpt with a source line so the LLM can attribute:
     `[«{book_title}»]\n{text}` joined by `\n---\n`
- `delete_book(book_id)`

### B.6 `knowledge/tasks.py` — Celery ingestion task

`ingest_book_task(book_id: str)` registered in the existing Celery app, using the persistent-loop pattern from Part 1 §3.2:

1. Load `Book` row; set `status='processing'`.
2. Read the stored file from `BOOKS_STORAGE_DIR/<book_id>.<ext>` (see C.2).
3. `extract_text` → `ingest_book` via `BookKnowledgeManager`.
4. On success: `status='ready'`, store `chunk_count`, `char_count`; delete the source file (keep if `BOOKS_KEEP_SOURCE_FILES=true`).
5. On failure: `status='failed'`, `error=<message>`, log with traceback.

Ingestion must be idempotent: before upserting, call `store.delete_book(book_id)` so a retried task doesn't duplicate chunks.

**Why Celery and not inline in the admin bot:** a 500-page book is minutes of parsing + embedding; the admin bot handler must return immediately after the upload.

---

## Phase C — Admin Bot Integration

### C.1 Feature flag

Add to `features.py`:

```python
BOOK_KNOWLEDGE = "book_knowledge"   # in BotFeature enum
DEFAULT_FEATURE_FLAGS[BotFeature.BOOK_KNOWLEDGE.value] = False  # opt-in
```

Default **off** — only persona bots that need it enable it via the existing `/togglefeature <bot_id> book_knowledge`.

### C.2 File storage

- New config: `BOOKS_STORAGE_DIR` (default `./book_files`), must be a **shared Docker volume** between the admin-bot container and the Celery worker container — add the volume to `docker-compose.yml` for both services.
- Admin bot downloads the Telegram document to `BOOKS_STORAGE_DIR/<book_id>.<ext>`.
- Telegram Bot API caps downloads at **20 MB** — validate `document.file_size` and reject larger files with a clear message (sufficient for virtually any text book).

### C.3 New admin commands (in `admin_bot.py`)

Follow the existing `ConversationHandler` + `_pending_bot_data` + `_session_key` patterns and the admin-authorization check on every entry point. All DB access goes through `BotRepo` / `BookRepo` (Part 1 §2.3) — no inline SQL.

**`/addbook <bot_id>`** — conversation flow:

1. Validate bot exists. Reply: "Send me the book file (.txt, .pdf, .epub, .fb2, max 20 MB). /cancel to abort."
2. New state `WAITING_BOOK_FILE` with `MessageHandler(filters.Document.ALL, ...)`:
   - validate extension and size;
   - compute sha256, check `find_by_hash(bot_id, hash)` → reject duplicates;
   - create `Book` row (`status='pending'`, title defaults to filename stem);
   - download file to `BOOKS_STORAGE_DIR`;
   - ask: "Send the book title and author as `Title — Author` (or /skip to use the filename)."
3. New state `WAITING_BOOK_META`: parse `Title — Author` (also accept `/skip`), update the row, enqueue `ingest_book_task(book_id)`.
4. Reply: "📚 Book queued for processing. Check /listbooks {bot_id} for status."

**`/listbooks <bot_id>`** — plain command: list each book as
`{status_emoji} **{title}** — {author} | {chunk_count} chunks | ID: {book_id}`
(status emoji: ⏳ pending/processing, ✅ ready, ❌ failed + error text).

**`/removebook <book_id>`** — deletes vector chunks (`BookKnowledgeManager.delete_book`), the stored file if present, and the DB row. Confirms with the title.

**Update help/start text and `/editbot` output** to mention the three new commands and the `book_knowledge` flag.

### C.4 Wiring

The `BookKnowledgeManager` is constructed in the composition root (`ServiceContainer` / `AppContext`, Part 1 §2.2) from the shared embedding model, and exposed to: the admin bot (delete path), the prompt assembler (retrieval, §D.1), and Celery (ingest). If Part 1 §2.2 has not landed yet, wire it in both `app_context.py` and `bot.py` the same way memory is wired today — but prefer landing §2.2 first (see execution order).

---

## Phase D — Retrieval at Reply Time (PromptAssembler)

### D.1 Inject book context in `prompt/assembler.py`

`PromptAssembler.__init__` gets an optional `book_knowledge_manager: Optional[BookKnowledgeManager] = None`.

Add a `_build_book_section` step **between memory retrieval and history** (alongside the section builders from Part 1 §2.4):

1. Skip unless `book_knowledge_manager` is set, the conversation has a `bot_id`, and the bot's `book_knowledge` feature flag is on (flags arrive together with personality per Part 1 §2.4 — no extra DB query here).
2. Query: same `memory_query` already resolved for memory retrieval.
3. `context = await book_knowledge_manager.get_context(bot_id, query, top_k=config.BOOK_RAG_TOP_K, min_score=config.BOOK_RAG_MIN_SCORE)`
4. Token budget: new config `BOOK_RAG_TOKEN_BUDGET_RATIO` (default **0.25** of `history_budget`), deducted from `remaining_history_budget` like the memory section; reuse the same line-by-line truncation approach.
5. Inject as a system message:

```
### Source Material
Relevant excerpts from your own published works. Ground your answer in these
ideas and, where natural, paraphrase or quote them. If the excerpts are not
relevant to the question, ignore them.

[«Так говорил Заратустра»]
<chunk text>
---
[«Beyond Good and Evil»]
<chunk text>
```

6. Add `book_tokens` to `token_counts` and `included_book_chunk_ids` to metadata.

Failure isolation: wrap in try/except like the memory block — a broken knowledge store must never block a reply.

### D.2 Wiring in the bot runtime

Wherever `PromptAssembler` is constructed — bot process, Celery proactive-messaging path, `get_ai_runtime_for_bot` — pass the shared `BookKnowledgeManager` in (**all** construction sites; with Part 1 §2.2 there is exactly one). Gate global enablement on new config `BOOK_RAG_ENABLED` (default `true`; per-bot control stays with the feature flag).

### D.3 Config additions (`config.py` / `AppSettings.books` + `env_example.txt`)

```python
BOOK_RAG_ENABLED = bool, default true
BOOKS_STORAGE_DIR = str, default './book_files'
BOOKS_KEEP_SOURCE_FILES = bool, default false
BOOK_CHUNK_TARGET_TOKENS = int, default 400
BOOK_CHUNK_OVERLAP_TOKENS = int, default 50
BOOK_RAG_TOP_K = int, default 4
BOOK_RAG_MIN_SCORE = float, default 0.35
BOOK_RAG_TOKEN_BUDGET_RATIO = float, default 0.25
BOOK_RAG_EXPAND_NEIGHBORS = int, default 1
BOOK_EMBED_BATCH_SIZE = int, default 64
```

Add validation mirroring the memory settings (ratio in [0,1], budget sanity, etc.) — as pydantic validators if Part 1 §2.5 has landed, otherwise in `config.validate()`.

---

## Phase E — Persona Setup (documentation, no code)

Document in README (or `docs/persona-bots.md`) the recipe:

1. `/addbot` → token, name "Friedrich Nietzsche", personality prompt. Suggested template:

```
You are Friedrich Nietzsche, the 19th-century German philosopher. Speak in the
first person with his characteristic aphoristic, provocative, poetic style.
Draw on your actual published ideas: will to power, eternal recurrence, the
Übermensch, master–slave morality, amor fati, the death of God. When excerpts
from your works are provided in the Source Material section, ground your
answers in them and quote or paraphrase them where it strengthens the point.
Never break character. Answer in the language the user writes in.
```

2. `/togglefeature <bot_id> book_knowledge`
3. `/addbook <bot_id>` → upload "Also sprach Zarathustra.txt" etc. (one file per command run)
4. `/listbooks <bot_id>` → wait for ✅
5. Chat with the bot.

---

## Phase F — Tests

Follow existing test layout in `tests/` (deterministic, fake providers — see `conftest.py`):

1. **`tests/test_book_parser.py`** — txt (utf-8 + cp1251), minimal pdf/epub/fb2 fixtures, unsupported format raises `BookParseError`.
2. **`tests/test_book_chunker.py`** — chunk sizes respect target/overlap, sequential indices, oversized-paragraph splitting, empty text → no chunks.
3. **`tests/test_book_repo.py`** — CRUD, status transitions, unique `(bot_id, file_hash)` dedup.
4. **`tests/test_book_knowledge_manager.py`** — with fake embedding model + fake store: ingest produces correct node metadata and batching; `get_context` formats with titles, applies `min_score`, orders chunks; re-ingest deletes old chunks first (idempotency).
5. **`tests/test_assembler_book_rag.py`** — book section injected only when flag on; token budget respected and truncation works; knowledge-store exception does not break prompt build; metadata contains `book_tokens`.
6. **`tests/test_admin_bot_books.py`** — flow tests mirroring existing admin-bot tests: oversized file rejected, bad extension rejected, duplicate hash rejected, happy path creates row + enqueues task (Celery mocked), `/removebook` cleans up.

## Part 2 — Out of scope (explicitly)

- Web UI for book management (admin bot only).
- OCR for scanned PDFs (text-layer PDFs only; scanned PDFs fail with a clear parse error).
- Cross-bot shared libraries of books (each book belongs to exactly one bot; upload the file again for another bot).
- Re-chunking existing books after config changes (delete + re-add the book instead).
- Citation rendering to the end user (the LLM may quote naturally; no structured citations).

## Part 2 — Key risks & mitigations

- **Embedding dimension mismatch**: book chunks must use the same `MEMORY_EMBED_DIM` as configured; if the operator changes embedding models later, both vector tables are invalidated — document this in `env_example.txt` next to the new vars.
- **Long ingestion**: batch embedding (64/call) + Celery retry with backoff; status visible via `/listbooks`.
- **Prompt bloat**: book budget is ratio-capped and comes out of the existing `history_budget`, so total prompt size never grows beyond current limits.
- **Relevance noise on chit-chat messages** ("hi", "how are you"): `BOOK_RAG_MIN_SCORE` threshold drops weak matches, and the injected instruction tells the model to ignore irrelevant excerpts.

---
---

# Unified Execution Order

---

# Current Completion Audit — 2026-06-11

Evidence used for this audit:
- `ruff check .` passed.
- `pytest -q` passed with `199 passed, 55 deselected`.
- Repository searches for raw SQL/model leaks, config imports, `uuid5("telegram_user_...")`, book manager construction, async loop usage, and deprecated warning sources.

Status key:
- `[done]` acceptance criteria are satisfied by current code and tests.
- `[partial]` material progress exists, but the plan item is not fully accepted.
- `[open]` still requires implementation.

## Part 1 Status

### P0 — Behavior bugs
- `[done] 0.1` Generation parameters are passed through `ModelClient.ask(..., temperature=..., max_tokens=...)`, including Gemini `GenerationConfig`; covered by AI handler tests.
- `[done] 0.2` Personality switching persists a per-user `UserBotSettings.settings["personality_override"]`; `PromptAssembler` resolves it per conversation instead of mutating the global bot personality.
- `[done] 0.3` Message queue and dispatcher use `redis.asyncio`; dispatcher processes active users with bounded concurrency.
- `[done] 0.4` `MessageDispatcher` lazily creates and LRU-caches Telegram `Bot` instances by token; the default bot is lazy when no token is configured.
- `[done] 0.5` The outer timeout was removed from `generate_ai_response`; retry/timeout ownership is in `AIHandler.generate_response`.
- `[done] 0.6` `AIHandler.generate_response` has an explicit `Optional[str]` failure contract and no longer silently falls through.
- `[done] 0.7` Queue validation allows negative Telegram chat IDs by validating only integer type.
- `[done] 0.8` Non-test timestamp storage/comparison paths use timezone-aware UTC datetimes.

### P1 — Dead code and duplication
- `[done] 1.1` Orphaned `PostgresMemoryRepo`, `Memory` model, and `memories_embeddings` references are gone from non-history code.
- `[done] 1.2` Sync wrapper methods were removed from `PostgresConversationManager`; production uses async methods.
- `[done] 1.3` Shared `BotConfig`, `mask_db_url`, token counting, and embedding factory exist; embedding factory now accepts `AppSettings`.
- `[partial] 1.4` Listed dead-code removals are mostly complete, but a final explicit grep/review pass is still needed before marking the whole item done.
- `[done] 1.5` `conversations.persona_id` is nullable via migration, and first-contact conversation creation no longer fabricates a default persona.
- `[done] 1.6` `messages_user` model/repo/storage wiring is removed, with a migration dropping the table.

### P2 — Architecture
- `[done] 2.1` Multi-bot construction uses constructor injection and shared handler registration; no config monkey-patching remains.
- `[done] 2.2` `ServiceContainer` owns process-shared storage, conversation manager, embedding model, memory manager, queue manager, typing manager, dispatcher, and book knowledge manager; bot, manager, admin, and Celery context consume it.
- `[done] 2.3` Bot access goes through `PostgresBotRepo`; `from storage.models import Bot` is limited to storage/migrations.
- `[done] 2.4` `PromptAssembler` no longer imports SQL/model classes or queries the DB for bot personality; section builders and token metadata are split out.
- `[partial] 2.5` `AppSettings` exists and is injected through the container and prompt assembler, but several runtime modules still import compatibility globals from `config.py`.
- `[done] 2.6` Canonical identity is documented in `docs/user-identity.md`: raw Telegram integer ID at runtime boundaries, `users.id` as internal relational UUID, and `messages_log` UUID derivation confined to `PostgresMessageHistoryRepo`.

### P3 — Async and runtime hygiene
- `[partial] 3.1` `bot.py` uses PTB lifecycle hooks and has no `get_event_loop`, but the `__main__` block still uses `asyncio.run(shutdown_handler(...))` in exception paths.
- `[done] 3.2` Celery tasks use a persistent worker loop helper (`core/celery_loop.py`); `AppContext` no longer tracks event-loop identity or disposes engines on loop changes.
- `[done] 3.3` `TypingIndicatorManager` lock state is reference-counted and cleaned up.
- `[open] 3.4` `bot_manager` still uses polling sleeps for bot lifetime/watchdog control.

### P4 — Decomposition, logging, error policy
- `[open] 4.1` `message_manager.py` has not been split into a package.
- `[partial] 4.2` Some privacy/noise reductions landed, but runtime modules still need a focused logging audit.
- `[partial] 4.3` Exception policy is improved in touched paths, but broad catches remain and have not been audited systematically.
- `[done] 4.4` Photo/voice replies are now neutral fallbacks instead of persona-conflicting canned romantic replies.
- `[partial] 4.5` Conversation caching stores conversation IDs only, but `_user_cache` is still present in code and should be removed before marking this item fully complete.

## Part 2 Status

- `[done] Phase A` `Book` model, Alembic migration, `BookRepo`, storage wiring, and tests exist.
- `[done] Phase B` `knowledge/` parser, chunker, vector store, manager, and Celery ingestion task exist and are tested.
- `[done] Phase C` Admin feature flag, file storage, `/addbook`, `/listbooks`, `/removebook`, and service-container wiring exist and are tested.
- `[done] Phase D.1-D.2` `PromptAssembler` injects book context with feature gating and receives the shared `BookKnowledgeManager` from the container.
- `[partial] Phase D.3` `AppSettings.books` exists, but some book modules still import compatibility globals from `config.py`; `env_example.txt` still needs an explicit final audit.
- `[open] Phase E` Persona setup documentation has not been added.
- `[done] Phase F` Focused tests exist for book repo, parser, chunker, knowledge manager, ingestion task, admin commands, and prompt book RAG.

## Remaining High-Signal Work

1. Finish the typed settings migration by removing remaining runtime `from config import ...` usage where practical.
2. Finish `bot_manager` event-driven stop/watchdog cleanup.
3. Remove the remaining `_user_cache` field or prove it is needed.
4. Audit logging and broad exception catches in touched runtime paths.
5. Add persona setup documentation and final `env_example.txt` review for book settings.
6. Run a final requirement-by-requirement audit before marking the goal complete.

| Step | Items | Risk | Notes |
|---|---|---|---|
| 1 | Part 1: P0.1, P0.2, P0.6, P0.7, P0.8 | low | isolated bug fixes with tests |
| 2 | Part 1: P1.1–P1.4 (deletions, incl. `core/tokens.py` + embedding factory) | low | green suite proves it; unblocks Part 2 |
| 3 | Part 1: P0.3, P0.4, P0.5 (messaging runtime) + P3.3 | medium | needs the dispatcher tests |
| 4 | Part 1: P2.1, P2.3, P2.4 | medium | `BotRepo` + assembler split unblock Part 2 admin & retrieval |
| 5 | **Part 2: Phases A + B** (model, migration, repo, knowledge package, Celery ingest) | medium | testable in isolation, no behavior change for existing bots |
| 6 | **Part 2: Phases D + C** (retrieval behind flags, then admin commands + docker volume) | medium | retrieval first so admin upload is immediately useful; everything behind `BOOK_RAG_ENABLED` + per-bot flag |
| 7 | **Part 2: Phases E + F** (docs + remaining tests) | low | tests are written alongside steps 5–6, not deferred |
| 8 | Part 1: P2.2, P2.5, P3.1, P3.2 (composition root, settings, runtime) | high | own PR; move Book wiring into the container per §C.4 |
| 9 | Part 1: P1.5, P1.6, P2.6 (schema migrations) | medium | take a DB backup first |
| 10 | Part 1: P4.x (decomposition, logging, error policy) | low | includes §4.4 which matters for persona bots |

Rationale: steps 1–4 fix the bugs the feature would otherwise inherit (silent `llm_config`, blocking dispatcher) and create the shared pieces Part 2 imports; the feature lands in 5–7 while the codebase is still familiar; the high-risk composition-root rework (8) then has one extra consumer (books) to validate the design; schema cleanups (9) and polish (10) close out.
