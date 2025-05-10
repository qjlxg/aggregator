import requests
import yaml
import os
import re

# 定义要排除的关键字
exclude_keywords = [
    "https://raw.githubusercontent.com",
    "https://t.me",
    "https://github.com",
    "raw"
]

# 配置文件 URL
config_url = "https://github.com/qjlxg/collectSub/raw/refs/heads/main/config.yaml"

# 输出文件路径
output_file = "data/subscribes.txt"

def is_valid_url(url):
    """判断字符串是否为有效的 URL"""
    regex = re.compile(
        r'^(?:http|ftp)s?://'  # http(s) or ftp(s)
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url) is not None

def test_connectivity(url, timeout=5):
    """测试 URL 是否可以连通"""
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def main():
    try:
        response = requests.get(config_url)
        response.raise_for_status()
        config = yaml.safe_load(response.text)

        new_links = set()

        # 提取 clash 订阅链接
        if "clash订阅" in config and isinstance(config["clash订阅"], list):
            for link in config["clash订阅"]:
                if isinstance(link, str) and is_valid_url(link) and not any(keyword in link for keyword in exclude_keywords):
                    new_links.add(link)

        # 提取 v2 订阅链接
        if "v2订阅" in config and isinstance(config["v2订阅"], list):
            for link in config["v2订阅"]:
                if isinstance(link, str) and is_valid_url(link) and not any(keyword in link for keyword in exclude_keywords):
                    new_links.add(link)

        # 读取已存在的订阅链接
        existing_links = set()
        if os.path.exists(output_file):
            with open(output_file, "r") as f:
                for line in f:
                    link = line.strip()
                    if link:
                        existing_links.add(link)

        # 测试新链接的连通性并去重
        connected_links = set()
        for link in new_links:
            if link not in existing_links and test_connectivity(link):
                connected_links.add(link)
                print(f"链接 {link} 可连通")
            elif link in existing_links:
                print(f"链接 {link} 已存在")
            else:
                print(f"链接 {link} 无法连通")

        # 合并已存在的和新连接通的链接并去重
        all_links = existing_links.union(connected_links)

        # 保存去重后的链接到文件
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w") as f:
            for link in sorted(list(all_links)):
                f.write(link + "\n")

        print(f"共保存 {len(all_links)} 个订阅链接到 {output_file}")

    except requests.exceptions.RequestException as e:
        print(f"获取配置文件失败: {e}")
    except yaml.YAMLError as e:
        print(f"解析 YAML 失败: {e}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()
