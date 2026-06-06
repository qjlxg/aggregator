import socket
import ssl
import ipaddress
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ========== 默认备用 IP ==========
DEFAULT_IPS = [
    '104.16.0.1',
    '104.17.0.1',
    '172.64.0.1',
    '104.18.25.1',
    '172.64.52.206',
    '172.64.53.221',
    '104.17.146.56',
]

# ========== Cloudflare 官方网段 ==========
CF_RANGES = [
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "188.114.96.0/20",
    "162.158.0.0/15",
    "141.101.64.0/18",
    "198.41.128.0/17",
    "173.245.48.0/20",
]

# ========== 获取 ip.164746.xyz ==========
def get_ips_from_api():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        r = requests.get("https://ip.164746.xyz/ipTop.html", headers=headers, timeout=10)
        if r.status_code == 200 and r.text.strip():
            return [x.strip() for x in r.text.replace("\n", ",").split(",") if x.strip()]
    except:
        pass
    return []

# ========== 随机生成 CF 官方 IP ==========
def generate_cf_ips(per_range=20):
    ips = set()
    for cidr in CF_RANGES:
        net = ipaddress.ip_network(cidr)
        for _ in range(per_range):
            ip = str(net.network_address + random.randint(1, net.num_addresses - 2))
            ips.add(ip)
    return list(ips)

# ========== TCP/SNI 探测 ==========
def check_ip(ip, port=443, timeout=3):
    start = time.time()
    try:
        context = ssl.create_default_context()
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname="cloudflare.com"):
                latency = int((time.time() - start) * 1000)
                return {"ip": ip, "latency": latency}
    except:
        return None

# ========== 主程序 ==========
def main():
    api_ips = get_ips_from_api()
    candidates = set(api_ips + DEFAULT_IPS)

    # 如果候选太少自动补充
    if len(candidates) < 50:
        candidates.update(generate_cf_ips(20))

    candidates = list(candidates)
    print(f"待检测 IP 数量: {len(candidates)}")

    results = []
    with ThreadPoolExecutor(max_workers=100) as executor:
        futures = {executor.submit(check_ip, ip): ip for ip in candidates}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)
                print(f"[OK] {res['ip']} {res['latency']}ms")

    if not results:
        print("没有检测到可用 IP，直接使用默认库")
        results = [{"ip": ip, "latency": 9999} for ip in DEFAULT_IPS]

    results.sort(key=lambda x: x["latency"])

    # 写入 candidate_ips.txt
    with open("candidate_ips.txt", "w") as f:
        for item in results:
            f.write(item["ip"] + "\n")

    # 写入详细结果
    with open("candidate_ips_detail.txt", "w") as f:
        for item in results:
            f.write(f"{item['ip']},{item['latency']}ms\n")

    print("\n===== TOP 20 IP =====")
    for item in results[:20]:
        print(f"{item['ip']:15} {item['latency']}ms")

if __name__ == "__main__":
    main()