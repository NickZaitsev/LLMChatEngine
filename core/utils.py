"""Small shared utility helpers."""


def mask_db_url(db_url: str) -> str:
    """Mask credentials in a database URL for logs."""
    try:
        if "@" in db_url and "://" in db_url:
            scheme_and_auth, rest = db_url.split("://", 1)
            if "@" in rest:
                auth, host_and_path = rest.split("@", 1)
                if ":" in auth:
                    user, _ = auth.split(":", 1)
                    return f"{scheme_and_auth}://{user}:***@{host_and_path}"
        return db_url[:20] + "***"
    except Exception:
        return "***masked***"
