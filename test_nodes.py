import requests
import time
import yaml
import subprocess

def test_node(node_name):
    # 通过API切换到指定节点
    requests.put(
        "http://127.0.0.1:9090/proxies/auto",
        json={"name": node_name}
    )
    time.sleep(1)  # 等待切换完成
    try:
        # 通过Clash的SOCKS5代理测试连接
        response = requests.get(
            "http://www.google.com",
            proxies={"http": "socks5://127.0.0.1:7891", "https": "socks5://127.0.0.1:7891"},
            timeout=10
        )
        if response.status_code == 200:
            return True
    except:
        return False
    return False

# 启动Clash
subprocess.Popen(["clash", "-f", "config.yaml"])
time.sleep(5)  # 等待Clash启动

# 读取配置文件中的节点
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)
nodes = {p["name"]: p for p in config["proxies"]}

# 测试节点并保存有效节点
valid_nodes = []
with open("data/ss.txt", "r") as f:
    raw_nodes = {i: line.strip() for i, line in enumerate(f.readlines())}
for node_name in nodes.keys():
    if test_node(node_name):
        # 查找原始URI
        for i, raw in raw_nodes.items():
            if node_name in raw or node_name.startswith(f"ss-{raw.split('@')[1].split(':')[0]}"):
                valid_nodes.append(raw)
                break

# 保存到data/sp.txt
with open("data/sp.txt", "w") as f:
    f.write("\n".join(valid_nodes))
