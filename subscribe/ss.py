
import requests
from urllib.parse import urlparse
import base64

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Encoding': 'gzip, deflate'
}

# 配置参数
MAX_SUCCESS = 99999  # 需要获取的有效内容数量
TIMEOUT = 256      # 单次请求超时时间（秒）
OUTPUT_FILE = 'data/ss.txt'

def is_valid_url(url):
    """验证URL格式是否合法"""
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False

# 获取原始URL列表
sub_all_clash_url = 'https://raw.githubusercontent.com/qjlxg/aggregator/refs/heads/main/data/valid_links.txt'
try:
    response = requests.get(sub_all_clash_url, headers=headers, timeout=256)
    response.raise_for_status()
    raw_urls = response.text.splitlines()
    print(f"原始列表包含 {len(raw_urls)} 个URL")
except Exception as e:
    print(f"获取URL列表失败: {e}")
    exit()

# 预处理URL列表
valid_urls = [url.strip() for url in raw_urls if is_valid_url(url.strip())]
print(f"经过格式验证的有效URL数量：{len(valid_urls)}")

success_count = 0
processed_count = 0

with open(OUTPUT_FILE, 'w', encoding='utf-8') as out_file:
    for url in valid_urls:
                 
        processed_count += 1
        
        try:
            # 显示智能进度（每10个或最后5个显示）
            if processed_count % 10 == 0 :
                print(f"[进度] 已处理 {processed_count} 个 | 成功 {success_count} 个 ")
            
            resp = requests.get(url, headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
                    
            # 内容有效性检查（至少包含10个可打印字符，且不包含“DOMAIN”字符串）
            if len(resp.text.strip()) < 10 or "DOMAIN" in resp.text or "port" in resp.text or "proxies" in resp.text:
                raise ValueError("内容过短或包含DOMAIN字符串")
                
            # 编码检测
            resp.encoding = resp.apparent_encoding
            
            # 写入文件
            #out_file.write(f"\n\n{'=' * 20}\n")
            #out_file.write(f"\n\n")
            #out_file.write(f"# 成功序号: {success_count+1} | 原始序号: {raw_urls.index(url)+1}\n")
            #out_file.write(f"# URL: {url}\n")
            #out_file.write(f"{'=' * 20}\n\n")
            #out_file.write(resp.text)
            # 在写入文件之前，对 resp.text 进行 Base64 解码
            try:
                decoded_content = base64.b64decode(resp.text).decode('utf-8')  # 解码并转换为字符串
                out_file.write(decoded_content)  # 写入解码后的内容
            except base64.binascii.Error as e:
                print(f"Base64 解码失败: {e}")
                continue  # 跳过解码失败的网页
            except UnicodeDecodeError as e:
                print(f"解码后内容无法转换为 UTF-8 字符串: {e}")
                continue  # 跳过无法解码的网页            
                        
            success_count += 1
            
        except requests.exceptions.RequestException as e:
            continue  # 静默跳过网络错误
        except Exception as e:
            continue  # 跳过其他所有异常

# 最终结果报告
print("\n" + "=" * 50)
print(f"最终结果：")
print(f"处理URL总数：{processed_count}")
print(f"成功获取内容数：{success_count}")
print(f"有效内容率：{success_count/processed_count:.1%}")

    
print(f"结果文件已保存至：{OUTPUT_FILE}")
