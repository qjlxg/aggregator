import requests
from urllib.parse import urlparse
import base64

# 请求头
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Encoding': 'gzip, deflate'
}

# 配置参数
MAX_SUCCESS = 99999  # 需要获取的有效内容数量
TIMEOUT = 256        # 单次请求超时时间（秒）
OUTPUT_FILE = 'data/ss.txt'

def is_valid_url(url):
    """验证URL格式是否合法"""
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False

def get_url_list(source_url):
    """从单个源URL获取URL列表"""
    try:
        response = requests.get(source_url, headers=headers, timeout=256)
        response.raise_for_status()
        raw_urls = response.text.splitlines()
        return [url.strip() for url in raw_urls if is_valid_url(url.strip())]
    except Exception as e:
        print(f"获取URL列表失败 ({source_url}): {e}")
        return []

def process_url(url, out_file):
    """处理单个URL，获取内容并写入文件"""
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        
        # 内容有效性检查
        if len(resp.text.strip()) < 10 or "DOMAIN" in resp.text or "port" in resp.text or "proxies" in resp.text:
            raise ValueError("内容过短或包含DOMAIN字符串")
        
        # 尝试Base64解码
        try:
            decoded_content = base64.b64decode(resp.text).decode('utf-8')
        except base64.binascii.Error as e:
            print(f"Base64 解码失败 ({url}): {e}")
            return False
        except UnicodeDecodeError as e:
            print(f"解码后内容无法转换为 UTF-8 字符串 ({url}): {e}")
            return False
        
        # 写入文件
        out_file.write(decoded_content)
        return True
    except requests.exceptions.RequestException as e:
        return False
    except Exception as e:
        return False

# 主程序
source_urls = [
        'https://github.com/qjlxg/aggregator/raw/refs/heads/main/xujw3.txt',
]

# 获取所有有效的URL
all_valid_urls = []
for source_url in source_urls:
    valid_urls = get_url_list(source_url)
    all_valid_urls.extend(valid_urls)

print(f"总共获取到 {len(all_valid_urls)} 个有效URL")

# 处理URL并保存内容
success_count = 0
processed_count = 0

with open(OUTPUT_FILE, 'w', encoding='utf-8') as out_file:
    for url in all_valid_urls:
        processed_count += 1
        
        if process_url(url, out_file):
            success_count += 1
        
        # 显示进度
        if processed_count % 10 == 0:
            print(f"[进度] 已处理 {processed_count} 个 | 成功 {success_count} 个")

# 最终报告
print("\n" + "=" * 50)
print(f"最终结果：")
print(f"处理URL总数：{processed_count}")
print(f"成功获取内容数：{success_count}")
if processed_count > 0:
    print(f"有效内容率：{success_count/processed_count:.1%}")
else:
    print("没有处理任何URL")
print(f"结果文件已保存至：{OUTPUT_FILE}")
