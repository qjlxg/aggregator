import requests
import base64
import os
import re

def get_github_file_content(repo_api_url, bot_token):
    """
    从 GitHub 仓库获取指定文件的内容。
    Args:
        repo_api_url (str): GitHub 文件内容的 API URL。
        bot_token (str): GitHub Personal Access Token (PAT)。
    Returns:
        str: 文件内容，如果获取失败则为 None。
    """
    headers = {
        "Authorization": f"token {bot_token}",
        "Accept": "application/vnd.github.v3.raw"
    }
    try:
        response = requests.get(repo_api_url, headers=headers, timeout=20)
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"从 GitHub 获取文件失败: {repo_api_url}，原因: {e}")
        return None

def fetch_and_decode_urls(urls):
    """
    遍历 URL 列表，获取内容并尝试解码。
    Args:
        urls (list): 包含订阅链接的列表。
    Returns:
        str: 所有成功解码内容的组合字符串。
    """
    combined_text = ""
    processed_count = 0

    for url in urls:
        url = url.strip()
        if not url:
            continue

        # 过滤掉常见的非订阅链接
        # 这里你可以根据你的实际需求调整或增加过滤规则
        if any(keyword in url for keyword in [
            "cdn.jsdelivr.net", "statically.io", "googletagmanager.com",
            "www.w3.org", "fonts.googleapis.com", "schemes.ogf.org", "clashsub.net", # 根据日志，这些也是非订阅链接
            "html", "css", "js", "ico", "png", "jpg", "jpeg", "gif", "svg", "webp" # 常见图片和静态文件
        ]):
            print(f"跳过非订阅链接: {url}")
            continue

        print(f"正在处理链接: {url}")
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
            content = response.content

            print(f"  --- URL: {url} 下载内容大小: {len(content)} 字节 ---")
            # 注意：打印原始内容可能包含敏感信息，仅用于调试，生产环境请注释掉
            # print(f"  --- 内容预览 (前100字符): {content[:100].decode('latin-1', errors='ignore')} ---")

            decoded_content = "" # 初始化解码内容

            # 尝试 UTF-8 解码
            try:
                decoded_content = content.decode('utf-8')
                print(f"  --- URL: {url} 成功解码为 UTF-8 ---")
            except UnicodeDecodeError:
                print(f"  --- URL: {url} 尝试 UTF-8 解码失败，尝试 Base64 解码 ---")
                try:
                    # 尝试 Base64 解码
                    # 某些订阅链接返回的内容可能包含不必要的字符（如换行符），需要清理
                    cleaned_content = content.strip() # 移除首尾空白字符
                    decoded_content = base64.b64decode(cleaned_content).decode('utf-8')
                    print(f"  --- URL: {url} 成功解码 Base64 内容并转为 UTF-8 ---")
                except (base64.binascii.Error, UnicodeDecodeError) as decode_err:
                    print(f"  --- URL: {url} 尝试 Base64 解码或转为 UTF-8 失败: {decode_err} ---")
                    # 如果 Base64 解码仍然失败，尝试其他常见编码
                    try:
                        decoded_content = content.decode('gbk')
                        print(f"  --- URL: {url} 成功解码 GBK 内容 ---")
                    except UnicodeDecodeError:
                        decoded_content = content.decode('latin-1', errors='ignore')
                        print(f"警告: 无法将 {url} 的内容解码为 UTF-8、GBK 或 Base64。使用 latin-1 并忽略错误。")
            
            if decoded_content:
                # 过滤掉一些明显的非代理内容（例如 HTML 标签）
                if "<!DOCTYPE html>" in decoded_content.lower() or "<html" in decoded_content.lower():
                    print(f"  --- URL: {url} 返回的内容似乎是 HTML 页面，跳过追加。---")
                else:
                    combined_text += decoded_content + "\n"
                    processed_count += 1
            else:
                print(f"  --- URL: {url} 未能解码出有效文本内容，跳过追加。---")

        except requests.exceptions.RequestException as e:
            print(f"从 URL 获取数据失败: {url}，原因: {e}")
        except Exception as e:
            print(f"处理 URL {url} 时发生意外错误: {e}")

    print(f"成功处理并聚合了 {processed_count} 个订阅内容。")
    return combined_text

def main():
    # 从环境变量中读取 BOT 和 URL_LIST_REPO_API
    bot_token = os.environ.get("BOT")
    url_list_repo_api = os.environ.get("URL_LIST_REPO_API")

    if not bot_token or not url_list_repo_api:
        print("错误：环境变量 BOT 或 URL_LIST_REPO_API 未设置！")
        print("请在 GitHub Actions secrets/variables 中正确设置了这些变量。")
        exit(1) # 退出脚本，表示失败

    # 1. 从 GitHub 获取 URL 列表
    print("正在从 GitHub 获取 URL 列表...")
    url_content = get_github_file_content(url_list_repo_api, bot_token)

    if url_content is None:
        print("无法获取 URL 列表，脚本终止。")
        exit(1) # 退出脚本，表示失败

    urls = url_content.strip().split('\n')
    print(f"从 GitHub 获取到 {len(urls)} 个订阅链接。")

    # 2. 遍历 URL，获取数据并解码
    combined_base64_text = fetch_and_decode_urls(urls)

    # 3. 将聚合后的内容进行 Base64 编码
    # 先将文本内容编码为字节流，再进行Base64编码
    final_base64_encoded = base64.b64encode(combined_base64_text.encode('utf-8')).decode('utf-8')

    # 4. 将 Base64 编码后的内容写入 base64.txt 文件
    with open("base64.txt", "w") as f:
        f.write(final_base64_encoded)

    print("Base64 编码内容已成功写入 base64.txt")

if __name__ == "__main__":
    main()
