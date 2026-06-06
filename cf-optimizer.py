import requests
import json
import sys
import urllib3
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 禁用 HTTPS 告警
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 建议的测试 IP 列表 (可根据需求扩展)
TARGET_IPS = [
    '104.16.0.1', '104.17.0.1', '104.18.0.1', '104.19.0.1',
    '172.64.0.1', '172.66.0.1', '172.67.0.1',
    '188.114.96.1', '103.21.244.1'
]

def check_ip(ip):
    """探活并计算延迟"""
    url = f"https://{ip}/cdn-cgi/trace"
    headers = {
        "Host": "www.cloudflare.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    latencies = []
    colo = "Unknown"
    
    # 连续测试 3 次取平均值，减小误差
    for _ in range(3):
        try:
            start = time.perf_counter()
            r = requests.get(url, headers=headers, timeout=5, verify=False)
            if r.status_code == 200 and "colo=" in r.text:
                latencies.append((time.perf_counter() - start) * 1000)
                if colo == "Unknown":
                    colo = r.text.split("colo=")[1].split("\n")[0]
        except:
            pass
        time.sleep(0.3)
    
    if not latencies:
        return None
        
    avg_latency = sum(latencies) / len(latencies)
    # 计算健康分：基准 100 分，延迟每超过 1ms 扣 0.2 分，最低 0 分
    score = max(0, 100 - (avg_latency * 0.2))
    
    return {
        "ip": ip,
        "latency": round(avg_latency, 2),
        "score": round(score, 2),
        "colo": colo
    }

def main():
    results = []
    print(f"开始筛选，目标 IP: {len(TARGET_IPS)}")
    
    # 使用线程池并发探活，设置总超时 30 秒
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_ip, ip): ip for ip in TARGET_IPS}
        for future in as_completed(futures, timeout=30):
            res = future.result()
            if res:
                results.append(res)
    
    # 按健康分从高到低排序
    results.sort(key=lambda x: x['score'], reverse=True)
    
    # 输出 JSON 文件
    output = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(results),
        "data": results
    }
    
    with open('results/latest.json', 'w') as f:
        json.dump(output, f, indent=2)
        
    print(f"筛选完成，共找到 {len(results)} 个有效节点。")

if __name__ == "__main__":
    main()
