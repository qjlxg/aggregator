import time
import requests
import yaml
import os

# 等待 Clash 启动
def wait_for_clash():
    while True:
        try:
            response = requests.get("http://127.0.0.1:9090/version")
            if response.status_code == 200:
                break
        except:
            pass
        time.sleep(1)

# 启动 Clash 在后台运行
os.system("./clash/clash-linux -f data/clash.yaml &")
wait_for_clash()

# 读取 Clash 配置文件
with open("data/clash.yaml", "r") as f:
    config = yaml.safe_load(f)
proxies_list = config["proxies"]

# 配置代理，使用 Clash 默认的代理端口 7890
proxies = {
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890",
}

available_proxies = []
for proxy in proxies_list:
    # 通过 API 切换到当前代理节点
    requests.put("http://127.0.0.1:9090/proxies/GLOBAL", json={"name": proxy["name"]})

    # 测试 Google
    try:
        response = requests.get("https://www.google.com", proxies=proxies, timeout=30)
        google_ok = response.status_code == 200
    except:
        google_ok = False

    # 测试 YouTube
    try:
        response = requests.get("https://www.youtube.com", proxies=proxies, timeout=30)
        youtube_ok = response.status_code == 200
    except:
        youtube_ok = False

    # 如果两个网站都能访问，则记录该节点
    if google_ok and youtube_ok:
        available_proxies.append(proxy)
    
    # 避免请求过快被封锁
    time.sleep(1)

# 将可用节点写入 data/google.yaml
with open("data/google.yaml", "w") as f:
    yaml.dump({"proxies": available_proxies}, f)

# 停止 Clash 进程
os.system("pkill clash-linux")
