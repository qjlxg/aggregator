import requests, urllib3, base64, time
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
import ssl

# 1. 配置参数
UUID = "82d277fb-db97-4daf-a071-c88a10e4393e"
DOMAIN = "and.qjlxg.workers.dev"
PATH = "/82d277fb-db97-4daf-a071-c88a10e4393e"
# 使用更广的 IP 段，包含 104 和 162 开头
IPS = [
    '104.16.0.1', '104.17.0.1', '104.18.0.1', 
    '162.159.192.1', '162.159.193.1', '162.159.195.1'
]

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 2. 强力 SSL 适配器（解决握手失败）
class HostHeaderSSLAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = PoolManager(
            num_pools=connections, maxsize=maxsize, block=block,
            ssl_version=ssl.PROTOCOL_TLSv1_2
        )

# 3. 测速逻辑
valid_ips = []
session = requests.Session()
session.mount("https://", HostHeaderSSLAdapter())

print("正在进行深度测速...")
for ip in IPS:
    try:
        start = time.time()
        # 核心：必须带 Host 头，且 URL 直接用 IP
        r = session.get(
            f"https://{ip}/cdn-cgi/trace",
            headers={"Host": DOMAIN, "User-Agent": "Mozilla/5.0"},
            timeout=5, verify=False
        )
        if r.status_code == 200 and "colo=" in r.text:
            cost = int((time.time() - start) * 1000)
            valid_ips.append((cost, ip))
            print(f"成功: {ip} | 延迟: {cost}ms")
    except Exception as e:
        print(f"失败: {ip}")

# 4. 生成订阅内容
valid_ips.sort()
top_ips = [item[1] for item in valid_ips[:3]] or IPS[:3]

sub_links = ""
for ip in top_ips:
    # 使用完全匹配的 VLESS 参数，适配 NekoBox/Clash/Sing-box
    link = f"vless://{UUID}@{ip}:443?encryption=none&security=tls&sni={DOMAIN}&fp=random&type=ws&host={DOMAIN}&path={PATH}&mode=gun#CF-优选-{ip}"
    sub_links += link + "\n"

# 5. Base64 编码并保存
encoded_sub = base64.b64encode(sub_links.encode()).decode()
with open("sub.yaml", "w") as f:
    f.write(encoded_sub)

print(f"生成成功，共 {len(top_ips)} 个节点。")
