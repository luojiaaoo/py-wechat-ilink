from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from Crypto.Cipher import AES

from .parser import parse_message
from .storage import CacheStorage
from .types import (
    BOT_TYPE,
    CHANNEL_VERSION,
    DEFAULT_CDN_BASE_URL,
    DEFAULT_BASE_URL,
    DEFAULT_POLL_TIMEOUT,
    MSG_ITEM_FILE,
    MSG_ITEM_IMAGE,
    MSG_ITEM_TEXT,
    MSG_ITEM_VIDEO,
    MSG_STATE_FINISH,
    MSG_TYPE_BOT,
    MSG_TYPE_USER,
    UPLOAD_MEDIA_FILE,
    UPLOAD_MEDIA_IMAGE,
    UPLOAD_MEDIA_VIDEO,
    AccountData,
    QRLoginResult,
    ReceivedMessage,
    SendResult,
    UploadUrlResponse,
    WeChatILinkError,
)


class WeChatClient:
    def __init__(self, cache_dir: str | Path = ".cache", base_url: str = DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.storage = CacheStorage(cache_dir)
        self.account: AccountData | None = None
        self._context_map = self.storage.load_context_map()
        self._login_thread: threading.Thread | None = None
        self._login_error: Exception | None = None

    def load_credentials(self) -> AccountData | None:
        self.account = self.storage.load_account()
        if self.account is not None:
            self.base_url = self.account.base_url.rstrip("/")
        return self.account

    def get_login_qrcode(self) -> QRLoginResult:
        qr_data = self._http_get_json(f"{self.base_url}/ilink/bot/get_bot_qrcode?bot_type={quote(BOT_TYPE)}")
        return QRLoginResult(
            qrcode=qr_data["qrcode"],
            qrcode_url=qr_data.get("qrcode_img_content", ""),
            qrcode_base64=qr_data.get("qrcode_img_content", ""),
            status="wait",
        )

    def wait_for_qrcode_and_save_credentials(self, qrcode: str, timeout: int = 480) -> AccountData:
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self._http_get_json(
                f"{self.base_url}/ilink/bot/get_qrcode_status?qrcode={quote(qrcode)}",
                timeout=35,
            )
            state = status.get("status")
            if state in {"wait", "scaned"}:
                time.sleep(1)
                continue
            if state == "expired":
                raise WeChatILinkError("QR code expired before confirmation")
            if state == "confirmed":
                token = status.get("bot_token")
                account_id = status.get("ilink_bot_id")
                if not token or not account_id:
                    raise WeChatILinkError("Login confirmed but credentials are incomplete")
                account = AccountData(
                    token=token,
                    base_url=(status.get("baseurl") or self.base_url).rstrip("/"),
                    account_id=account_id,
                    user_id=status.get("ilink_user_id"),
                    saved_at=datetime.now(timezone.utc).isoformat(),
                )
                self.account = account
                self.base_url = account.base_url
                self.storage.save_account(account)
                return account
            raise WeChatILinkError(f"Unexpected QR status: {state}")

        raise WeChatILinkError("Login timed out")

    def get_qrcode_and_save_credentials(self, timeout: int = 480) -> str:
        login = self.get_login_qrcode()
        self._login_error = None
        self._login_thread = threading.Thread(
            target=self._login_worker,
            args=(login.qrcode, timeout),
            daemon=True,
        )
        self._login_thread.start()
        return login.qrcode_url

    def wait_for_credentials(self, timeout: int = 480) -> AccountData:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._login_error is not None:
                error = self._login_error
                self._login_error = None
                raise WeChatILinkError(str(error))
            account = self.load_credentials()
            if account is not None:
                return account
            time.sleep(1)
        raise WeChatILinkError("Waiting for credentials timed out")

    def _login_worker(self, qrcode: str, timeout: int) -> None:
        try:
            self.wait_for_qrcode_and_save_credentials(qrcode, timeout=timeout)
        except Exception as exc:
            self._login_error = exc

    def send_text(self, to_user: str, text: str) -> SendResult:
        context_token = self._require_context_token(to_user)
        raw = self._api_call(
            "ilink/bot/sendmessage",
            {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": to_user,
                    "client_id": self._generate_client_id(),
                    "message_type": MSG_TYPE_BOT,
                    "message_state": MSG_STATE_FINISH,
                    "item_list": [{"type": MSG_ITEM_TEXT, "text_item": {"text": text}}],
                    "context_token": context_token,
                },
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
        )
        return SendResult(ok=True, message="text sent", to_user=to_user, message_type="text", raw=raw)

    def send_image(self, to_user: str, file_path: str | Path) -> SendResult:
        return self._send_media(to_user, file_path, MSG_ITEM_IMAGE, "image")

    def send_video(self, to_user: str, file_path: str | Path) -> SendResult:
        return self._send_media(to_user, file_path, MSG_ITEM_VIDEO, "video")

    def send_file(self, to_user: str, file_path: str | Path) -> SendResult:
        return self._send_media(to_user, file_path, MSG_ITEM_FILE, "file")

    def receive_messages(self, timeout: int = DEFAULT_POLL_TIMEOUT) -> list[ReceivedMessage]:
        response = self._api_call(
            "ilink/bot/getupdates",
            {
                "get_updates_buf": self.storage.load_sync_buf(),
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
            timeout=timeout,
            swallow_timeout=True,
        )

        ret = response.get("ret", 0)
        if ret not in (0, None):
            raise WeChatILinkError(f"getupdates failed: ret={ret} errmsg={response.get('errmsg', '')}")

        next_buf = response.get("get_updates_buf")
        if next_buf:
            self.storage.save_sync_buf(next_buf)

        received: list[ReceivedMessage] = []
        for raw in response.get("msgs") or []:
            if raw.get("message_type") != MSG_TYPE_USER:
                continue
            parsed = parse_message(raw)
            if parsed is None:
                continue
            if parsed.context_token:
                self._context_map[parsed.chat_id] = parsed.context_token
                self.storage.save_context_map(self._context_map)
            if parsed.message_type in {"image", "video", "file"}:
                parsed.media_path = self.download_media(parsed)
            received.append(parsed)
        return received

    def download_media(self, message: ReceivedMessage) -> Path | None:
        if message.media_path is not None:
            return message.media_path

        item = self._find_media_item(message.raw)
        if item is None:
            return None

        media_info = item.get(f"{message.message_type}_item") or {}
        nested_media = media_info.get("media") or {}
        download_url = (
            media_info.get("cdn_url")
            or media_info.get("url")
            or media_info.get("full_url")
            or nested_media.get("cdn_url")
            or nested_media.get("url")
            or nested_media.get("full_url")
        )
        if not download_url:
            return None

        payload = self._http_get_bytes(download_url)
        aes_key = (
            media_info.get("aes_key")
            or media_info.get("aeskey")
            or nested_media.get("aes_key")
            or nested_media.get("aeskey")
        )
        if aes_key:
            payload = self._decrypt_aes_ecb(payload, aes_key)
        suffix = self._guess_media_suffix(message.message_type, download_url, media_info, nested_media)
        return self.storage.save_media(payload, suffix=suffix, prefix=message.message_type)

    def _send_media(self, to_user: str, file_path: str | Path, item_type: int, message_type: str) -> SendResult:
        context_token = self._require_context_token(to_user)
        source_path = Path(file_path)
        plaintext = source_path.read_bytes()
        aes_key = secrets.token_bytes(16)
        ciphertext = self._encrypt_aes_ecb(plaintext, aes_key)
        upload_media_type = self._upload_media_type_for_item(item_type)
        file_key = secrets.token_hex(16)
        raw_md5 = hashlib.md5(plaintext).hexdigest()

        upload_data = self._api_call(
            "ilink/bot/getuploadurl",
            {
                "to_user_id": to_user,
                "context_token": context_token,
                "media_type": upload_media_type,
                "content_length": len(ciphertext),
                "filekey": file_key,
                "rawsize": len(plaintext),
                "rawfilemd5": raw_md5,
                "filesize": len(ciphertext),
                "aeskey": aes_key.hex(),
                "no_need_thumb": True,
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
        )
        upload_resp = UploadUrlResponse(
            upload_param=upload_data.get("upload_param"),
            ret=upload_data.get("ret"),
            errmsg=upload_data.get("errmsg"),
        )
        if not upload_resp.upload_param:
            raise WeChatILinkError(f"Failed to get upload url: {upload_data}")
        file_key = str(upload_data.get("filekey") or file_key)
        download_param = self._upload_to_cdn(upload_resp.upload_param, file_key, ciphertext)
        item_payload = self._build_cdn_media_item(item_type, download_param, aes_key, source_path)

        raw = self._api_call(
            "ilink/bot/sendmessage",
            {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": to_user,
                    "client_id": self._generate_client_id(),
                    "message_type": MSG_TYPE_BOT,
                    "message_state": MSG_STATE_FINISH,
                    "item_list": [item_payload],
                    "context_token": context_token,
                },
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
        )
        return SendResult(
            ok=True,
            message=f"{message_type} sent",
            to_user=to_user,
            message_type=message_type,  # type: ignore[arg-type]
            media_id=upload_resp.upload_param,
            raw=raw,
        )

    def _build_cdn_media_item(self, item_type: int, download_param: str, aes_key: bytes, source_path: Path) -> dict[str, Any]:
        media = {
            "encrypt_query_param": download_param,
            "aes_key": base64.b64encode(aes_key.hex().encode("utf-8")).decode("utf-8"),
            "encrypt_type": 1,
        }
        if item_type == MSG_ITEM_IMAGE:
            return {"type": item_type, "image_item": {"media": media, "mid_size": source_path.stat().st_size}}
        if item_type == MSG_ITEM_VIDEO:
            return {"type": item_type, "video_item": {"media": media, "video_size": source_path.stat().st_size}}
        return {
            "type": item_type,
            "file_item": {
                "media": media,
                "file_name": source_path.name,
                "len": str(source_path.stat().st_size),
            },
        }

    def _require_context_token(self, to_user: str) -> str:
        token = self._context_map.get(to_user)
        if token:
            return token
        raise WeChatILinkError(f"No context token cached for {to_user}")

    def _ensure_account(self) -> AccountData:
        if self.account is None:
            loaded = self.load_credentials()
            if loaded is None:
                raise WeChatILinkError("Credentials are not loaded")
        assert self.account is not None
        return self.account

    def _api_call(
        self,
        endpoint: str,
        body: dict[str, Any],
        timeout: int = 15,
        swallow_timeout: bool = False,
    ) -> dict[str, Any]:
        account = self._ensure_account()
        return self._http_post_json(
            f"{account.base_url.rstrip('/')}/{endpoint}",
            body,
            headers={
                "AuthorizationType": "ilink_bot_token",
                "Authorization": f"Bearer {account.token}",
                "X-WECHAT-UIN": self._random_wechat_uin(),
            },
            timeout=timeout,
            swallow_timeout=swallow_timeout,
        )

    def _http_get_json(self, url: str, timeout: int = 15) -> dict[str, Any]:
        request = Request(url, headers={"iLink-App-ClientVersion": "1"}, method="GET")
        return json.loads(self._read_response(request, timeout))

    def _http_post_json(
        self,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
        timeout: int = 15,
        swallow_timeout: bool = False,
    ) -> dict[str, Any]:
        request_headers = {
            "Content-Type": "application/json",
            "iLink-App-ClientVersion": "1",
            **headers,
        }
        data = json.dumps(body).encode("utf-8")
        request = Request(url, data=data, headers=request_headers, method="POST")
        try:
            return json.loads(self._read_response(request, timeout))
        except TimeoutError:
            if swallow_timeout:
                return {"ret": 0, "msgs": [], "get_updates_buf": body.get("get_updates_buf", "")}
            raise

    def _http_put_bytes(self, url: str, payload: bytes, timeout: int = 60) -> None:
        request = Request(url, data=payload, headers={"Content-Length": str(len(payload))}, method="PUT")
        self._read_response(request, timeout)

    def _http_get_bytes(self, url: str, timeout: int = 30) -> bytes:
        request = Request(url, method="GET")
        return self._read_response(request, timeout)

    def _upload_to_cdn(self, upload_param: str, file_key: str, payload: bytes, timeout: int = 60) -> str:
        cdn_url = f"{DEFAULT_CDN_BASE_URL}/upload?encrypted_query_param={quote(upload_param)}&filekey={quote(file_key)}"
        request = Request(
            cdn_url,
            data=payload,
            headers={"Content-Type": "application/octet-stream"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                response.read()
                encrypted_param = response.headers.get("x-encrypted-param")
                if not encrypted_param:
                    raise WeChatILinkError("CDN upload succeeded but x-encrypted-param is missing")
                return encrypted_param
        except HTTPError as exc:
            raise WeChatILinkError(f"CDN upload HTTP error {exc.code}: {exc.read().decode('utf-8', errors='ignore')}") from exc
        except URLError as exc:
            raise WeChatILinkError(f"CDN upload network error: {exc.reason}") from exc

    def _read_response(self, request: Request, timeout: int) -> bytes:
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            raise WeChatILinkError(f"HTTP error {exc.code}: {exc.read().decode('utf-8', errors='ignore')}") from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise TimeoutError("request timed out") from exc
            raise WeChatILinkError(f"Network error: {exc.reason}") from exc

    def _generate_client_id(self) -> str:
        return f"wechat-ilink:{int(time.time() * 1000)}-{secrets.token_hex(4)}"

    def _random_wechat_uin(self) -> str:
        return base64.b64encode(str(secrets.randbits(32)).encode("utf-8")).decode("utf-8")

    def _encrypt_aes_ecb(self, data: bytes, key: bytes) -> bytes:
        cipher = AES.new(key, AES.MODE_ECB)
        padding_size = 16 - (len(data) % 16)
        return cipher.encrypt(data + bytes([padding_size]) * padding_size)

    def _decrypt_aes_ecb(self, data: bytes, encoded_key: str) -> bytes:
        key = self._decode_aes_key(encoded_key)
        cipher = AES.new(key, AES.MODE_ECB)
        plaintext = cipher.decrypt(data)
        padding_size = plaintext[-1]
        return plaintext[:-padding_size]

    def _decode_aes_key(self, encoded_key: str) -> bytes:
        if len(encoded_key) == 32:
            try:
                return bytes.fromhex(encoded_key)
            except ValueError:
                pass

        decoded = base64.b64decode(encoded_key)
        if len(decoded) == 16:
            return decoded

        try:
            decoded_text = decoded.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WeChatILinkError("Unsupported AES key format") from exc

        if len(decoded_text) == 32:
            try:
                return bytes.fromhex(decoded_text)
            except ValueError as exc:
                raise WeChatILinkError("Unsupported AES key format") from exc

        raise WeChatILinkError("Unsupported AES key format")

    def _find_media_item(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        for item in raw.get("item_list") or []:
            if item.get("type") in {MSG_ITEM_IMAGE, MSG_ITEM_VIDEO, MSG_ITEM_FILE}:
                return item
        return None

    def _guess_media_suffix(
        self,
        message_type: str,
        download_url: str,
        media_info: dict[str, Any],
        nested_media: dict[str, Any],
    ) -> str:
        suffix = Path(download_url.split("?")[0]).suffix
        if suffix:
            return suffix

        file_name = media_info.get("file_name") or nested_media.get("file_name")
        if file_name:
            suffix = Path(file_name).suffix
            if suffix:
                return suffix

        if message_type == "image":
            return ".jpg"
        if message_type == "video":
            return ".mp4"
        if message_type == "file":
            return ".bin"
        return ""

    def _upload_media_type_for_item(self, item_type: int) -> int:
        if item_type == MSG_ITEM_IMAGE:
            return UPLOAD_MEDIA_IMAGE
        if item_type == MSG_ITEM_VIDEO:
            return UPLOAD_MEDIA_VIDEO
        if item_type == MSG_ITEM_FILE:
            return UPLOAD_MEDIA_FILE
        raise WeChatILinkError(f"Unsupported media item type: {item_type}")
