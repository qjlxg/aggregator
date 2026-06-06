import requests
import urllib3
import time
import ipaddress
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================
# 固定备用库
# =========================
DEFAULT_IPS = [
    '104.16.0.1',
    '104.17.0.1',
    '172.64.0.1',
    '104.18.25.1',
    '172.64.52.206',
    '172.64.53.221',
    '104.17.146.56',
]

# =========================
# Cloudflare 官方网段
# =========================
CF_RANGES = [
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
]

# =========================
# 获取优选IP
# =========================
def get_ips_from_api():
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }

        response = requests.get(
            "https://ip.164746.xyz/ipTop.html",
            timeout=10,
            headers=headers,
        )

        if response.status_code == 200 and response.text.strip():
            ips = [
                x.strip()
                for x in response.text.replace("\n", ",").split(",")
                if x.strip()
            ]

            print(f"接口返回 {len(ips)} 个IP")
            return ips

    except Exception as e:
        print("接口获取失败:", e)

    return []

# =========================
# 随机补充CF IP
# =========================
def generate_cf_ips(per_range=10):
    result = []

    for cidr in CF_RANGES:
        net = ipaddress.ip_network(cidr)

        for _ in range(per_range):
            ip = str(
                net.network_address
                + random.randint(1, net.num_addresses - 2)
            )
            result.append(ip)

    return result

# =========================
# 检测IP
# =========================
def check_ip(ip):
    try:
        start = time.time()

        r = requests.get(
            f"https://{ip}/cdn-cgi/trace",
            headers={
                "Host": "cloudflare.com",
                "User-Agent": "Mozilla/5.0"
            },
            timeout=5,
            verify=False,
        )

        latency = int((time.time() - start) * 1000)

        if (
            r.status_code == 200
            and "colo=" in r.text
        ):
            colo = "unknown"

            for line in r.text.splitlines():
                if line.startswith("colo="):
                    colo = line.split("=")[1]
                    break

            return {
                "ip": ip,
                "latency": latency,
                "colo": colo,
            }

    except:
        pass

    return None

# =========================
# 主程序
# =========================
def main():

    api_ips = get_ips_from_api()

    # API + 默认库
    candidates = set(api_ips)
    candidates.update(DEFAULT_IPS)

    # 如果数量太少自动补充
    if len(candidates) < 50:
        print("优选IP不足，自动补充官方网段")
        candidates.update(generate_cf_ips(20))

    candidates = list(candidates)

    print(f"待检测IP数量: {len(candidates)}")

    results = []

    with ThreadPoolExecutor(max_workers=100) as executor:
        futures = {
            executor.submit(check_ip, ip): ip
            for ip in candidates
        }

        for future in as_completed(futures):
            result = future.result()

            if result:
                results.append(result)

                print(
                    f"[OK] "
                    f"{result['ip']} "
                    f"{result['latency']}ms "
                    f"{result['colo']}"
                )

    if not results:
        print("没有检测到有效IP，回退默认库")
        results = [
            {
                "ip": ip,
                "latency": 9999,
                "colo": "fallback"
            }
            for ip in DEFAULT_IPS
        ]

    results.sort(key=lambda x: x["latency"])

    # 保存全部结果
    with open("candidate_ips.txt", "w") as f:
        for item in results:
            f.write(item["ip"] + "\n")

    # 保存详细结果
    with open("candidate_ips_detail.txt", "w") as f:
        for item in results:
            f.write(
                f"{item['ip']},"
                f"{item['latency']}ms,"
                f"{item['colo']}\n"
            )

    print("\n===== TOP 20 =====")

    for item in results[:20]:
        print(
            f"{item['ip']:15} "
            f"{item['latency']:4}ms "
            f"{item['colo']}"
        )

    print(f"\n最终存活IP数量: {len(results)}")

if __name__ == "__main__":
    main()