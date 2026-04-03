from __future__ import annotations

import sys
import time

import qrcode

from py_wechat_ilink import WeChatClient, WeChatILinkError


def print_qr_terminal(content: str) -> None:
    qr = qrcode.QRCode(border=1)
    qr.add_data(content)
    qr.make(fit=True)
    qr.print_ascii()



def main() -> int:
    client = WeChatClient()
    account = client.load_credentials()
    if account is None:
        login = client.get_qrcode_and_save_credentials()
        print("Scan this QR code with WeChat:")
        print_qr_terminal(login)
        print()
        print("QR URL:")
        print(login)
        account = client.wait_for_credentials()

    if account is None:
        print("Failed to load credentials.")
        return 1

    print(f"Logged in as: {account.account_id}")
    print("Echo bot is running. Press Ctrl+C to stop.")

    last_message_chat_id = list(client._context_map.keys())[-1]
    print(f"Last message chat ID: {last_message_chat_id}")
    client.send_text(last_message_chat_id, "欢迎使用微信机器人！")
    try:
        while True:
            messages = client.receive_messages()
            for message in messages:
                try:
                    if message.message_type == "text":
                        print(f"recv {message.message_type} from {message.chat_id}: {message.text}")
                        client.send_text(message.chat_id, message.text)
                    elif message.message_type == "image" and message.media_path is not None:
                        print(f"recv {message.message_type} from {message.chat_id}: {message.media_path}")
                        client.send_image(message.chat_id, message.media_path)
                    elif message.message_type == "video":
                        print(f"recv {message.message_type} from {message.chat_id}: {message.media_path}")
                        client.send_video(message.chat_id, message.media_path)
                    elif message.message_type == "file":
                        print(f"recv {message.message_type} from {message.chat_id}: {message.media_path}")
                        client.send_file(message.chat_id, message.media_path)
                    else:
                        print(f"recv {message.message_type} from {message.chat_id}, not supported")
                        client.send_text(message.chat_id, message.text or f"[{message.message_type}]")
                except WeChatILinkError as exc:
                    print(f"failed to echo {message.message_type}: {exc}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopped.")
        return 0
    except WeChatILinkError as exc:
        print(f"WeChat error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
