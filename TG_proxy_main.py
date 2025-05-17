# coding=utf-8
import base64
import requests
import time
import os
import random
import string
import datetime
import logging
import asyncio
import aiohttp
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
import chardet
import yaml

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('subscription.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 从配置文件加载机场链接
def load_config(config_file: str = "config.yaml") -> List[str]:
    """加载配置文件中的机场链接"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            return config.get('home_urls', [])
    except FileNotFoundError:
        logger.error(f"配置文件 {config_file} 未找到，使用默认空列表")
        return []
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return []

# 数据存储类
class SubscriptionManager:
    def __init__(self, update_path: str = "./sub/"):
        self.update_path = update_path
        self.permanent_subs: List[str] = []  # 永久订阅
        self.trial_subs: List[str] = []      # 试用订阅
        self.nodes: List[str] = []           # 所有节点明文信息
        self.trial_nodes: List[str] = []     # 试用节点明文

    def decode_base64(self, data: str) -> Optional[str]:
        """解码base64数据并检测编码"""
        try:
            decoded_bytes = base64.b64decode(data)
            encoding = chardet.detect(decoded_bytes)['encoding'] or 'utf-8'
            return decoded_bytes.decode(encoding)
        except Exception as e:
            logger.error(f"Base64解码失败: {e}")
            return None

    async def fetch_subscription(self, url: str, session: aiohttp.ClientSession, retries: int = 3) -> Optional[str]:
        """异步获取订阅内容并实现重试机制"""
        for attempt in range(retries):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        logger.warning(f"请求 {url} 失败，状态码: {response.status}")
            except Exception as e:
                logger.warning(f"尝试 {attempt + 1}/{retries} 获取 {url} 失败: {e}")
                await asyncio.sleep(1)  # 重试前等待
        logger.error(f"获取 {url} 失败，已达最大重试次数")
        return None

    async def process_subscriptions(self):
        """异步处理所有订阅"""
        async with aiohttp.ClientSession() as session:
            tasks = []
            for url in self.permanent_subs:
                tasks.append(self.fetch_subscription(url, session))
            for url in self.trial_subs:
                tasks.append(self.fetch_subscription(url, session))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for url, result in zip(self.permanent_subs + self.trial_subs, results):
                if isinstance(result, str):
                    decoded = self.decode_base64(result)
                    if decoded and self.validate_nodes(decoded):
                        if url in self.permanent_subs:
                            self.nodes.extend(decoded.splitlines())
                        else:
                            self.trial_nodes.extend(decoded.splitlines())
                    else:
                        logger.warning(f"订阅 {url} 内容无效")
                else:
                    logger.error(f"订阅 {url} 获取失败")

    def validate_nodes(self, data: str) -> bool:
        """验证订阅内容是否有效"""
        return bool(data.strip())  # 简单验证非空，后续可扩展

    def deduplicate_nodes(self) -> List[str]:
        """高效去重节点"""
        return list(dict.fromkeys(self.nodes))  # 保持顺序并去重

    def write_to_file(self):
        """一次性写入文件"""
        if not self.permanent_subs or not self.trial_subs:
            logger.error("订阅为空，请检查！")
            return

        t = time.localtime()
        date = time.strftime('%y%m', t)
        date_day = time.strftime('%y%m%d', t)
        output_dir = os.path.join(self.update_path, date)
        os.makedirs(output_dir, exist_ok=True)

        # 写入永久订阅
        deduped_nodes = self.deduplicate_nodes()
        logger.info(f"去重完毕，去除 {len(self.nodes) - len(deduped_nodes)} 个重复节点")
        content = '\n'.join(deduped_nodes).replace('\n\n', '\n')
        txt_file = os.path.join(output_dir, f'{date_day}.txt')
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(content)

        # 写入长期订阅文件
        with open("Long_term_subscription_num", 'w', encoding='utf-8') as f:
            f.write(base64.b64encode(content.encode()).decode())

        # 写入试用订阅文件
        trial_content = '\n'.join(self.trial_nodes).replace('\n\n', '\n')
        with open("Long_term_subscription_try", 'w', encoding='utf-8') as f:
            f.write(base64.b64encode(trial_content.encode()).decode())

        logger.info(f"合并完成，共获取到 {len(deduped_nodes)} 个节点")

async def get_sub_url(manager: SubscriptionManager):
    """获取订阅链接"""
    V2B_REG_REL_URL = '/api/v1/passport/auth/register'
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1',
        'Content-Type': 'application/x-www-form-urlencoded',
    }

    async with aiohttp.ClientSession() as session:
        for url in load_config():
            form_data = {
                'email': ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(12)) + '@gmail.com',
                'password': 'autosub_v2b',
                'invite_code': '',
                'email_code': ''
            }
            try:
                async with session.post(url + V2B_REG_REL_URL, data=form_data, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        sub_url = f'{url}/api/v1/client/subscribe?token={data["data"]["token"]}'
                        manager.permanent_subs.append(sub_url)
                        manager.trial_subs.append(sub_url)
                        logger.info(f"添加订阅: {sub_url}")
                    else:
                        logger.warning(f"注册失败 {url}，状态码: {response.status}")
            except Exception as e:
                logger.error(f"获取订阅 {url} 失败: {e}")

async def main():
    logger.info("========== 开始获取机场订阅链接 ==========")
    manager = SubscriptionManager()
    await get_sub_url(manager)
    logger.info("========== 准备处理订阅 ==========")
    await manager.process_subscriptions()
    logger.info("========== 准备写入订阅 ==========")
    manager.write_to_file()
    logger.info("========== 写入完成任务结束 ==========")

if __name__ == "__main__":
    asyncio.run(main())
