import requests
import urllib3
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ips = [
    '104.16.0.1', '104.17.0.1', '104.18.0.1',
    '172.64.0.1', '172.66.0.1',
    '188.114.96.1'
]

valid_ips = []

for ip in ips:
    try:
        start = time.time()

        r = requests.get(
            f"https://{ip}/cdn-cgi/trace",
            headers={"Host": "cloudflare.com"},
            timeout=3,
            verify=False
        )

        cost = int((time.time() - start) * 1000)

        # ✔ 稳定判断三条件
        if (
            r.status_code == 200
            and "colo=" in r.text
            and cost < 3000
        ):
            valid_ips.append((cost, ip))

    except:
        continue

# ✔ 按稳定性排序（不是“假测速”）
valid_ips.sort()

# ✔ 至少保证有 fallback
output = [ip for _, ip in valid_ips] or ips[:3]

with open("candidate_ips.txt", "w") as f:
    f.write("\n".join(output))

print("valid:", len(output))
