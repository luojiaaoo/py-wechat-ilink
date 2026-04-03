from __future__ import annotations

from typing import Any

from .types import (
    MSG_ITEM_FILE,
    MSG_ITEM_IMAGE,
    MSG_ITEM_TEXT,
    MSG_ITEM_VIDEO,
    ParsedContent,
    ReceivedMessage,
)


def parse_message(raw: dict[str, Any]) -> ReceivedMessage | None:
    content = _extract_content(raw)
    if content is None:
        return None

    sender_id = raw.get("from_user_id") or "unknown"
    group_id = raw.get("group_id") or None
    chat_id = group_id or sender_id
    message_id = str(raw.get("message_id") or raw.get("client_id") or "")

    return ReceivedMessage(
        message_id=message_id,
        sender_id=sender_id,
        group_id=group_id,
        chat_id=chat_id,
        message_type=content.message_type,
        text=content.text,
        context_token=raw.get("context_token") or None,
        create_time_ms=raw.get("create_time_ms"),
        raw=raw,
    )


def _extract_content(raw: dict[str, Any]) -> ParsedContent | None:
    for item in raw.get("item_list") or []:
        parsed = _extract_item(item)
        if parsed is not None:
            return parsed
    return None


def _extract_item(item: dict[str, Any]) -> ParsedContent | None:
    item_type = item.get("type")
    if item_type == MSG_ITEM_TEXT:
        text = ((item.get("text_item") or {}).get("text") or "").strip()
        if not text:
            return None
        title = ((item.get("ref_msg") or {}).get("title") or "").strip()
        if title:
            text = f"[引用: {title}]\n{text}"
        return ParsedContent(message_type="text", text=text, item=item)

    if item_type == MSG_ITEM_IMAGE:
        image = item.get("image_item") or {}
        dims = ""
        if image.get("width") and image.get("height"):
            dims = f" ({image['width']}x{image['height']})"
        return ParsedContent(message_type="image", text=f"[图片{dims}]", item=item)

    if item_type == MSG_ITEM_FILE:
        file_item = item.get("file_item") or {}
        file_name = f' "{file_item["file_name"]}"' if file_item.get("file_name") else ""
        return ParsedContent(message_type="file", text=f"[文件{file_name}]", item=item)

    if item_type == MSG_ITEM_VIDEO:
        video = item.get("video_item") or {}
        duration_ms = video.get("duration_ms")
        suffix = f" ({duration_ms / 1000:.1f}s)" if duration_ms else ""
        return ParsedContent(message_type="video", text=f"[视频{suffix}]", item=item)

    return ParsedContent(message_type="unknown", text=f"[未知消息类型 {item_type}]", item=item)

