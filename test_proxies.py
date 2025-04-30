import yaml
import subprocess
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import os

# 全局锁，确保 API 调用线程安全
api_lock = threading.Lock()

def main():
    # 1. 解析 clash.yaml 文件
    clash_config_path = 'clash/clash.yaml'  # 假设配置文件在仓库的 clash 目录下
    if not os.path.exists(clash_config_path):
        print(f"错误: {clash_config_path} 不存在")
        return
    with open(clash_config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    proxies = config['proxies']
    proxy_names = [proxy['name'] for proxy in proxies]

    # 2. 生成临时配置文件
    temp_config = config.copy()
    temp_config['proxy-groups'] = [
        {
            'name': 'test-group',
            'type': 'select',
            'proxies': proxy_names
        }
    ]
    temp_config['mode'] = 'global'
    if 'external-controller' not in temp_config:
        temp_config['external-controller'] = '127.0.0.1:9090'
    if 'port' not in temp_config:
        temp_config['port'] = 7890  # 默认 HTTP 代理端口
    temp_config_path = 'clash/temp_clash.yaml'
    with open(temp_config_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(temp_config, f, default_flow_style=False)

    # 3. 启动 Clash 进程
    clash_binary = './clash/clash'  # Clash 二进制文件路径
    if not os.path.exists(clash_binary):
        print(f"错误: Clash 二进制文件 {clash_binary} 不存在")
        return
    clash_process = subprocess.Popen([clash_binary, '-f', temp_config_path])
    api_url = 'http://127.0.0.1:9090'

    # 等待 Clash 启动
    max_wait = 30  # 最大等待时间（秒）
    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(f'{api_url}/version', timeout=5)
            if response.status_code == 200:
                print("Clash 已成功启动")
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    else:
        print("Clash 启动超时")
        clash_process.terminate()
        return

    # 4. 使用多线程测试代理
    available_proxies = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_proxy = {
            executor.submit(test_single_proxy, api_url, proxy['name']): proxy
            for proxy in proxies
        }
        for future in as_completed(future_to_proxy):
            proxy = future_to_proxy[future]
            try:
                if future.result():
                    available_proxies.append(proxy['name'])
                    print(f"代理 {proxy['name']} 可用")
                else:
                    print(f"代理 {proxy['name']} 不可用")
            except Exception as e:
                print(f"测试代理 {proxy['name']} 时出错: {e}")

    # 5. 关闭 Clash 进程
    clash_process.terminate()

    # 6. 筛选可用代理并保存
    available_proxy_configs = [
        proxy for proxy in proxies if proxy['name'] in available_proxies
    ]
    output_path = 'clash/2.yaml'
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump({'proxies': available_proxy_configs}, f, default_flow_style=False)
    print(f"可用代理已保存到 {output_path}")

def select_proxy(api_url, proxy_name):
    """通过 Clash API 选择代理"""
    url = f'{api_url}/proxies/test-group'
    data = {'name': proxy_name}
    with api_lock:
        try:
            response = requests.put(url, json=data, timeout=5)
            if response.status_code != 200:
                print(f"选择代理 {proxy_name} 失败")
                return False
            time.sleep(1)  # 等待代理切换生效
            return True
        except requests.exceptions.RequestException as e:
            print(f"选择代理 {proxy_name} 时出错: {e}")
            return False

def test_proxy():
    """测试当前代理是否能访问 Google 和 Yahoo"""
    urls = ['https://www.google.com', 'https://www.yahoo.com']
    proxies_dict = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
    for url in urls:
        try:
            response = requests.get(url, proxies=proxies_dict, timeout=10)
            if response.status_code != 200:
                return False
        except requests.exceptions.RequestException:
            return False
    return True

def test_single_proxy(api_url, proxy_name):
    """测试单个代理"""
    if not select_proxy(api_url, proxy_name):
        return False
    return test_proxy()

if __name__ == '__main__':
    main()
