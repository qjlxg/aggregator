import yaml
import subprocess
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 全局锁，确保 API 调用线程安全
api_lock = threading.Lock()

def main():
    # 1. 解析 clash.yaml 文件
    with open('data/clash.yaml', 'r', encoding='utf-8') as f:
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
    with open('data/temp_clash.yaml', 'w', encoding='utf-8') as f:
        yaml.safe_dump(temp_config, f, default_flow_style=False)

    # 3. 启动 Clash 进程
    clash_process = subprocess.Popen(['clash', '-f', 'data/temp_clash.yaml'])
    api_url = 'http://127.0.0.1:9090'

    # 等待 Clash 启动
    while True:
        try:
            response = requests.get(f'{api_url}/version', timeout=5)
            if response.status_code == 200:
                print("Clash 已成功启动")
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)

    # 4. 使用多线程测试代理
    available_proxies = []
    with ThreadPoolExecutor(max_workers=5) as executor:  # 限制最大线程数，避免 API 冲突
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
    with open('data/2.yaml', 'w', encoding='utf-8') as f:
        yaml.safe_dump({'proxies': available_proxy_configs}, f, default_flow_style=False)
    print("可用代理已保存到 data/2.yaml")

def select_proxy(api_url, proxy_name):
    """通过 Clash API 选择代理"""
    url = f'{api_url}/proxies/test-group'
    data = {'name': proxy_name}
    with api_lock:  # 确保线程安全
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
