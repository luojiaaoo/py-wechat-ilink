# py-wechat-ilink

通过ClawBot的ilink接口实现WX SDK

## 功能特性

- 二维码登录认证
- 发送文本消息
- 发送图片、视频和文件附件
- 接收和解析消息
- 下载消息中的媒体文件
- 自动缓存凭证

## 安装

```bash
pip install py-wechat-ilink
```

## 依赖

- Python >= 3.9
- pycryptodome >= 3.19.0

## 快速开始

```bash
python run_test.py
```

## API 参考

### WeChatClient

#### `__init__(cache_dir: str | Path = ".cache", base_url: str = DEFAULT_BASE_URL)`
初始化客户端，指定用于存储凭证和媒体文件的缓存目录。

#### `load_credentials() -> AccountData | None`
加载已缓存的账号凭证（如果有）。用于跳过登录流程。

#### `get_login_qrcode() -> QRLoginResult`
获取登录二维码。返回 `QRLoginResult`，包含：
- `qrcode`: 二维码原始内容
- `qrcode_url`: 二维码图片 URL
- `qrcode_base64`: Base64 编码的图片
- `status`: 登录状态（wait/scaned/confirmed/expired）

#### `get_qrcode_and_save_credentials(timeout: int = 480) -> str`
在后台线程启动登录流程，返回二维码 URL。适合非阻塞场景。

#### `wait_for_credentials(timeout: int = 480) -> AccountData`
等待用户扫码确认，然后返回账号数据。阻塞直到登录成功或超时。

#### `wait_for_qrcode_and_save_credentials(qrcode: str, timeout: int = 480) -> AccountData`
轮询指定二维码的扫码状态，直到确认或过期。

#### `send_text(to_user: str, text: str) -> SendResult`
向用户发送文本消息。返回 `SendResult`，包含：
- `ok`: 是否发送成功
- `message`: 结果描述
- `to_user`: 目标用户 ID
- `message_type`: 消息类型
- `media_id`: 媒体 ID（如果有）

#### `send_image(to_user: str, file_path: str | Path) -> SendResult`
向用户发送图片文件。支持 JPG、PNG 等常见格式。

#### `send_video(to_user: str, file_path: str | Path) -> SendResult`
向用户发送视频文件。

#### `send_file(to_user: str, file_path: str | Path) -> SendResult`
向用户发送通用文件。

#### `receive_messages(timeout: int = 35) -> list[ReceivedMessage]`
长轮询获取新消息。返回接收到的消息列表。`ReceivedMessage` 包含：
- `message_id`: 消息 ID
- `sender_id`: 发送者 ID
- `group_id`: 群 ID（如果是群消息）
- `chat_id`: 会话 ID
- `message_type`: 消息类型（text/image/video/file/unknown）
- `text`: 文本内容
- `media_path`: 媒体文件本地路径（下载后）
- `raw`: 原始消息数据

#### `download_media(message: ReceivedMessage) -> Path | None`
下载并保存消息中的媒体文件（图片/视频/文件）。返回本地保存路径。

### 数据类型

| 类型 | 说明 |
|------|------|
| `AccountData` | 账号凭证（token、base_url、account_id、user_id、saved_at） |
| `QRLoginResult` | 二维码登录结果（qrcode、qrcode_url、qrcode_base64、status） |
| `SendResult` | 发送结果（ok、message、to_user、message_type、media_id） |
| `ReceivedMessage` | 接收消息（message_id、sender_id、group_id、chat_id、message_type、text、media_path） |
| `WeChatILinkError` | API 错误时抛出的异常 |

### 异常

所有 API 调用失败时会抛出 `WeChatILinkError` 异常：

```python
from py_wechat_ilink import WeChatClient, WeChatILinkError

try:
    client.send_text(to_user="user_id_here", text="Hello")
except WeChatILinkError as e:
    print(f"发送失败: {e}")
```

## 许可证

MIT