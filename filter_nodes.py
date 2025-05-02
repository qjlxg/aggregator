import logging
import requests
import yaml
from queue import Queue
from threading import Thread
import os
import sys

# 配置日志格式和级别
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定义测试 URL
TEST_URLS = {
    "GitHub": "https://www.github.com"
}

def load_nodes(input_file):
    """加载 Clash 节点配置文件"""
    with open(input_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data.get("proxies", [])

def test_proxy(proxy, result_queue):
    """测试单个节点的连通性"""
    try:
        proxies = {
            "http": f"http://{proxy['server']}:{proxy['port']}",
            "https": f"http://{proxy['server']}:{proxy['port']}"
        }
        success = True
        for name, url in TEST_URLS.items():
            try:
                response = requests.get(url, proxies=proxies, timeout=15)
                if response.status_code != 200:
                    success = False
                    logging.info(f"节点 {proxy['name']} 无法访问 {name}")
                    break
            except Exception as e:
                success = False
                logging.info(f"节点 {proxy['name']} 测试 {name} 失败: {e}")
                break
        if success:
            result_queue.put(proxy)
            logging.info(f"节点 {proxy['name']} 测试通过")
    except Exception as e:
        logging.error(f"测试节点 {proxy['name']} 时出错: {e}")

def save_results(proxies, output_file):
    """保存测试通过的节点到输出文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.safe_dump({"proxies": proxies}, f)

def main():
    """主函数，协调节点加载、测试和结果保存"""
    input_file = "data/clash.yaml"
    output_file = "data/google.yaml"
    
    if not os.path.exists(input_file):
        logging.error(f"输入文件 {input_file} 不存在")
        sys.exit(1)
    
    nodes = load_nodes(input_file)
    logging.info(f"共加载 {len(nodes)} 个节点")
    
    result_queue = Queue()
    threads = []
    for node in nodes:
        t = Thread(target=test_proxy, args=(node, result_queue))
        t.start()
        threads.append(t)
    
    for t in threads:
        t.join()
    
    available_proxies = []
    while not result_queue.empty():
        available_proxies.append(result_queue.get())
    
    if available_proxies:
        save_results(available_proxies, output_file)
        logging.info(f"找到 {len(available_proxies)} 个可用节点")
    else:
        logging.warning("没有找到可用节点，生成空文件")
        with open(output_file, 'w', encoding='utf-8') as f:
            yaml.safe_dump({"proxies": []}, f)

if __name__ == "__main__":
    main()
