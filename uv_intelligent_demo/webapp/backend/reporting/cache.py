from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from redis import Redis
from redis.exceptions import RedisError


@dataclass
class CachedPdf:
    content: bytes
    content_type: str = "application/pdf"


class ReportCache:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self.client: Redis | None = None

    def connect(self) -> None:
        try:
            self.client = Redis.from_url(self.redis_url, decode_responses=False)
            self.client.ping()
        except RedisError:
            self.client = None

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def is_available(self) -> bool:
        return self.client is not None

    def get_json(self, key: str) -> dict[str, Any] | None:
        if self.client is None:
            return None
        try:
            payload = self.client.get(key)
            if not payload:
                return None
            return json.loads(payload.decode("utf-8"))
        except (RedisError, json.JSONDecodeError):
            return None

    def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int = 3600) -> None:
        if self.client is None:
            return
        try:
            self.client.setex(key, ttl_seconds, json.dumps(value, default=str).encode("utf-8"))
        except RedisError:
            return

    def delete(self, *keys: str) -> None:
        if self.client is None or not keys:
            return
        try:
            self.client.delete(*keys)
        except RedisError:
            return

    def cache_pdf(self, report_id: str, pdf_path: Path, ttl_seconds: int = 86400) -> None:
        if self.client is None or not pdf_path.exists():
            return
        try:
            content = pdf_path.read_bytes()
            payload = {
                "content": base64.b64encode(content).decode("ascii"),
                "content_type": "application/pdf",
            }
            self.client.setex(
                f"report:pdf:{report_id}",
                ttl_seconds,
                json.dumps(payload).encode("utf-8"),
            )
        except (OSError, RedisError):
            return

    def get_pdf(self, report_id: str) -> CachedPdf | None:
        if self.client is None:
            return None
        try:
            payload = self.client.get(f"report:pdf:{report_id}")
            if not payload:
                return None
            data = json.loads(payload.decode("utf-8"))
            return CachedPdf(
                content=base64.b64decode(data["content"]),
                content_type=data.get("content_type", "application/pdf"),
            )
        except (KeyError, ValueError, RedisError, json.JSONDecodeError):
            return None
