import requests
import base64
import os
import json
import re

def get_github_file_content(repo_api_url, bot_token):
    headers = {
        "Authorization": f"token {bot_token}",
        "Accept": "application/vnd.github.v3.raw"
    }
    try:
        response_json = requests.get(repo_api_url, headers={"Authorization": f"token {bot_token}", "Accept": "application/vnd.github.v3+json"}, timeout=20)
        response_json.raise_for_status()
        file_data = response_json.json()
        
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
    headers = {
        "Authorization": f"token {bot_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    encoded_new_content = base64.b64encode(new_content.encode('utf-8')).decode('utf-8')

    data = {
        "message": commit_message,
        "content": encoded_new_content,
        "sha": file_sha
    }
    
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
    combined_text = ""
    processed_count = 0
    successful_urls = []

    EXCLUDE_KEYWORDS = [
        "cdn.jsdelivr.net", "statically.io", "googletagmanager.com",
        "www.w3.org", "fonts.googleapis.com", "schemes.ogf.org", "clashsub.net", 
        "t.me", "api.w.org",
        "html", "css", "js", "ico", "png", "jpg", "jpeg", "gif", "svg", "webp", "xml", "json", "txt",
        "google-analytics.com", "cloudflare.com/cdn-cgi/", "gstatic.com", "googleapis.com",
        "disqus.com", "gravatar.com", "s.w.org",
        "amazon.com", "aliyuncs.com", "tencentcos.cn",
        "cdn.bootcss.com", "cdnjs.cloudflare.com",
        "bit.ly", "tinyurl.com", "cutt.ly", "shorturl.at", "surl.li", "suo.yt", "v1.mk",
        "youtube.com", "facebook.com", "twitter.com", "weibo.com",
        "mail.google.com", "docs.google.com",
        "microsoft.com", "apple.com", "baidu.com", "qq.com",
        ".woff", ".woff2", ".ttf", ".otf", ".eot",
        ".zip", ".rar", ".7z", ".tar.gz", ".exe", ".dmg", ".apk",
        "/assets/", "/static/", "/images/", "/scripts/", "/styles/", "/fonts/",
        "robots.txt", "sitemap.xml", "favicon.ico",
        "rss", "atom",
        "/LICENSE", "/README.md", "/CHANGELOG.md",
        ".git", ".svn",
        "swagger-ui.html", "openapi.json"
    ]

    PROXY_PREFIXES = [
        "vmess://", "ss://", "trojan://", "vless://", "clash:", "proxies:",
        "hy://", "hy2://", "ssr://", "tuic://", "warp://", "hysteria://",
        "hysteria2://", "shadowsocks:"
    ]

    for url in urls:
        url = url.strip()
        if not url:
            continue

        if any(keyword in url for keyword in EXCLUDE_KEYWORDS):
            print(f"跳过非订阅链接 (根据关键字过滤): {url}")
            continue
            
        print(f"正在处理链接: {url}")
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            content = response.content

            print(f"  --- URL: {url} 下载内容大小: {len(content)} 字节 ---")

            decoded_content = ""
            is_valid_subscription = False

            def contains_proxy_prefix(text):
                return any(prefix in text for prefix in PROXY_PREFIXES)

            def lines_are_all_urls(text):
                lines = text.strip().split('\n')
                if not lines:
                    return False
                return all(line.strip().startswith("http://") or line.strip().startswith("https://") for line in lines if line.strip()) and len(lines) > 1

            try:
                decoded_content = content.decode('utf-8')
                print(f"  --- URL: {url} 成功解码为 UTF-8 ---")
                
                if len(decoded_content.strip()) > 0 and len(decoded_content.strip()) % 4 == 0 and re.fullmatch(r'[A-Za-z0-9+/=]*', decoded_content.strip()):
                    try:
                        temp_decoded = base64.b64decode(decoded_content.strip()).decode('utf-8')
                        if contains_proxy_prefix(temp_decoded) or lines_are_all_urls(temp_decoded):
                            decoded_content = temp_decoded
                            is_valid_subscription = True
                            print(f"  --- URL: {url} 额外 Base64 解码并识别为有效订阅 ---")
                        else:
                            print(f"  --- URL: {url} Base64 解码成功，但内容不符合已知订阅格式，视为非订阅。---")
                    except (base64.binascii.Error, UnicodeDecodeError) as base64_decode_err:
                        print(f"  --- URL: {url} 看起来像Base64但解码失败 ({base64_decode_err})，按明文处理 ---")
                
                if not is_valid_subscription and (contains_proxy_prefix(decoded_content) or lines_are_all_urls(decoded_content)):
                    is_valid_subscription = True
                    print(f"  --- URL: {url} 识别为明文/YAML 格式的有效订阅 ---")
                elif not is_valid_subscription:
                    print(f"  --- URL: {url} UTF-8 解码成功，但内容不符合已知订阅格式，视为非订阅。---")


            except UnicodeDecodeError:
                print(f"  --- URL: {url} 尝试 UTF-8 解码失败，尝试 Base64 解码 ---")
                try:
                    cleaned_content = content.strip()
                    decoded_content = base64.b64decode(cleaned_content).decode('utf-8')
                    print(f"  --- URL: {url} 成功解码 Base64 内容并转为 UTF-8 ---")
                    if contains_proxy_prefix(decoded_content) or lines_are_all_urls(decoded_content):
                        is_valid_subscription = True
                        print(f"  --- URL: {url} Base64 解码并识别为有效订阅 ---")
                    else:
                        print(f"  --- URL: {url} Base64 解码成功，但内容不符合已知订阅格式，视为非订阅。---")

                except (base64.binascii.Error, UnicodeDecodeError) as decode_err:
                    print(f"  --- URL: {url} 尝试 Base64 解码或转为 UTF-8 失败: {decode_err} ---")
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

            
            if decoded_content and is_valid_subscription:
                cleaned_decoded_content = decoded_content.strip().lower()
                if cleaned_decoded_content.startswith("<!doctype html>") or cleaned_decoded_content.startswith("<html"):
                    print(f"  --- URL: {url} 返回的内容似乎是完整的 HTML 页面，跳过追加。---")
                else:
                    combined_text += decoded_content + "\n"
                    processed_count += 1
                    successful_urls.append(url)
            elif not is_valid_subscription:
                print(f"  --- URL: {url} 内容未识别为有效订阅，跳过追加。---")
            else:
                print(f"  --- URL: {url} 未能解码出有效文本内容，跳过追加。---")

        except requests.exceptions.RequestException as e:
            print(f"从 URL 获取数据失败: {url}，原因: {e}")
        except Exception as e:
            print(f"处理 URL {url} 时发生意外错误: {e}")

    print(f"成功处理并聚合了 {processed_count} 个订阅内容。")
    return combined_text, successful_urls

def main():
    bot_token = os.environ.get("BOT")
    url_list_repo_api = os.environ.get("URL_LIST_REPO_API")
    
    try:
        parts = url_list_repo_api.split('/')
        owner = parts[4]
        repo_name = parts[5]
        file_path_in_repo = '/'.join(parts[7:])
    except IndexError:
        print("错误：URL_LIST_REPO_API 格式不正确。请确保它是 GitHub API 的文件内容链接。")
        exit(1)

    repo_contents_api_base = f"https://api.github.com/repos/{owner}/{repo_name}/contents"

    if not bot_token or not url_list_repo_api:
        print("错误：环境变量 BOT 或 URL_LIST_REPO_API 未设置！")
        print("请在 GitHub Actions secrets/variables 中正确设置了这些变量。")
        exit(1)

    print("正在从 GitHub 获取 URL 列表及其 SHA...")
    url_content, url_file_sha = get_github_file_content(url_list_repo_api, bot_token)

    if url_content is None or url_file_sha is None:
        print("无法获取 URL 列表或其 SHA，脚本终止。")
        exit(1)

    urls = url_content.strip().split('\n')
    print(f"从 GitHub 获取到 {len(urls)} 个订阅链接。")

    combined_base64_text, successful_urls = fetch_and_decode_urls(urls)

    final_base64_encoded = base64.b64encode(combined_base64_text.encode('utf-8')).decode('utf-8')

    with open("base64.txt", "w") as f:
        f.write(final_base64_encoded)
    print("Base64 编码内容已成功写入 base64.txt")

    new_url_list_content = "\n".join(sorted(list(set(successful_urls))))
    
    if new_url_list_content.strip() != url_content.strip():
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
