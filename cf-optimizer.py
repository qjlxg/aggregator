import ipaddress
import random
import time
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

# ======================
# 默认备用 IP
# ======================
DEFAULT_IPS = [
    '104.16.0.1',
    '104.17.0.1',
    '172.64.0.1',
    '104.18.25.1',
    '172.64.52.206',
    '172.64.53.221',
    '104.17.146.56',
]

# ======================
# Cloudflare 官方网段 (去掉错误的 1.0.0.0/8)
# ======================
CF_RANGES = [
    "104.16.0.0/12",
    "172.64.0.0/13",
    "162.158.0.0/15",
    "162.159.0.0/16",
    "188.114.96.0/20",
    "141.101.64.0/18",
    "198.41.128.0/17",
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
]

# ======================
# TCP 存活检查
# ======================
def tcp_check(ip, port=443, timeout=1):
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        s.close()
        return True
    except:
        return False

# ======================
# 随机生成 CF 官方 IP
# ======================
def generate_cf_ips(per_range=10):
    ips = set()
    for cidr in CF_RANGES:
        net = ipaddress.ip_network(cidr)
        for _ in range(per_range):
            ip = str(net.network_address + random.randint(1, net.num_addresses - 2))
            ips.add(ip)
    return list(ips)

# ======================
# 测试 IP 延迟 + Colo
# ======================
def check_ip(ip):
    try:
        start = time.time()
        with httpx.Client(
            verify=False,
            timeout=5,
            http2=True,
            headers={"Host": "cloudflare.com"}
        ) as client:
            r = client.get(f"https://{ip}/cdn-cgi/trace", headers={"Host": "cloudflare.com"})
        latency = int((time.time() - start) * 1000)
        if "colo=" in r.text:
            colo = None
            for line in r.text.splitlines():
                if line.startswith("colo="):
                    colo = line.split("=")[1].strip()
                    break
            return {"ip": ip, "latency": latency, "colo": colo}
    except:
        return None

# ======================
# 主程序
# ======================
def main():
    # 1️⃣ 生成候选 IP
    candidates = set(DEFAULT_IPS + generate_cf_ips(20))
    print(f"[INFO] 候选 IP 数量: {len(candidates)}")

    # 2️⃣ TCP 预筛选
    print("[INFO] 正在进行 TCP 存活检测 ...")
    alive_ips = [ip for ip in candidates if tcp_check(ip)]
    print(f"[INFO] 存活 IP 数量: {len(alive_ips)}")

    # 3️⃣ 并发 HTTPS 检测
    print("[INFO] 正在测速 COLO 和延迟 ...")
    results = []
    with ThreadPoolExecutor(max_workers=100) as executor:
        futures = {executor.submit(check_ip, ip): ip for ip in alive_ips}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)
                print(f"[OK] {res['ip']:15} {res['latency']:4}ms {res['colo']}")

    if not results:
        print("[WARN] 没有检测到有效 IP，使用默认备用库")
        results = [{"ip": ip, "latency": 9999, "colo": "fallback"} for ip in DEFAULT_IPS]

    # 4️⃣ Colo 优化: 每个 colo 保留 2 个最低延迟
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

    # 5️⃣ 写入文件
    with open("candidate_ips.txt", "w") as f:
        for item in optimized_results:
            f.write(item['ip'] + "\n")

    with open("candidate_ips_detail.txt", "w") as f:
        for item in optimized_results:
            f.write(f"{item['ip']},{item['latency']}ms,{item['colo']}\n")

    # 6️⃣ 输出 TOP20
    print("\n===== TOP 20 COLO 优化 IP =====")
    for item in optimized_results[:20]:
        print(f"{item['ip']:15} {item['latency']:4}ms {item['colo']}")
    print(f"\n最终存活 IP 数量: {len(optimized_results)}")

if __name__ == "__main__":
    main()