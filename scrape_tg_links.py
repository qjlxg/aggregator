import os
import asyncio
import re
import requests
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest

# 从环境变量中获取 API ID 和 Hash （GitHub Actions Secrets）
api_id = int(os.environ.get("TELEGRAM_API_ID"))
api_hash = os.environ.get("TELEGRAM_API_HASH")
channel_username = "dingyue_center"  # 替换为你的频道用户名
output_file = "data/subscribes.txt"

async def scrape_channel(api_id, api_hash, channel_username, output_file):
    """
    从 Telegram 频道抓取链接，去重，验证并保存。
    """

    client = TelegramClient('anon', api_id, api_hash)

    async with client:
        try:
            channel = await client.get_entity(channel_username)
        except Exception as e:
            print(f"Error getting channel: {e}")
            return

        all_messages = []
        offset_id = 0
        limit = 100

        while True:
            print(f"Fetching messages from offset {offset_id}...")
            history = await client(GetHistoryRequest(
                peer=channel,
                offset_id=offset_id,
                offset_date=None,
                add_offset=0,
                limit=limit,
                max_id=0,
                min_id=0,
                hash=0
            ))
            if not history.messages:
                break
            messages = history.messages
            all_messages.extend(messages)
            offset_id = messages[-1].id
            if len(messages) < limit:
                break

        urls = set()  # 用于去重

        for message in all_messages:
            if message.message:
                # 使用正则表达式提取链接
                found_urls = re.findall(r'(https?://\S+)', message.message)
                for url in found_urls:
                    urls.add(url.strip())

        valid_urls = []
        for url in urls:
            try:
                response = requests.head(url, timeout=5)  # 使用 HEAD 请求，更快
                if response.status_code < 400:  # 认为 400+ 的状态码是无效链接
                    valid_urls.append(url)
                    print(f"Valid URL: {url}")
                else:
                    print(f"Invalid URL (Status {response.status_code}): {url}")
            except requests.exceptions.RequestException as e:
                print(f"Error checking URL {url}: {e}")


        # 保存到文件
        os.makedirs(os.path.dirname(output_file), exist_ok=True) # 确保目录存在
        with open(output_file, "w", encoding="utf-8") as f:
            for url in valid_urls:
                f.write(url + "\n")

        print(f"Saved {len(valid_urls)} valid URLs to {output_file}")


async def main():
    await scrape_channel(api_id, api_hash, channel_username, output_file)

if __name__ == "__main__":
    asyncio.run(main())
