import requests
import sys
from concurrent.futures import ThreadPoolExecutor

# 配置项
# 增加一些官方常用 CDN IP 段，确保覆盖率
TARGET_IPS = [
    '104.16.0.1', '172.64.0.1', '188.114.96.1', 
    '104.17.0.1', '104.18.0.1', '104.19.0.1',
    '172.66.0.1', '172.67.0.1', '103.21.244.1'
]

def check_ip(ip):
    """
    探活函数：通过访问 CDN 边缘探针检查 IP 是否可用
    """
    url = f"https://{ip}/cdn-cgi/trace"
    headers = {"Host": "www.cloudflare.com"}
    try:
        # 超时设为 3 秒，避免阻塞过多资源
        response = requests.get(url, headers=headers, timeout=3, verify=False)
        if response.status_code == 200:
            return ip
    except Exception:
        return None
    return None

def main():
    print(f"开始筛选，目标 IP 数量: {len(TARGET_IPS)}")
    
    # 使用线程池并发探活，20 并发是 GitHub Actions 容器的最佳平衡点
    valid_ips = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(check_ip, TARGET_IPS))
        
    valid_ips = [ip for ip in results if ip is not None]
    
    # 结果去重与保存
    valid_ips = sorted(list(set(valid_ips)))
    
    if not valid_ips:
        print("错误：未找到可用 IP")
        sys.exit(1)
        
    with open('candidate_ips.txt', 'w') as f:
        f.write('\n'.join(valid_ips))
        
    print(f"筛选完成，共找到 {len(valid_ips)} 个有效 IP 已写入 candidate_ips.txt")

if __name__ == "__main__":
    main()
