from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
BOT_TYPE = "3"
CHANNEL_VERSION = "1.0.0"
DEFAULT_POLL_TIMEOUT = 35

MSG_TYPE_USER = 1
MSG_TYPE_BOT = 2
MSG_STATE_FINISH = 2

MSG_ITEM_TEXT = 1
MSG_ITEM_IMAGE = 2
MSG_ITEM_VOICE = 3
MSG_ITEM_FILE = 4
MSG_ITEM_VIDEO = 5

UPLOAD_MEDIA_IMAGE = 1
UPLOAD_MEDIA_VIDEO = 2
UPLOAD_MEDIA_FILE = 3

MessageKind = Literal["text", "image", "video", "file", "unknown"]


class WeChatILinkError(Exception):
    pass


@dataclass(slots=True)
class AccountData:
    token: str
    base_url: str
    account_id: str
    user_id: str | None
    saved_at: str


@dataclass(slots=True)
class UploadUrlResponse:
    upload_param: str | None = None
    ret: int | None = None
    errmsg: str | None = None


@dataclass(slots=True)
class QRLoginResult:
    qrcode: str
    qrcode_url: str
    qrcode_base64: str
    account: AccountData | None = None
    status: Literal["wait", "scaned", "confirmed", "expired"] | None = None


@dataclass(slots=True)
class SendResult:
    ok: bool
    message: str
    to_user: str
    message_type: MessageKind
    media_id: str | None = None
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class ReceivedMessage:
    message_id: str
    sender_id: str
    group_id: str | None
    chat_id: str
    message_type: MessageKind
    text: str | None
    context_token: str | None
    create_time_ms: int | None
    media_path: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedContent:
    message_type: MessageKind
    text: str | None
    item: dict[str, Any] | None
