# User Identity

Telegram user identity has one canonical external form in this codebase:

- `telegram_id` (`int`) is the external user identifier used at runtime boundaries.
- `users.id` (`UUID`) is the internal relational identifier for conversation-owned data.
- `users.username` stores `str(telegram_id)` for the Telegram integration.
- `messages.extra_data["telegram_user_id"]` may store the raw Telegram ID for debugging and traceability.

`messages_log.user_id` is an analytics-table compatibility detail. The column is UUID-shaped, so
`PostgresMessageHistoryRepo` derives a deterministic UUID from the raw Telegram ID before writing
that table. Callers must still pass the raw Telegram integer ID; they must not derive or persist
`uuid5(NAMESPACE_OID, f"telegram_user_{telegram_id}")` outside the message-history repository.

Book memory/vector metadata should use the raw Telegram ID string when it needs an external user
identifier. New schema work should prefer either raw `telegram_id` for external references or
`users.id` for relational references, not additional derived identifiers.
