import requests
import urllib3
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 备用库：防止接口失效导致订阅归零
default_ips = ['104.16.0.1', '104.17.0.1', '172.64.0.1', '104.18.25.1', '172.64.52.206', '172.64.53.221','104.17.146.56']

def get_ips():
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get("https://ip.164746.xyz/ipTop.html", timeout=10, headers=headers)
        
        if response.status_code == 200 and response.text.strip():
            print(f"成功从接口获取到 IP: {response.text.strip()}")
            return response.text.replace('\n', '').replace('\r', '').split(',')
        else:
            print(f"接口返回异常，状态码: {response.status_code}")
            return default_ips
    except Exception as e:
        print(f"获取接口失败: {e}")
        return default_ips

ips = get_ips()
valid_ips = []

for ip in ips:
    ip = ip.strip()
    if not ip: continue
    
    try:
        start = time.time()
        # 对 CDN 进行握手校验
        r = requests.get(f"https://{ip}/cdn-cgi/trace", headers={"Host": "cloudflare.com"}, timeout=5, verify=False)
        cost = int((time.time() - start) * 1000)

        if r.status_code == 200 and "colo=" in r.text:
            valid_ips.append(ip)
    except:
        continue

final_ips = valid_ips if valid_ips else default_ips
with open("candidate_ips.txt", "w") as f:
    f.write("\n".join(final_ips))

print(f"最终校验完成，存活 IP 数量: {len(final_ips)}")
