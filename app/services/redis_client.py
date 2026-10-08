import fnmatch
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple
import httpx
from app.core.config import settings


class UpstashRedisClient:
    """
    Upstash Redis REST client using httpx.
    Does not require persistent socket connections — ideal for serverless & Railway deployments.
    Falls back to a memory store if unconfigured (for offline unit tests).
    """

    def __init__(self):
        self.url = (settings.UPSTASH_REDIS_REST_URL or "").rstrip("/")
        self.token = settings.UPSTASH_REDIS_REST_TOKEN or ""
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        self._local_store: Dict[str, Any] = {}
        self._local_ttls: Dict[str, Tuple[float, int]] = {}

    def _purge_expired(self, key: str) -> bool:
        if key in self._local_ttls:
            set_at, ex = self._local_ttls[key]
            if time.time() - set_at >= ex:
                self._local_store.pop(key, None)
                self._local_ttls.pop(key, None)
                return True
        return False

    async def get(self, key: str) -> Optional[str]:
        if not self.url or not self.token:
            if self._purge_expired(key):
                return None
            val = self._local_store.get(key)
            return str(val) if val is not None else None

        async with httpx.AsyncClient() as client:
            res = await client.get(f"{self.url}/get/{key}", headers=self.headers)
            if res.status_code == 200:
                data = res.json()
                return data.get("result")
            return None

    async def set(self, key: str, value: Any, ex_seconds: Optional[int] = None) -> bool:
        if not self.url or not self.token:
            self._local_store[key] = str(value)
            if ex_seconds:
                self._local_ttls[key] = (time.time(), int(ex_seconds))
            else:
                self._local_ttls.pop(key, None)
            return True

        async with httpx.AsyncClient() as client:
            encoded_val = urllib.parse.quote(str(value), safe="")
            endpoint = f"{self.url}/set/{key}/{encoded_val}"
            if ex_seconds:
                endpoint += f"?EX={ex_seconds}"
            res = await client.post(endpoint, headers=self.headers)
            return res.status_code == 200

    async def delete(self, key: str) -> bool:
        if not self.url or not self.token:
            had_key = key in self._local_store
            self._local_store.pop(key, None)
            self._local_ttls.pop(key, None)
            return had_key

        async with httpx.AsyncClient() as client:
            res = await client.post(f"{self.url}/del/{key}", headers=self.headers)
            return res.status_code == 200

    async def expire(self, key: str, seconds: int) -> bool:
        """Sets a timeout on key in seconds."""
        if not self.url or not self.token:
            if self._purge_expired(key):
                return False
            if key in self._local_store:
                self._local_ttls[key] = (time.time(), int(seconds))
                return True
            return False

        async with httpx.AsyncClient() as client:
            res = await client.post(f"{self.url}/expire/{key}/{seconds}", headers=self.headers)
            if res.status_code == 200:
                data = res.json()
                return data.get("result") in (1, "OK", True)
            return False

    async def ttl(self, key: str) -> int:
        """Returns the remaining time to live of a key that has a timeout in seconds."""
        if not self.url or not self.token:
            if self._purge_expired(key):
                return -2
            if key in self._local_ttls:
                set_at, ex = self._local_ttls[key]
                remaining = int(ex - (time.time() - set_at))
                return max(0, remaining)
            if key in self._local_store:
                return -1
            return -2

        async with httpx.AsyncClient() as client:
            res = await client.get(f"{self.url}/ttl/{key}", headers=self.headers)
            if res.status_code == 200:
                val = res.json().get("result")
                return int(val) if val is not None else -2
            return -2

    async def rpush(self, key: str, value: str) -> int:
        """Append a value to the end of a Redis list, returning the length after the push."""
        if not self.url or not self.token:
            self._purge_expired(key)
            lst = self._local_store.get(key)
            if not isinstance(lst, list):
                lst = []
                self._local_store[key] = lst
            lst.append(value)
            return len(lst)

        async with httpx.AsyncClient() as client:
            encoded_value = urllib.parse.quote(value, safe="")
            res = await client.post(
                f"{self.url}/rpush/{key}/{encoded_value}",
                headers=self.headers,
            )
            if res.status_code == 200:
                result = res.json().get("result")
                try:
                    return int(result)
                except (ValueError, TypeError):
                    return 1
            return 0

    async def lrange(self, key: str, start: int, stop: int) -> list:
        """Return elements from a list between start and stop indices."""
        if not self.url or not self.token:
            if self._purge_expired(key):
                return []
            lst = self._local_store.get(key)
            if not isinstance(lst, list):
                return []
            if stop == -1:
                return list(lst[start:])
            return list(lst[start : stop + 1])

        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"{self.url}/lrange/{key}/{start}/{stop}",
                headers=self.headers,
            )
            if res.status_code == 200:
                return res.json().get("result", [])
            return []

    async def ltrim(self, key: str, start: int, stop: int) -> bool:
        """Trim a list to elements between start and stop indices."""
        if not self.url or not self.token:
            if self._purge_expired(key):
                return False
            lst = self._local_store.get(key)
            if not isinstance(lst, list):
                return False
            if stop == -1:
                self._local_store[key] = lst[start:]
            else:
                self._local_store[key] = lst[start : stop + 1]
            return True

        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{self.url}/ltrim/{key}/{start}/{stop}",
                headers=self.headers,
            )
            return res.status_code == 200

    async def keys(self, pattern: str) -> list:
        """Find all keys matching pattern."""
        if not self.url or not self.token:
            current_keys = list(self._local_store.keys())
            for k in current_keys:
                self._purge_expired(k)
            return [k for k in self._local_store.keys() if fnmatch.fnmatch(k, pattern)]

        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"{self.url}/keys/{pattern}",
                headers=self.headers,
            )
            if res.status_code == 200:
                return res.json().get("result", []) or []
            return []


redis_client = UpstashRedisClient()
