import os
import requests
import base64
import yaml
import re
import asyncio
import aiohttp
from github import Github
from github import GithubException

# 从环境变量获取配置
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
TARGET_GITHUB_URL = os.getenv("TARGET_GITHUB_URL")
SOURCE_REPO = os.getenv("SOURCE_REPO")
TARGET_REPO = os.getenv("TARGET_REPO")
SOURCE_FILE_PATH = os.getenv("SOURCE_FILE_PATH")
TARGET_FILE_PATH = os.getenv("TARGET_FILE_PATH")

# 验证环境变量
for var_name, var_value in [
    ("GITHUB_TOKEN", GITHUB_TOKEN),
    ("TARGET_GITHUB_URL", TARGET_GITHUB_URL),
    ("SOURCE_REPO", SOURCE_REPO),
    ("TARGET_REPO", TARGET_REPO),
    ("SOURCE_FILE_PATH", SOURCE_FILE_PATH),
    ("TARGET_FILE_PATH", TARGET_FILE_PATH)
]:
    if not var_value:
        raise ValueError(f"{var_name} environment variable is not set")

print(f"Using GITHUB_TOKEN: {'*' * len(GITHUB_TOKEN[:-4]) + GITHUB_TOKEN[-4:]}")
print(f"Using TARGET_GITHUB_URL: {TARGET_GITHUB_URL}")
print(f"Using SOURCE_REPO: {SOURCE_REPO}")
print(f"Using TARGET_REPO: {TARGET_REPO}")
print(f"Using SOURCE_FILE_PATH: {SOURCE_FILE_PATH}")
print(f"Using TARGET_FILE_PATH: {TARGET_FILE_PATH}")

# GitHub API 搜索关键词
SEARCH_QUERIES = [
    "proxy url in:readme",
    "proxy base64 in:readme",
    "v2ray url in:readme",
    "clash config in:readme",
    "ss:// in:readme",
    "ssr:// in:readme",
    "vmess:// in:readme",
    "trojan:// in:readme",
    "vless:// in:readme",
    "hysteria url in:readme",
    "hysteria2 url in:readme",
    "hy2:// in:readme",
    "tuic config in:readme"
]

# 支持的代理节点协议前缀
VALID_PROTOCOLS = [
    "ss://", "ssr://", "vmess://", "trojan://",
    "vless://", "hysteria://", "hysteria2://", "hy2://", "tuic://"
]

# 提取 URL 的正则表达式
URL_REGEX = r'(?:(?:ss|ssr|vmess|trojan|vless|hysteria|hysteria2|hy2|tuic):\/\/[^\s<>"\']+)'

async def test_url_connectivity(session, url, timeout=5):
    """异步测试 URL 连通性"""
    try:
        async with session.get(url, timeout=timeout) as response:
            print(f"Testing {url}: Status {response.status}")
            return response.status == 200
    except Exception as e:
        print(f"Testing {url}: Failed with error {e}")
        return False

def decode_base64(data):
    """解码 Base64 编码的内容"""
    try:
        decoded = base64.b64decode(data).decode('utf-8', errors='ignore')
        return decoded
    except:
        return None

def parse_yaml_content(content):
    """解析 YAML 格式内容，提取代理节点"""
    try:
        data = yaml.safe_load(content)
        urls = []
        if not isinstance(data, dict):
            print("YAML content is not a dictionary")
            return urls

        # 支持 Clash 配置中的 proxies 字段
        if 'proxies' in data:
            for proxy in data.get('proxies', []):
                if 'server' in proxy and 'port' in proxy:
                    proto = proxy.get('type', 'ss')
                    if proto in [p.strip(':/') for p in VALID_PROTOCOLS]:
                        urls.append(f"{proto}://{proxy['server']}:{proxy['port']}")

        # 支持 V2Ray 配置中的 outbounds 字段
        if 'outbounds' in data:
            for outbound in data.get('outbounds', []):
                if 'settings' in outbound and isinstance(outbound['settings'], dict):
                    settings = outbound['settings']
                    if 'servers' in settings:
                        for server in settings['servers']:
                            if 'address' in server and 'port' in server:
                                proto = outbound.get('protocol', 'vmess')
                                if proto in [p.strip(':/') for p in VALID_PROTOCOLS]:
                                    urls.append(f"{proto}://{server['address']}:{server['port']}")
                    elif 'vnext' in settings:
                        for vnext in settings['vnext']:
                            if 'address' in vnext and 'port' in vnext:
                                proto = outbound.get('protocol', 'vmess')
                                if proto in [p.strip(':/') for p in VALID_PROTOCOLS]:
                                    urls.append(f"{proto}://{vnext['address']}:{vnext['port']}")

        print(f"Extracted {len(urls)} URLs from YAML content")
        return urls
    except Exception as e:
        print(f"Error parsing YAML content: {e}")
        return []

def extract_urls(content):
    """从内容中提取所有可能的 URL"""
    urls = set()
    
    # 提取明文 URL
    matches = re.findall(URL_REGEX, content, re.IGNORECASE)
    for match in matches:
        if any(match.startswith(proto) for proto in VALID_PROTOCOLS):
            urls.add(match.strip())
    print(f"Extracted {len(matches)} plaintext URLs")

    # 尝试解码 Base64
    base64_pattern = r'(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?'
    base64_matches = re.findall(base64_pattern, content)
    for b64 in base64_matches:
        decoded = decode_base64(b64)
        if decoded:
            decoded_urls = re.findall(URL_REGEX, decoded, re.IGNORECASE)
            for url in decoded_urls:
                if any(url.startswith(proto) for proto in VALID_PROTOCOLS):
                    urls.add(url.strip())
    print(f"Extracted {len(urls)} URLs after Base64 decoding")

    # 解析 YAML 内容
    yaml_urls = parse_yaml_content(content)
    urls.update(yaml_urls)

    return urls

async def search_and_collect_urls():
    """搜索 GitHub 仓库并提取代理节点 URL"""
    g = Github(GITHUB_TOKEN)
    all_urls = set()

    for query in SEARCH_QUERIES:
        print(f"Searching with query: {query}")
        try:
            results = g.search_code(query=query, sort="indexed", order="desc")
            for result in results[:10]:  # 限制每个查询的前 10 个结果
                print(f"Processing file: {result.path}")
                try:
                    content = result.decoded_content.decode('utf-8', errors='ignore')
                    urls = extract_urls(content)
                    all_urls.update(urls)
                except Exception as e:
                    print(f"Error processing file {result.path}: {e}")
        except GithubException as e:
            print(f"Error with query {query}: {e}")
    
    print(f"Total unique URLs found: {len(all_urls)}")
    return all_urls

async def test_urls(urls):
    """测试 URL 连通性"""
    async with aiohttp.ClientSession() as session:
        tasks = [test_url_connectivity(session, url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        available_urls = [url for url, result in zip(urls, results) if result]
        print(f"Total available URLs after testing: {len(available_urls)}")
        return available_urls

def ensure_data_directory(repo, repo_name):
    """确保 data/ 目录存在"""
    try:
        repo.get_contents("data")
        print(f"Directory 'data/' already exists in {repo_name}.")
    except GithubException:
        print(f"Creating 'data/' directory in {repo_name}...")
        repo.create_file(
            path="data/.gitkeep",
            message="Create data directory with .gitkeep",
            content=""
        )
        print(f"Directory 'data/' created in {repo_name}.")

def get_existing_urls(repo, file_path):
    """获取指定文件中的现有 URL"""
    try:
        file = repo.get_contents(file_path)
        content = file.decoded_content.decode('utf-8')
        urls = set(url.strip() for url in content.splitlines() if url.strip() and any(url.startswith(proto) for proto in VALID_PROTOCOLS))
        print(f"Existing URLs in {file_path}: {len(urls)}")
        return urls, file.sha if file else None
    except GithubException:
        print(f"No existing {file_path} found.")
        return set(), None

def update_github_file(repo, file_path, new_urls, repo_name, existing_sha=None):
    """将新 URL 追加到指定文件"""
    try:
        # 获取现有 URL
        existing_urls, sha = get_existing_urls(repo, file_path)
        
        # 找出新增的 URL
        new_unique_urls = new_urls - existing_urls
        
        if not new_unique_urls:
            print(f"No new URLs to add to {file_path} in {repo_name}. Skipping update.")
            return

        # 获取现有文件内容（如果存在）
        try:
            file = repo.get_contents(file_path)
            existing_content = file.decoded_content.decode('utf-8')
        except GithubException:
            existing_content = ""

        # 追加新 URL
        new_content = existing_content + "\n" + "\n".join(new_unique_urls) if existing_content else "\n".join(new_unique_urls)
        
        # 更新或创建文件
        if existing_sha:
            repo.update_file(
                path=file_path,
                message=f"Append new proxy URLs to {file_path}",
                content=new_content,
                sha=existing_sha
            )
            print(f"Successfully appended {len(new_unique_urls)} new URLs to {file_path} in {repo_name}.")
        else:
            repo.create_file(
                path=file_path,
                message=f"Create {file_path} with proxy URLs",
                content=new_content
            )
            print(f"Successfully created {file_path} with {len(new_unique_urls)} URLs in {repo_name}.")
    except GithubException as e:
        print(f"Error updating {file_path} in {repo_name}: {e}")

async def main():
    """主函数"""
    print("Starting proxy URL search...")
    urls = await search_and_collect_urls()
    if not urls:
        print("No URLs found. Exiting.")
        return

    print(f"Testing connectivity for {len(urls)} URLs...")
    available_urls = await test_urls(urls)
    if not available_urls:
        print("No available URLs found. Exiting.")
        return

    g = Github(GITHUB_TOKEN)
    
    # 处理 source 仓库
    try:
        source_repo = g.get_repo(SOURCE_REPO)
        ensure_data_directory(source_repo, SOURCE_REPO)
        update_github_file(source_repo, SOURCE_FILE_PATH, set(available_urls), SOURCE_REPO)
    except GithubException as e:
        print(f"Error processing {SOURCE_REPO}: {e}")

    # 处理 target 仓库
    try:
        target_repo = g.get_repo(TARGET_REPO)
        ensure_data_directory(target_repo, TARGET_REPO)
        update_github_file(target_repo, TARGET_FILE_PATH, set(available_urls), TARGET_REPO)
    except GithubException as e:
        print(f"Error processing {TARGET_REPO}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
