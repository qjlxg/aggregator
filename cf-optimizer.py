import requests, urllib3, base64, time

# 禁用 HTTPS 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 你的节点信息基础配置
UUID = "82d277fb-db97-4daf-a071-c88a10e4393e"
DOMAIN = "and.qjlxg.workers.dev"
PATH = "/82d277fb-db97-4daf-a071-c88a10e4393e"

ips = ['162.159.192.1', '162.159.193.1', '162.159.195.1', '162.159.196.1']
valid_ips = []

print("正在测速...")

# 1. 测速与筛选
for ip in ips:
    try:
        start = time.time()
        # 必须带上正确的 Host 和 UA，否则 CF 会重置连接
        r = requests.get(
            f"https://{ip}/cdn-cgi/trace",
            headers={"Host": DOMAIN, "User-Agent": "Mozilla/5.0"},
            timeout=3, verify=False
        )
        cost = int((time.time() - start) * 1000)
        
        if r.status_code == 200 and "colo=" in r.text:
            valid_ips.append((cost, ip))
            print(f"成功: {ip} | 延迟: {cost}ms")
    except Exception as e:
        print(f"失败: {ip} | {e}")

# 2. 排序并取前 3 个
valid_ips.sort()
top_ips = [item[1] for item in valid_ips[:3]] or ips[:3]

# 3. 生成订阅链接 (VLESS over WS+TLS 标准格式)
sub_links = ""
for ip in top_ips:
    # 构造标准 VLESS 链接
    link = f"vless://{UUID}@{ip}:443?security=tls&sni={DOMAIN}&fp=random&type=ws&host={DOMAIN}&path={PATH}#CF-优选-{ip}"
    sub_links += link + "\n"

# 4. 关键：Base64 编码 (所有客户端识别的订阅标准)
encoded_sub = base64.b64encode(sub_links.encode()).decode()

with open("sub.yaml", "w") as f:
    f.write(encoded_sub)

print(f"生成成功，共 {len(top_ips)} 个节点。")
