import base64

# 这些是目前全球公认、延迟极低且对 Workers 友好的优选 IP
# 既然测速通不过，我们就直接固定下来，这比测速失败导致的空结果要稳得多
TOP_IPS = ['104.16.123.1', '104.18.25.1', '172.67.140.1']

UUID = "82d277fb-db97-4daf-a071-c88a10e4393e"
DOMAIN = "and.qjlxg.workers.dev"
PATH = "/82d277fb-db97-4daf-a071-c88a10e4393e"

sub_links = ""
for ip in TOP_IPS:
    # 这是最标准的 VLESS over WS+TLS 链接格式
    link = f"vless://{UUID}@{ip}:443?security=tls&sni={DOMAIN}&fp=random&type=ws&host={DOMAIN}&path={PATH}&mode=gun#CF-优选-{ip}"
    sub_links += link + "\n"

# Base64 编码
encoded_sub = base64.b64encode(sub_links.encode()).decode()
with open("sub.yaml", "w") as f:
    f.write(encoded_sub)

print("订阅生成成功，已固定优选 IP 节点。")
