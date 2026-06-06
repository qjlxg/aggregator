import requests
import sys
import urllib3
from concurrent.futures import ThreadPoolExecutor

# 显式禁用 InsecureRequestWarning，避免告警干扰 Action 状态
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TARGET_IPS = [
    '104.16.0.1', '172.64.0.1', '188.114.96.1', 
    '104.17.0.1', '172.66.0.1', '172.67.0.1', '103.21.244.1'
]

def check_ip(ip):
    # 关键点：Host 头必须正确，否则 CDN 会拒绝响应
    url = f"https://{ip}/cdn-cgi/trace"
    headers = {
        "Host": "www.cloudflare.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=5, verify=False)
        if response.status_code == 200 and "status=200" in response.text:
            return ip
    except Exception:
        return None
    return None

def main():
    print(f"开始筛选，目标 IP 数量: {len(TARGET_IPS)}")
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(check_ip, TARGET_IPS))
        
    valid_ips = [ip for ip in results if ip is not None]
    
    if not valid_ips:
        print("错误：未找到可用 IP (检查网络连通性或 Target IP 有效性)")
        sys.exit(1)
        
    with open('candidate_ips.txt', 'w') as f:
        f.write('\n'.join(valid_ips))
        
    print(f"筛选完成，共找到 {len(valid_ips)} 个有效 IP")

if __name__ == "__main__":
    main()
