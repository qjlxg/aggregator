import requests
import urllib3
import ipaddress
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 默认备用 IP
DEFAULT_IPS = [
    '104.16.0.1',
    '104.17.0.1',
    '172.64.0.1',
    '104.18.25.1',
    '172.64.52.206',
    '172.64.53.221',
    '104.17.146.56',
]

# Cloudflare 官方网段
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

# 获取 ip.164746.xyz
def get_ips_from_api():
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get("https://ip.164746.xyz/ipTop.html", headers=headers, timeout=10)
        if r.status_code == 200 and r.text.strip():
            return [x.strip() for x in r.text.replace("\n", ",").split(",") if x.strip()]
    except:
        pass
    return []

# 随机生成 CF 官方 IP
def generate_cf_ips(per_range=20):
    ips = set()
    for cidr in CF_RANGES:
        net = ipaddress.ip_network(cidr)
        for _ in range(per_range):
            ip = str(net.network_address + random.randint(1, net.num_addresses - 2))
            ips.add(ip)
    return list(ips)

# HTTP 测 colo + 延迟
def check_ip(ip):
    try:
        start = time.time()
        r = requests.get(f"https://{ip}/cdn-cgi/trace", headers={"Host":"cloudflare.com"}, timeout=5, verify=False)
        latency = int((time.time() - start) * 1000)
        if r.status_code == 200 and "colo=" in r.text:
            colo = None
            for line in r.text.splitlines():
                if line.startswith("colo="):
                    colo = line.split("=")[1].strip()
                    break
            return {"ip": ip, "latency": latency, "colo": colo}
    except:
        pass
    return None

# 主程序
def main():
    # 1️⃣ 收集候选 IP
    api_ips = get_ips_from_api()
    candidates = set(api_ips + DEFAULT_IPS)
    if len(candidates) < 50:
        candidates.update(generate_cf_ips(20))
    candidates = list(candidates)
    print(f"待检测 IP 数量: {len(candidates)}")

    # 2️⃣ 并发检测
    results = []
    with ThreadPoolExecutor(max_workers=100) as executor:
        futures = {executor.submit(check_ip, ip): ip for ip in candidates}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)
                print(f"[OK] {res['ip']} {res['latency']}ms {res['colo']}")

    # 3️⃣ 回退处理
    if not results:
        print("没有检测到有效IP，使用默认库")
        results = [{"ip": ip, "latency": 9999, "colo": "fallback"} for ip in DEFAULT_IPS]

    # 4️⃣ Colo 优化：每个 colo 只保留 1~2 个延迟最小的
    colo_map = {}
    for r in sorted(results, key=lambda x: x["latency"]):
        c = r["colo"]
        if c not in colo_map:
            colo_map[c] = [r]
        elif len(colo_map[c]) < 2:
            colo_map[c].append(r)

    optimized_results = []
    for lst in colo_map.values():
        optimized_results.extend(lst)

    optimized_results.sort(key=lambda x: x["latency"])

    # 5️⃣ 保存文件
    with open("candidate_ips.txt", "w") as f:
        for item in optimized_results:
            f.write(item["ip"] + "\n")

    with open("candidate_ips_detail.txt", "w") as f:
        for item in optimized_results:
            f.write(f"{item['ip']},{item['latency']}ms,{item['colo']}\n")

    # 6️⃣ 输出 Top 20
    print("\n===== TOP 20 Colo 优化 IP =====")
    for item in optimized_results[:20]:
        print(f"{item['ip']:15} {item['latency']:4}ms {item['colo']}")

    print(f"\n最终存活 IP 数量: {len(optimized_results)}")

if __name__ == "__main__":
    main()