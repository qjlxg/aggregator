import requests
import base64
import os
import json
import re

def get_github_file_content(repo_api_url, bot_token):
    """
    从 GitHub 仓库获取指定文件的内容。
    Args:
        repo_api_url (str): GitHub 文件内容的 API URL (通常是 raw.githubusercontent.com 链接，但修改文件需要 api.github.com 链接)。
        bot_token (str): GitHub Personal Access Token (PAT)。
    Returns:
        tuple: (文件内容str, 文件SHA值str) 或 (None, None)。
    """
    headers = {
        "Authorization": f"token {bot_token}",
        "Accept": "application/vnd.github.v3.raw"
    }
    try:
        # 为了获取文件 SHA (用于更新文件)，我们需要使用 GitHub API 的 JSON 格式响应
        # 假设 repo_api_url 已经是类似 https://api.github.com/repos/OWNER/REPO/contents/PATH 的形式
        response_json = requests.get(repo_api_url, headers={"Authorization": f"token {bot_token}", "Accept": "application/vnd.github.v3+json"}, timeout=20)
        response_json.raise_for_status()
        file_data = response_json.json()
        
        # 文件内容是 base64 编码的
        content_base64 = file_data['content']
        decoded_content = base64.b64decode(content_base64).decode('utf-8')
        file_sha = file_data['sha']
        
        return decoded_content, file_sha
    except requests.exceptions.RequestException as e:
        print(f"从 GitHub 获取文件失败: {repo_api_url}，原因: {e}")
        return None, None
    except Exception as e:
        print(f"解析 GitHub API 响应失败: {e}")
        return None, None

def update_github_file_content(repo_api_url, bot_token, file_path, new_content, file_sha, commit_message):
    """
    更新 GitHub 仓库中的文件内容。
    Args:
        repo_api_url (str): GitHub API 的仓库内容 URL (例如: https://api.github.com/repos/OWNER/REPO/contents/)
        bot_token (str): GitHub Personal Access Token (PAT)。
        file_path (str): 要更新的文件在仓库中的路径 (例如: data/url.txt)。
        new_content (str): 更新后的文件内容。
        file_sha (str): 文件的当前 SHA 值 (用于乐观锁，防止冲突)。
        commit_message (str): 提交消息。
    Returns:
        bool: 更新是否成功。
    """
    headers = {
        "Authorization": f"token {bot_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 编码新内容为 base64
    encoded_new_content = base64.b64encode(new_content.encode('utf-8')).decode('utf-8')

    data = {
        "message": commit_message,
        "content": encoded_new_content,
        "sha": file_sha # 必须提供文件的当前 SHA
    }
    
    # 构建完整的 API URL
    full_api_url = f"{repo_api_url}/{file_path}"
    
    try:
        response = requests.put(full_api_url, headers=headers, json=data, timeout=20)
        response.raise_for_status()
        print(f"成功更新 GitHub 文件: {file_path}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"更新 GitHub 文件失败: {file_path}，原因: {e.response.text if e.response else e}")
        return False

def fetch_and_decode_urls(urls):
    """
    遍历 URL 列表，获取内容并尝试解码。
    Args:
        urls (list): 包含订阅链接的列表。
    Returns:
        tuple: (所有成功解码内容的组合字符串, 成功处理的原始 URL 列表)
    """
    combined_text = ""
    processed_count = 0
    successful_urls = [] # 用于存储成功获取并被识别为有效订阅内容的 URL

    # 扩展过滤列表，增加更多常见非订阅/静态资源/网页链接
    # 移除了 "github.com" 和 "drive.google.com"
    EXCLUDE_KEYWORDS = [
        "cdn.jsdelivr.net", "statically.io", "googletagmanager.com",
        "www.w3.org", "fonts.googleapis.com", "schemes.ogf.org", "clashsub.net", 
        "t.me", "api.w.org", # Telegram 链接和 WordPress API
        "html", "css", "js", "ico", "png", "jpg", "jpeg", "gif", "svg", "webp", "xml", "json", "txt", # 常见静态文件扩展名
        "google-analytics.com", "cloudflare.com/cdn-cgi/", "gstatic.com", "googleapis.com", # 常见CDN、统计、谷歌服务
        "disqus.com", "gravatar.com", "s.w.org", # 评论系统、头像、WordPress相关
        "amazon.com", "aliyuncs.com", "tencentcos.cn", # 常见云存储/CDN域名
        "cdn.bootcss.com", "cdnjs.cloudflare.com", # 常见前端CDN
        "bit.ly", "tinyurl.com", "cutt.ly", "shorturl.at", "surl.li", "suo.yt", "v1.mk", # 常见短链接服务
        "youtube.com", "facebook.com", "twitter.com", "weibo.com", # 社交媒体
        "mail.google.com", "docs.google.com", # 谷歌应用 (drive.google.com 已移除)
        "microsoft.com", "apple.com", "baidu.com", "qq.com", # 大型公司官网
        ".woff", ".woff2", ".ttf", ".otf", ".eot", # 字体文件
        ".zip", ".rar", ".7z", ".tar.gz", ".exe", ".dmg", ".apk", # 压缩包和可执行文件
        "/assets/", "/static/", "/images/", "/scripts/", "/styles/", "/fonts/", # 常见资源路径
        "robots.txt", "sitemap.xml", "favicon.ico", # 网站标准文件
        "rss", "atom", # 订阅阅读器可能用的RSS/Atom
        "/LICENSE", "/README.md", "/CHANGELOG.md", # 项目文档
        ".git", ".svn", # 版本控制系统文件
        "swagger-ui.html", "openapi.json" # API文档
    ]

    # 定义所有已知的代理类型前缀
    PROXY_PREFIXES = [
        "vmess://", "ss://", "trojan://", "vless://", "clash:", "proxies:",
        "hy://", "hy2://", "ssr://", "tuic://", "warp://", "hysteria://",
        "hysteria2://", "shadowsocks:"
    ]

    for url in urls:
        url = url.strip()
        if not url:
            continue

        # 在处理前进行初步的关键字过滤
        if any(keyword in url for keyword in EXCLUDE_KEYWORDS):
            print(f"跳过非订阅链接 (根据关键字过滤): {url}")
            continue
            
        print(f"正在处理链接: {url}")
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
            content = response.content

            print(f"  --- URL: {url} 下载内容大小: {len(content)} 字节 ---")

            decoded_content = "" # 初始化解码内容
            is_valid_subscription = False # 标记是否是有效订阅内容

            # 辅助函数：检查内容是否包含任何代理前缀
            def contains_proxy_prefix(text):
                return any(prefix in text for prefix in PROXY_PREFIXES)

            # 辅助函数：检查多行文本是否都是有效的 HTTP/HTTPS URL
            def lines_are_all_urls(text):
                lines = text.strip().split('\n')
                if not lines:
                    return False
                # 检查所有非空行是否都是以 http:// 或 https:// 开头的 URL
                return all(line.strip().startswith("http://") or line.strip().startswith("https://") for line in lines if line.strip()) and len(lines) > 1 # 确保至少有两行，避免单个 URL 误判

            # 尝试 UTF-8 解码
            try:
                decoded_content = content.decode('utf-8')
                print(f"  --- URL: {url} 成功解码为 UTF-8 ---")
                
                # 优先级1: 检查是否是 Base64 编码的订阅 (内容本身是Base64字符串)
                # 必须满足 Base64 编码的长度要求 (是4的倍数) 并且只包含 Base64 字符
                if len(decoded_content.strip()) > 0 and len(decoded_content.strip()) % 4 == 0 and re.fullmatch(r'[A-Za-z0-9+/=]*', decoded_content.strip()):
                    try:
                        temp_decoded = base64.b64decode(decoded_content.strip()).decode('utf-8') # strip() before base64 decode for robust
                        if contains_proxy_prefix(temp_decoded) or lines_are_all_urls(temp_decoded):
                            decoded_content = temp_decoded # 更新为真正解码后的内容
                            is_valid_subscription = True
                            print(f"  --- URL: {url} 额外 Base64 解码并识别为有效订阅 ---")
                        else:
                            print(f"  --- URL: {url} Base64 解码成功，但内容不符合已知订阅格式，视为非订阅。---")
                    except (base64.binascii.Error, UnicodeDecodeError) as base64_decode_err:
                        print(f"  --- URL: {url} 看起来像Base64但解码失败 ({base64_decode_err})，按明文处理 ---")
                
                # 优先级2: 如果不是 Base64 编码的订阅，则按明文/YAML 订阅处理
                # 这里再次检查，避免在前面的 Base64 尝试中误判
                if not is_valid_subscription and (contains_proxy_prefix(decoded_content) or lines_are_all_urls(decoded_content)):
                    is_valid_subscription = True
                    print(f"  --- URL: {url} 识别为明文/YAML 格式的有效订阅 ---")
                elif not is_valid_subscription: # 如果到这里is_valid_subscription还是False，说明不符合任何已知格式
                    print(f"  --- URL: {url} UTF-8 解码成功，但内容不符合已知订阅格式，视为非订阅。---")


            except UnicodeDecodeError:
                print(f"  --- URL: {url} 尝试 UTF-8 解码失败，尝试 Base64 解码 ---")
                try:
                    # 尝试 Base64 解码
                    cleaned_content = content.strip() # 移除首尾空白字符
                    decoded_content = base64.b64decode(cleaned_content).decode('utf-8')
                    print(f"  --- URL: {url} 成功解码 Base64 内容并转为 UTF-8 ---")
                    if contains_proxy_prefix(decoded_content) or lines_are_all_urls(decoded_content):
                        is_valid_subscription = True
                        print(f"  --- URL: {url} Base64 解码并识别为有效订阅 ---")
                    else:
                        print(f"  --- URL: {url} Base64 解码成功，但内容不符合已知订阅格式，视为非订阅。---")

                except (base64.binascii.Error, UnicodeDecodeError) as decode_err:
                    print(f"  --- URL: {url} 尝试 Base64 解码或转为 UTF-8 失败: {decode_err} ---")
                    # 如果 Base64 解码仍然失败，尝试其他常见编码
                    try:
                        decoded_content = content.decode('gbk')
                        print(f"  --- URL: {url} 成功解码 GBK 内容 ---")
                        if contains_proxy_prefix(decoded_content) or lines_are_all_urls(decoded_content):
                            is_valid_subscription = True
                            print(f"  --- URL: {url} GBK 解码并识别为有效订阅 ---")
                        else:
                            print(f"  --- URL: {url} GBK 解码成功，但内容不符合已知订阅格式，视为非订阅。---")
                    except UnicodeDecodeError:
                        decoded_content = content.decode('latin-1', errors='ignore')
                        print(f"警告: 无法将 {url} 的内容解码为 UTF-8、GBK 或 Base64。使用 latin-1 并忽略错误。")
                        # latin-1 通常用于兜底，很少是有效订阅内容，所以这里不设置 is_valid_subscription = True

            
            if decoded_content and is_valid_subscription:
                # 检查内容是否以常见的 HTML 标签开头，如果是，则很可能是一个完整的网页
                # 我们只检查开头，因为订阅内容中可能偶然包含一些HTML片段，但不会以HTML开头
                cleaned_decoded_content = decoded_content.strip().lower()
                if cleaned_decoded_content.startswith("<!doctype html>") or cleaned_decoded_content.startswith("<html"):
                    print(f"  --- URL: {url} 返回的内容似乎是完整的 HTML 页面，跳过追加。---")
                else:
                    combined_text += decoded_content + "\n"
                    processed_count += 1
                    successful_urls.append(url) # 记录成功处理的 URL
            elif not is_valid_subscription:
                print(f"  --- URL: {url} 内容未识别为有效订阅，跳过追加。---")
            else: # decoded_content is empty
                print(f"  --- URL: {url} 未能解码出有效文本内容，跳过追加。---")

        except requests.exceptions.RequestException as e:
            print(f"从 URL 获取数据失败: {url}，原因: {e}")
        except Exception as e:
            print(f"处理 URL {url} 时发生意外错误: {e}")

    print(f"成功处理并聚合了 {processed_count} 个订阅内容。")
    return combined_text, successful_urls

def main():
    # 从环境变量中读取 BOT 和 URL_LIST_REPO_API
    bot_token = os.environ.get("BOT")
    # URL_LIST_REPO_API 应该是一个 GitHub API URL，例如：
    # https://api.github.com/repos/qjlxg/362/contents/data/url.txt
    url_list_repo_api = os.environ.get("URL_LIST_REPO_API")
    
    try:
        parts = url_list_repo_api.split('/')
        owner = parts[4]
        repo_name = parts[5]
        file_path_in_repo = '/'.join(parts[7:]) # data/url.txt
    except IndexError:
        print("错误：URL_LIST_REPO_API 格式不正确。请确保它是 GitHub API 的文件内容链接。")
        exit(1)

    # 用于更新文件的基础 API URL
    repo_contents_api_base = f"https://api.github.com/repos/{owner}/{repo_name}/contents"

    if not bot_token or not url_list_repo_api:
        print("错误：环境变量 BOT 或 URL_LIST_REPO_API 未设置！")
        print("请在 GitHub Actions secrets/variables 中正确设置了这些变量。")
        exit(1) # 退出脚本，表示失败

    # 1. 从 GitHub 获取 URL 列表及其 SHA
    print("正在从 GitHub 获取 URL 列表及其 SHA...")
    url_content, url_file_sha = get_github_file_content(url_list_repo_api, bot_token)

    if url_content is None or url_file_sha is None:
        print("无法获取 URL 列表或其 SHA，脚本终止。")
        exit(1) # 退出脚本，表示失败

    urls = url_content.strip().split('\n')
    print(f"从 GitHub 获取到 {len(urls)} 个订阅链接。")

    # 2. 遍历 URL，获取数据并解码
    combined_base64_text, successful_urls = fetch_and_decode_urls(urls)

    # 3. 将聚合后的内容进行 Base64 编码
    final_base64_encoded = base64.b64encode(combined_base64_text.encode('utf-8')).decode('utf-8')

    # 4. 将 Base64 编码后的内容写入 base64.txt 文件
    with open("base64.txt", "w") as f:
        f.write(final_base64_encoded)
    print("Base64 编码内容已成功写入 base64.txt")

    # 5. 更新 GitHub 上的 url.txt 文件
    new_url_list_content = "\n".join(sorted(list(set(successful_urls)))) # 去重并排序，保持稳定性
    
    # 只有当成功处理的 URL 列表与原始列表不同时才更新
    if new_url_list_content.strip() != url_content.strip(): # strip() 以避免因末尾换行符导致的不必要更新
        print("正在更新 GitHub 上的 url.txt 文件...")
        commit_message = "feat: Update url.txt with valid subscription links (auto-filtered)"
        update_success = update_github_file_content(
            repo_contents_api_base,
            bot_token,
            file_path_in_repo,
            new_url_list_content,
            url_file_sha,
            commit_message
        )
        if update_success:
            print("url.txt 文件已成功更新。")
        else:
            print("更新 url.txt 文件失败。")
    else:
        print("url.txt 文件内容未改变，无需更新。")

if __name__ == "__main__":
    main()
