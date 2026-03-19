import os
import requests
import base64
import re
from urllib.parse import urlparse

def decode_base64(data):
    """通用的 Base64 解码，支持多种不规范格式"""
    if not data: return ""
    data = data.strip()
    try:
        # 移除干扰字符并补齐长度
        clean_data = re.sub(r'[^A-Za-z0-9+/=]', '', data)
        missing_padding = len(clean_data) % 4
        if missing_padding:
            clean_data += '=' * (4 - missing_padding)
        return base64.b64decode(clean_data).decode('utf-8', errors='ignore')
    except:
        return ""

def fetch_and_extract(url):
    """获取订阅内容并提取所有完整 URI"""
    try:
        headers = {'User-Agent': 'v2rayN/6.23 sub_parser_bot'}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200: return []
        
        content = resp.text.strip()
        # 尝试解码：如果内容不包含 :// 但看起来像 base64，则先解码
        if "://" not in content:
            decoded = decode_base64(content)
            if decoded: content = decoded

        # 正则匹配：匹配从协议头开始，直到遇到不可见字符或特定结束符
        # 确保捕获完整的 vmess://..., vless://... 等
        pattern = r'(?:vmess|vless|ss|ssr|trojan|hysteria2|hy2|tuic|socks|http|https)://[^\s\'"<>]+'
        return re.findall(pattern, content, re.IGNORECASE)
    except Exception:
        return []

def main():
    
    raw_links = os.environ.get('LINK', '').strip().split('\n')
    links = [l.strip() for l in raw_links if l.strip()]
    
    all_uris = []
    print(f"开始处理 {len(links)} 个订阅源...")

    for idx, link in enumerate(links):
       
        domain = urlparse(link).netloc or f"Source_{idx+1}"
        print(f"[{idx+1}/{len(links)}] 正在抓取: {domain}")
        
        uris = fetch_and_extract(link)
        all_uris.extend(uris)
        print(f"   - 提取到 {len(uris)} 个节点")

    # 去重
    unique_uris = sorted(list(set(all_uris)))
    
    # 确保目录存在
    os.makedirs('data', exist_ok=True)

    # 1. 保存明文 nodes.txt
    with open('data/nodes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(unique_uris))

    # 2. 保存 Base64 v2ray.txt
    with open('data/v2ray.txt', 'w', encoding='utf-8') as f:
        combined = '\n'.join(unique_uris)
        b64_content = base64.b64encode(combined.encode('utf-8')).decode('utf-8')
        f.write(b64_content)

    print(f"处理完成！总计有效节点: {len(unique_uris)}")

if __name__ == "__main__":
    main()
