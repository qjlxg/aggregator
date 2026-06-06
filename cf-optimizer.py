import requests, urllib3, yaml, time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 待测试的优选 IP 池
ips = ['104.16.0.1', '104.17.0.1', '104.18.0.1', '172.64.0.1', '172.66.0.1', '188.114.96.1']
valid_ips = []

for ip in ips:
    try:
        start = time.time()
        r = requests.get(
            f"https://{ip}/cdn-cgi/trace",
            headers={"Host": "cloudflare.com", "User-Agent": "Mozilla/5.0"},
            timeout=3, verify=False
        )
        cost = int((time.time() - start) * 1000)
        if r.status_code == 200 and "colo=" in r.text:
            valid_ips.append((cost, ip))
    except: continue

valid_ips.sort()
top_ips = [ip for _, ip in valid_ips[:3]] or ips[:3] # 兜底逻辑

# 生成 Clash 订阅格式 (YAML)
config = {"proxies": []}
for i, ip in enumerate(top_ips):
    config["proxies"].append({
        "name": f"CF-最优-{i+1}-{ip}",
        "type": "vless",
        "server": ip,
        "port": 443,
        "uuid": "82d277fb-db97-4daf-a071-c88a10e4393e",
        "tls": True,
        "sni": "and.qjlxg.workers.dev",
        "ws-opts": {"path": "/82d277fb-db97-4daf-a071-c88a10e4393e", "headers": {"Host": "and.qjlxg.workers.dev"}}
    })

with open("sub.yaml", "w") as f:
    yaml.dump(config, f, sort_keys=False)
