import logging
import time
from functools import wraps

from supabase import create_client, Client
from .config import settings

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client


def reset_client():
    global _client
    _client = None


def with_retry(max_attempts: int = 4, delay: float = 3.0):
    """Retry decorator — recreates the Supabase client on connection errors."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    msg = str(e)
                    if any(k in msg for k in ("RemoteProtocolError", "Server disconnected",
                                               "ConnectError", "ReadError", "TimeoutException")):
                        logger.warning("Supabase connection error (attempt %d/%d): %s",
                                       attempt, max_attempts, msg)
                        reset_client()
                        time.sleep(delay * attempt)
                    else:
                        raise
            raise RuntimeError(f"Supabase call failed after {max_attempts} attempts")
        return wrapper
    return decorator
