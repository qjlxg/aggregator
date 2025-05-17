# coding=utf-8
import base64
import time
import os
import random
import string
import logging
import asyncio
import aiohttp
import yaml
import chardet
from typing import List, Optional, Dict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('subscription.log', encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 从配置文件加载机场链接
def load_config(config_file: str = "config.yaml") -> List[Dict[str, str]]:
    """加载配置文件中的机场链接和邀请码"""
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

# 检查是否为 Base64 编码
def is_base64(data: str) -> bool:
    """检查字符串是否为有效的 Base64 编码"""
    try:
        base64.b64decode(data, validate=True)
        return True
    except Exception:
        return False

# 数据存储类
class SubscriptionManager:
    def __init__(self, update_path: str = "./sub/"):
        self.update_path = update_path
        self.permanent_subs: List[str] = ["https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/ss.yaml"]
        self.trial_subs: List[str] = ["https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/ss.yaml"]
        self.nodes: List[str] = ["https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/v2ray.txt"]
        self.trial_nodes: List[str] = ["https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/ss.txt"]

    def decode_base64(self, data: str) -> Optional[str]:
        """解码 Base64 数据并检测编码，若不是 Base64 则返回原文"""
        if is_base64(data):
            try:
                decoded_bytes = base64.b64decode(data, validate=True)
                encoding = chardet.detect(decoded_bytes).get('encoding', 'utf-8') or 'utf-8'
                return decoded_bytes.decode(encoding)
            except Exception as e:
                logger.error(f"Base64 解码失败: {e}")
                return None
        else:
            logger.info("数据非 Base64 编码，按明文处理")
            return data

    async def fetch_subscription(self, url: str, session: aiohttp.ClientSession, retries: int = 3) -> Optional[str]:
        """异步获取订阅内容并实现重试机制"""
        for attempt in range(retries):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        content = await response.text()
                        logger.info(f"成功获取订阅 {url}")
                        return content
                    else:
                        logger.warning(f"请求 {url} 失败，状态码: {response.status}")
            except Exception as e:
                logger.warning(f"尝试 {attempt + 1}/{retries} 获取 {url} 失败: {e}")
                await asyncio.sleep(1)
        logger.error(f"获取 {url} 失败，已达最大重试次数")
        return None

    async def process_subscriptions(self):
        """异步处理所有订阅"""
        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch_subscription(url, session) for url in self.permanent_subs + self.trial_subs]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for url, result in zip(self.permanent_subs + self.trial_subs, results):
                if isinstance(result, str):
                    decoded = self.decode_base64(result)
                    if decoded:
                        nodes = self.parse_nodes(decoded)
                        if nodes and self.validate_nodes(nodes):
                            if url in self.permanent_subs:
                                self.nodes.extend(nodes)
                            if url in self.trial_subs:
                                self.trial_nodes.extend(nodes)
                            logger.info(f"订阅 {url} 处理成功，获取到 {len(nodes)} 个节点")
                        else:
                            logger.warning(f"订阅 {url} 内容无效或无有效节点")
                    else:
                        logger.warning(f"订阅 {url} 解码失败")
                else:
                    logger.error(f"订阅 {url} 获取失败")

    def parse_nodes(self, data: str) -> List[str]:
        """解析订阅内容，支持多种格式"""
        lines = data.strip().splitlines()
        nodes = []
        # 如果是 YAML 格式，尝试解析
        if data.strip().startswith(('{', '[')) or 'proxies:' in data:
            try:
                yaml_data = yaml.safe_load(data)
                if isinstance(yaml_data, dict) and 'proxies' in yaml_data:
                    nodes = [str(proxy) for proxy in yaml_data['proxies']]
                elif isinstance(yaml_data, list):
                    nodes = [str(item) for item in yaml_data]
            except Exception as e:
                logger.warning(f"YAML 解析失败: {e}")
        else:
            # 按行处理明文节点
            nodes = [line.strip() for line in lines if line.strip()]
        return nodes

    def validate_nodes(self, nodes: List[str]) -> bool:
        """验证节点列表是否有效"""
        valid_prefixes = ('vmess://', 'trojan://', 'ss://', 'http://', 'https://')
        return bool(nodes) and any(node.startswith(prefixes) for node in nodes for prefixes in valid_prefixes)

    def deduplicate_nodes(self) -> List[str]:
        """高效去重节点"""
        return list(dict.fromkeys(self.nodes))

    def write_to_file(self):
        """一次性写入文件"""
        if not self.nodes and not self.trial_nodes:
            logger.error("没有获取到任何有效节点，请检查订阅！")
            return

        t = time.localtime()
        date = time.strftime('%y%m', t)
        date_day = time.strftime('%y%m%d', t)
        output_dir = os.path.join(self.update_path, date)
        os.makedirs(output_dir, exist_ok=True)

        deduped_nodes = self.deduplicate_nodes()
        logger.info(f"去重完毕，去除 {len(self.nodes) - len(deduped_nodes)} 个重复节点")
        content = '\n'.join(deduped_nodes).replace('\n\n', '\n')
        txt_file = os.path.join(output_dir, f'{date_day}.txt')
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(content)

        with open("Long_term_subscription_num", 'w', encoding='utf-8') as f:
            f.write(base64.b64encode(content.encode()).decode())

        trial_content = '\n'.join(self.trial_nodes).replace('\n\n', '\n')
        with open("Long_term_subscription_try", 'w', encoding='utf-8') as f:
            f.write(base64.b64encode(trial_content.encode()).decode())

        logger.info(f"合并完成，共获取到 {len(deduped_nodes)} 个节点")

async def get_sub_url(manager: SubscriptionManager):
    """增强注册功能，获取订阅链接"""
    V2B_REG_REL_URL = '/api/v1/passport/auth/register'
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1',
        'Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36',
    ]

    async with aiohttp.ClientSession() as session:
        config_urls = load_config()
        for item in config_urls:
            url = item if isinstance(item, str) else item.get('url', '')
            invite_code = item.get('invite_code', '') if isinstance(item, dict) else ''
            headers = {
                'User-Agent': random.choice(user_agents),
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
            }
            for attempt in range(5):  # 增加重试次数
                try:
                    form_data = {
                        'email': ''.join(random.choices(string.ascii_letters + string.digits, k=12)) + '@gmail.com',
                        'password': 'autosub_v2b_' + ''.join(random.choices(string.digits, k=4)),
                        'invite_code': invite_code,
                        'email_code': ''
                    }
                    logger.info(f"尝试注册 {url}，参数: {form_data}")
                    async with session.post(url + V2B_REG_REL_URL, data=form_data, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('data') and data['data'].get('token'):
                                sub_url = f'{url}/api/v1/client/subscribe?token={data["data"]["token"]}'
                                manager.permanent_subs.append(sub_url)
                                manager.trial_subs.append(sub_url)
                                logger.info(f"成功注册并添加订阅: {sub_url}")
                                break
                            else:
                                logger.warning(f"注册成功但未返回 token: {url}, 响应: {data}")
                        else:
                            logger.warning(f"注册失败 {url}，状态码: {response.status}")
                except Exception as e:
                    logger.error(f"注册 {url} 失败 (尝试 {attempt + 1}/5): {e}")
                await asyncio.sleep(random.uniform(1, 5))  # 随机延时
            else:
                logger.error(f"注册 {url} 失败，已达最大重试次数")

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
