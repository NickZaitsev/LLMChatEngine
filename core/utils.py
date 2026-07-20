"""Small shared utility helpers."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SENSITIVE_QUERY_KEYS = {
    "access_token", "api_key", "apikey", "auth", "key", "password",
    "secret", "signature", "token",
}


def mask_url(url: str) -> str:
    """Return a URL safe for logs by redacting credentials and secret query values."""
    if not url:
        return url
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname or ""
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        host = hostname
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        if parsed.username is not None:
            password = ":***" if parsed.password is not None else ""
            host = f"{parsed.username}{password}@{host}"
        query = urlencode([
            (key, "***" if key.lower() in _SENSITIVE_QUERY_KEYS else value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        ])
        return urlunsplit((parsed.scheme, host, parsed.path, query, parsed.fragment))
    except (TypeError, ValueError):
        return "***masked***"


def mask_db_url(db_url: str) -> str:
    """Backward-compatible alias for generic credential-safe URL masking."""
    return mask_url(db_url)
