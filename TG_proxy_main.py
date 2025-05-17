import base64
import logging
import asyncio
import aiohttp
import yaml
from typing import List, Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('subscription.log', encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class SubscriptionManager:
    def __init__(self, update_path: str = "./sub/"):
        self.update_path = update_path
        # 只存储订阅链接
        self.permanent_subs: List[str] = ["https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/v2ray.txt"]
        self.trial_subs: List[str] = ["https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/v2ray.txt"]
        # 节点列表初始化为空
        self.nodes: List[str] = []
        self.trial_nodes: List[str] = []

    def decode_base64(self, data: str) -> Optional[str]:
        """解码 Base64 数据，若不是 Base64 则返回原文"""
        try:
            decoded_bytes = base64.b64decode(data)
            return decoded_bytes.decode('utf-8', errors='ignore')
        except Exception:
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
        """解析订阅内容，支持 Base64、明文和 Clash YAML 格式"""
        nodes = []
        # 尝试按 YAML 解析（Clash 格式）
        try:
            yaml_data = yaml.safe_load(data)
            if isinstance(yaml_data, dict) and 'proxies' in yaml_data:
                nodes = [str(proxy) for proxy in yaml_data['proxies']]
            elif isinstance(yaml_data, list):
                nodes = [str(item) for item in yaml_data]
        except Exception:
            # 如果不是 YAML，按明文或 Base64 解码后按行解析
            lines = data.strip().splitlines()
            nodes = [line.strip() for line in lines if line.strip() and line.startswith(('vmess://', 'trojan://', 'ss://', 'http://', 'https://'))]
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
        import os
        import time

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

async def main():
    logger.info("========== 开始处理订阅 ==========")
    manager = SubscriptionManager()
    # 可以在这里添加更多订阅链接，例如通过注册获取的链接
    manager.permanent_subs.append("https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/v2ray.txt")
    await manager.process_subscriptions()
    logger.info("========== 准备写入订阅 ==========")
    manager.write_to_file()
    logger.info("========== 写入完成任务结束 ==========")

if __name__ == "__main__":
    asyncio.run(main())
