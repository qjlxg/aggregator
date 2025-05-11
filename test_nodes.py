import asyncio
import aiohttp
import time
import yaml
import subprocess
import logging
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CLASH_API_URL = "http://127.0.0.1:9090"
PROXY_GROUP = "auto"
SOCKS5_PROXY = "socks5://127.0.0.1:7891"
TEST_URLS = ["http://www.google.com", "https://www.cloudflare.com/"]  # 测试多个URL
API_TIMEOUT = 5
CONNECT_TIMEOUT = 10
MAX_API_RETRIES = 10
API_RETRY_INTERVAL = 1
CONCURRENCY = 5  # 同时测试的节点数量

async def is_clash_api_ready(session):
    for i in range(MAX_API_RETRIES):
        try:
            async with session.get(f"{CLASH_API_URL}/configs", timeout=API_TIMEOUT) as response:
                if response.status == 200:
                    logging.info("Clash API 已启动并响应。")
                    return True
        except aiohttp.ClientError:
            logging.warning(f"Clash API 未响应，正在重试 ({i + 1}/{MAX_API_RETRIES})...")
            await asyncio.sleep(API_RETRY_INTERVAL)
    logging.error("Clash API 在规定时间内未启动。")
    return False

async def switch_node(session, node_name):
    logging.info(f"尝试切换到节点: {node_name}")
    try:
        async with session.put(
            f"{CLASH_API_URL}/proxies/{PROXY_GROUP}",
            json={"name": node_name},
            timeout=API_TIMEOUT
        ) as response:
            if response.status == 204:
                await asyncio.sleep(0.3)
                return True
            else:
                logging.warning(f"切换到节点 '{node_name}' 失败，状态码: {response.status}")
                return False
    except aiohttp.ClientError as e:
        logging.warning(f"切换到节点 '{node_name}' 时发生错误: {e}")
        return False

async def test_connect(session, url):
    try:
        async with session.get(
            url,
            proxy=SOCKS5_PROXY,
            timeout=CONNECT_TIMEOUT
        ) as response:
            return response.status == 200
    except aiohttp.ClientError:
        return False

async def test_node(session, node_name):
    if not await switch_node(session, node_name):
        return False
    results = await asyncio.gather(*[test_connect(session, url) for url in TEST_URLS])
    if all(results):
        logging.info(f"节点 '{node_name}' 测试成功。")
        return True
    else:
        logging.info(f"节点 '{node_name}' 测试失败。")
        return False

async def main():
    logging.info("启动 Clash...")
    process = subprocess.Popen(["./clash/clash-linux", "-f", "config.yaml"])
    await asyncio.sleep(5)

    async with aiohttp.ClientSession() as session:
        if not await is_clash_api_ready(session):
            logging.error("无法进行节点测试，Clash API 不可用。")
            if process.poll() is None:
                process.terminate()
            return

        try:
            with open("config.yaml", "r") as f:
                config = yaml.safe_load(f)
            nodes = {p["name"]: p for p in config.get("proxies", [])}
        except FileNotFoundError:
            logging.error("config.yaml 文件未找到。")
            if process.poll() is None:
                process.terminate()
            return
        except yaml.YAMLError as e:
            logging.error(f"解析 config.yaml 文件时发生错误: {e}")
            if process.poll() is None:
                process.terminate()
            return

        raw_nodes = {}
        try:
            with open("data/ss.txt", "r") as f:
                raw_nodes = {i: line.strip() for i, line in enumerate(f.readlines())}
        except FileNotFoundError:
            logging.warning("data/ss.txt 文件未找到，将不关联原始 URI。")

        valid_nodes = []
        node_names = list(nodes.keys())
        semaphore = asyncio.Semaphore(CONCURRENCY)

        async def test_with_semaphore(node_name):
            async with semaphore:
                if await test_node(session, node_name):
                    for index, raw in raw_nodes.items():
                        if node_name in raw or re.match(f"^ss-{re.escape(raw.split('@')[1].split(':')[0])}", node_name):
                            valid_nodes.append(raw)
                            break

        tasks = [test_with_semaphore(name) for name in node_names]
        await asyncio.gather(*tasks)

        if process.poll() is None:
            process.terminate()
            await asyncio.sleep(1)

        try:
            with open("data/sp.txt", "w") as f:
                f.write("\n".join(valid_nodes))
            logging.info(f"成功保存 {len(valid_nodes)} 个有效节点到 data/sp.txt")
        except IOError as e:
            logging.error(f"写入 data/sp.txt 文件时发生错误: {e}")

if __name__ == "__main__":
    asyncio.run(main())
