import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 你的目标 IP 段
ips = ['104.16.0.1', '172.64.0.1', '188.114.96.1']
valid_ips = []

for ip in ips:
    try:
        # 只检查连通性，最简单的逻辑
        r = requests.get(f"https://{ip}/cdn-cgi/trace", timeout=3, verify=False)
        if r.status_code == 200:
            valid_ips.append(ip)
    except:
        pass

# 直接保存文本
with open('candidate_ips.txt', 'w') as f:
    f.write('\n'.join(valid_ips))
