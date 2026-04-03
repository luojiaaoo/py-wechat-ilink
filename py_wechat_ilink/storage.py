from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

from .types import AccountData


class CacheStorage:
    def __init__(self, cache_dir: str | Path = ".cache") -> None:
        self.root = Path(cache_dir)
        self.media_dir = self.root / "media"
        self.tmp_dir = self.root / "tmp"
        self.account_file = self.root / "account.json"
        self.context_file = self.root / "context.json"
        self.sync_buf_file = self.root / "sync_buf.txt"
        self.root.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def load_account(self) -> AccountData | None:
        if not self.account_file.exists():
            return None
        try:
            data = json.loads(self.account_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return AccountData(
            token=data["token"],
            base_url=data["base_url"],
            account_id=data["account_id"],
            user_id=data.get("user_id"),
            saved_at=data["saved_at"],
        )

    def save_account(self, account: AccountData) -> None:
        payload = {
            "token": account.token,
            "base_url": account.base_url,
            "account_id": account.account_id,
            "user_id": account.user_id,
            "saved_at": account.saved_at,
        }
        self.account_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_context_map(self) -> dict[str, str]:
        if not self.context_file.exists():
            return {}
        return json.loads(self.context_file.read_text(encoding="utf-8"))

    def save_context_map(self, data: dict[str, str]) -> None:
        self.context_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_sync_buf(self) -> str:
        if not self.sync_buf_file.exists():
            return ""
        return self.sync_buf_file.read_text(encoding="utf-8")

    def save_sync_buf(self, buf: str) -> None:
        self.sync_buf_file.write_text(buf, encoding="utf-8")

    def save_media(self, payload: bytes, suffix: str = "", prefix: str = "media") -> Path:
        extension = suffix if suffix.startswith(".") or not suffix else f".{suffix}"
        file_name = f"{prefix}-{int(time.time() * 1000)}-{secrets.token_hex(4)}{extension}"
        path = self.media_dir / file_name
        path.write_bytes(payload)
        return path
