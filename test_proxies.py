import requests
import yaml
import time
import os

# Clash API 地址
api_url = 'http://127.0.0.1:9090'
# 如果 Clash 配置文件中设置了 secret，请在此处添加认证头
# headers = {'Authorization': 'Bearer your_secret'}
headers = {}

# 等待 Clash 启动
time.sleep(10)

# 获取所有代理节点
response = requests.get(f'{api_url}/proxies', headers=headers)
proxies_data = response.json()
all_proxies = proxies_data['proxies']

# 找到一个 Selector 策略组用于切换代理
selector_groups = [name for name, info in all_proxies.items() if info['type'] == 'Selector']
if not selector_groups:
    print("未找到 Selector 策略组，请检查配置文件。")
    exit(1)
selector_group = selector_groups[0]

# 筛选出实际的代理节点（排除策略组）
proxy_nodes = [name for name, info in all_proxies.items() if info['type'] not in ['Selector', 'URLTest', 'Direct', 'Reject']]

# 测试每个代理节点
working_proxies = []
for proxy in proxy_nodes:
    # 切换到当前代理节点
    requests.put(f'{api_url}/proxies/{selector_group}', json={'name': proxy}, headers=headers)
    
    # 测试访问 Google
    try:
        response = requests.get('https://www.google.com', 
                              proxies={'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}, 
                              timeout=10)
        if response.status_code == 200:
            # 测试访问 YouTube
            response = requests.get('https://www.youtube.com', 
                                  proxies={'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}, 
                                  timeout=10)
            if response.status_code == 200:
                working_proxies.append(proxy)
    except Exception as e:
        print(f"测试 {proxy} 时出错: {e}")

# 读取原始配置文件
with open('data/clash.yaml', 'r') as f:
    config = yaml.safe_load(f)

# 提取能用的代理节点配置
working_proxy_configs = [p for p in config['proxies'] if p['name'] in working_proxies]

# 生成新的配置文件
new_config = {
    'proxies': working_proxy_configs,
    # 可根据需要添加其他配置，如 proxy-groups 或 rules
}

# 保存到新文件
with open('data/google.yaml', 'w') as f:
    yaml.dump(new_config, f)

# 输出 data/google.yaml 的内容
with open('data/google.yaml', 'r') as f:
    print(f.read())
