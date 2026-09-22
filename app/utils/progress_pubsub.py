import os
import json
from typing import AsyncIterator, Dict, Any

try:
    import redis.asyncio as aioredis
except Exception:
    aioredis = None

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


async def subscribe_progress(repo_id: str) -> AsyncIterator[Dict[str, Any]]:
    """Async generator that yields parsed JSON messages published to channel `progress:{repo_id}`.

    Falls back to nothing if aioredis is not installed.
    """
    if aioredis is None:
        return
        yield  # type: ignore

    client = aioredis.from_url(REDIS_URL)
    try:
        pubsub = client.pubsub()
        await pubsub.subscribe(f"progress:{repo_id}")
        async for message in pubsub.listen():
            if message is None:
                continue
            # message example: {'type': 'message', 'channel': b'progress:repo-...', 'data': b'...'}
            if message.get("type") == "message":
                data = message.get("data")
                try:
                    obj = json.loads(data)
                except Exception:
                    obj = {"raw": str(data)}
                yield obj
    finally:
        try:
            await pubsub.unsubscribe(f"progress:{repo_id}")
        except Exception:
            pass
        try:
            await client.close()
        except Exception:
            pass
