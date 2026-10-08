import httpx
from typing import Optional, Any
from app.core.config import settings

class UpstashRedisClient:
    """
    Upstash Redis REST client using httpx.
    Does not require persistent socket connections — ideal for serverless & Railway deployments.
    """
    def __init__(self):
        self.url = settings.UPSTASH_REDIS_REST_URL.rstrip("/")
        self.token = settings.UPSTASH_REDIS_REST_TOKEN
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def get(self, key: str) -> Optional[str]:
        if not self.url or not self.token:
            return None
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{self.url}/get/{key}", headers=self.headers)
            if res.status_code == 200:
                data = res.json()
                return data.get("result")
            return None

    async def set(self, key: str, value: Any, ex_seconds: Optional[int] = None) -> bool:
        if not self.url or not self.token:
            return False
        async with httpx.AsyncClient() as client:
            import urllib.parse
            encoded_val = urllib.parse.quote(str(value), safe="")
            endpoint = f"{self.url}/set/{key}/{encoded_val}"
            if ex_seconds:
                endpoint += f"?EX={ex_seconds}"
            res = await client.post(endpoint, headers=self.headers)
            return res.status_code == 200

    async def delete(self, key: str) -> bool:
        if not self.url or not self.token:
            return False
        async with httpx.AsyncClient() as client:
            res = await client.post(f"{self.url}/del/{key}", headers=self.headers)
            return res.status_code == 200

    async def rpush(self, key: str, value: str) -> bool:
        """Append a value to the end of a Redis list."""
        if not self.url or not self.token:
            return False
        async with httpx.AsyncClient() as client:
            import urllib.parse
            encoded_value = urllib.parse.quote(value, safe="")
            res = await client.post(
                f"{self.url}/rpush/{key}/{encoded_value}",
                headers=self.headers,
            )
            return res.status_code == 200

    async def lrange(self, key: str, start: int, stop: int) -> list:
        """Return elements from a list between start and stop indices."""
        if not self.url or not self.token:
            return []
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
            return False
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{self.url}/ltrim/{key}/{start}/{stop}",
                headers=self.headers,
            )
            return res.status_code == 200

    async def keys(self, pattern: str) -> list:
        """Find all keys matching pattern."""
        if not self.url or not self.token:
            return []
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"{self.url}/keys/{pattern}",
                headers=self.headers,
            )
            if res.status_code == 200:
                return res.json().get("result", []) or []
            return []

redis_client = UpstashRedisClient()
