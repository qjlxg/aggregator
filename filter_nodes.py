import logging
import requests
import yaml
from queue import Queue
from threading import Thread
import os
import sys

# 配置日志格式和级别
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定义测试 URL，仅包含 Cloudflare
TEST_URLS = {
    "Cloudflare": "https://www.cloudflare.com"
}

def load_nodes(input_file):
    """
    加载 Clash 节点配置文件。
    
    参数:
        input_file (str): 输入文件路径。
    
    返回:
        list: 节点列表。
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data.get("proxies", [])

def test_proxy(proxy, result_queue):
    """
    测试单个节点的连通性。
    
    参数:
        proxy (dict): 节点信息。
        result_queue (Queue): 用于存储测试结果的队列。
    """
    try:
        # 配置代理
        proxies = {
            "http": f"http://{proxy['server']}:{proxy['port']}",
            "https": f"http://{proxy['server']}:{proxy['port']}"
        }
        success = True
        # 测试 Cloudflare
        for name, url in TEST_URLS.items():
            try:
                response = requests.get(url, proxies=proxies, timeout=10)
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
    """
    保存测试通过的节点到输出文件。
    
    参数:
        proxies (list): 通过测试的节点列表。
        output_file (str): 输出文件路径。
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.safe_dump({"proxies": proxies}, f)

def main():
    """
    主函数，协调节点加载、测试和结果保存。
    """
    input_file = "data/clash.yaml"
    output_file = "data/google.yaml"
    
    # 检查输入文件是否存在
    if not os.path.exists(input_file):
        logging.error(f"输入文件 {input_file} 不存在")
        sys.exit(1)
    
    # 加载节点
    nodes = load_nodes(input_file)
    logging.info(f"共加载 {len(nodes)} 个节点")
    
    # 使用队列收集测试结果
    result_queue = Queue()
    threads = []
    
    # 为每个节点启动一个测试线程
    for node in nodes:
        t = Thread(target=test_proxy, args=(node, result_queue))
        t.start()
        threads.append(t)
    
    # 等待所有线程完成
    for t in threads:
        t.join()
    
    # 获取测试通过的节点
    available_proxies = []
    while not result_queue.empty():
        available_proxies.append(result_queue.get())
    
    # 保存结果或生成空文件
    if available_proxies:
        save_results(available_proxies, output_file)
        logging.info(f"找到 {len(available_proxies)} 个可用节点")
    else:
        logging.warning("没有找到可用节点，生成空文件")
        with open(output_file, 'w', encoding='utf-8') as f:
            yaml.safe_dump({"proxies": []}, f)

if __name__ == "__main__":
    main()
