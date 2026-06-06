import requests, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ips = ['104.16.0.1', '172.64.0.1', '188.114.96.1', '104.17.0.1', '104.18.0.1']
results = []

for ip in ips:
    try:
        # 使用 timeout 限制单次测试，避免卡死
        start = __import__('time').time()
        r = requests.get(f"https://{ip}/cdn-cgi/trace", timeout=2, verify=False)
        if r.status_code == 200:
            latency = int((__import__('time').time() - start) * 1000)
            results.append((latency, ip))
    except: pass

# 核心：按延迟排序并只存 IP
results.sort() 
with open('candidate_ips.txt', 'w') as f:
    f.write('\n'.join([ip for lat, ip in results[:10]]))
