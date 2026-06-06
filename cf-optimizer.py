import requests, urllib3, time
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 增加更多可能的 CF 节点地址
ips = ['104.16.0.1', '104.17.0.1', '104.18.0.1', '104.19.0.1', '172.64.0.1', '172.66.0.1', '172.67.0.1', '188.114.96.1']
results = []

print(f"开始测试 {len(ips)} 个 IP...")

for ip in ips:
    try:
        start = time.time()
        # 增加 Headers 模拟浏览器，这是最重要的改动
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(f"https://{ip}/cdn-cgi/trace", headers=headers, timeout=5, verify=False)
        if r.status_code == 200 and "colo=" in r.text:
            latency = int((time.time() - start) * 1000)
            results.append((latency, ip))
            print(f"成功: {ip} | 延迟: {latency}ms")
        else:
            print(f"失败: {ip} | 状态码: {r.status_code}")
    except Exception as e:
        print(f"超时/连接错误: {ip} | {e}")

results.sort()

# 如果一个都没找到，写入一条占位信息，防止文件为空
with open('candidate_ips.txt', 'w') as f:
    if results:
        f.write('\n'.join([ip for lat, ip in results]))
    else:
        f.write("# 未发现可用节点，请检查网络或更换 IP 池")
