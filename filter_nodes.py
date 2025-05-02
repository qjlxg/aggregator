import yaml
import subprocess
import requests
import os
import time
import logging
from threading import Thread
from queue import Queue

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 测试的目标 URL
TEST_URLS = {
    "Google": "https://www.google.com",
    "YouTube": "https://www.youtube.com"
}

# Clash 可执行文件路径（根据 GitHub Actions 环境选择）
CLASH_EXEC = "./clash/clash-linux"  # GitHub Actions 使用 Linux 环境
CLASH_CONFIG = "config.yaml"
COUNTRY_MMDB = "./clash/Country.mmdb"

# 读取 Clash YAML 文件
def load_nodes(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data.get('proxies', [])

# 生成临时的 Clash 配置文件
def generate_clash_config(proxy):
    config = {
        "port": 7890,
        "socks-port": 7891,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "external-controller": "127.0.0.1:9090",
        "proxies": [proxy],
        "proxy-groups": [
            {
                "name": "auto",
                "type": "select",
                "proxies": [proxy["name"]]
            }
        ],
        "rules": ["MATCH,auto"]
    }
    with open(CLASH_CONFIG, 'w', encoding='utf-8') as f:
        yaml.safe_dump(config, f)

# 测试代理节点
def test_proxy(proxy, result_queue):
    try:
        # 生成配置文件
        generate_clash_config(proxy)
        
        # 启动 Clash
        clash_process = subprocess.Popen([CLASH_EXEC, "-f", CLASH_CONFIG, "-d", "./clash"],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(2)  # 等待 Clash 启动
        
        # 配置代理
        proxies = {
            "http": "http://127.0.0.1:7890",
            "https": "http://127.0.0.1:7890"
        }
        
        # 测试 Google 和 YouTube
        success = True
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
        
        # 如果通过测试，放入结果队列
        if success:
            result_queue.put(proxy)
            logging.info(f"节点 {proxy['name']} 测试通过")
        
        # 关闭 Clash
        clash_process.terminate()
        time.sleep(1)
    except Exception as e:
        logging.error(f"测试节点 {proxy['name']} 时出错: {e}")

# 保存结果到 YAML 文件
def save_results(proxies, output_file):
    config = {"proxies": proxies}
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.safe_dump(config, f, allow_unicode=True)
    logging.info(f"已保存 {len(proxies)} 个可用节点到 {output_file}")

# 主函数
def main():
    input_file = "data/clash.yaml"
    output_file = "data/google.yaml"
    
    # 读取节点
    nodes = load_nodes(input_file)
    logging.info(f"共加载 {len(nodes)} 个节点")
    
    # 使用队列存储结果
    result_queue = Queue()
    threads = []
    
    # 多线程测试节点
    for node in nodes:
        t = Thread(target=test_proxy, args=(node, result_queue))
        t.start()
        threads.append(t)
    
    # 等待所有线程完成
    for t in threads:
        t.join()
    
    # 获取结果
    available_proxies = []
    while not result_queue.empty():
        available_proxies.append(result_queue.get())
    
    # 保存结果
    if available_proxies:
        save_results(available_proxies, output_file)
    else:
        logging.warning("没有找到可用节点")

if __name__ == "__main__":
    main()
