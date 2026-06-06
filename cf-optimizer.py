import base64

# 使用你截图中的真实参数
UUID = "82d277fb-db97-4daf-a071-c88a10e4393e"
DOMAIN = "and.qjlxg.workers.dev"
PATH = "/7ed=2560"  # 你的真实路径
PORT = 80            # 你的真实端口
# 你的节点 Security 为空，意味着不使用 TLS 加密
TLS = "" 

TOP_IPS = ['104.16.123.1', '104.18.25.1', '172.67.140.1']

sub_links = ""
for ip in TOP_IPS:
    # 构造复刻版链接
    # 注意：这里我们去掉了 security=tls，完全模拟你那个“能用”的节点
    link = f"vless://{UUID}@{ip}:{PORT}?type=ws&host={DOMAIN}&path={PATH}#CF-优选-{ip}"
    sub_links += link + "\n"

encoded_sub = base64.b64encode(sub_links.encode()).decode()
with open("sub.yaml", "w") as f:
    f.write(encoded_sub)

print("生成成功！已精准复刻节点参数。")
