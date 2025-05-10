import requests
import yaml
import os
import re
import time
from datetime import datetime, timezone, timedelta

# 定义要排除的关键字
exclude_keywords = [
    "https://raw.githubusercontent.com",
    "https://t.me",
    "https://github.com",
    "raw"
]

# 配置文件 URLs 列表
config_urls = [
    "https://github.com/qjlxg/collectSub/raw/refs/heads/main/config.yaml",
    "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/xujw3.txt",
   
]

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

def test_connectivity(url, timeout=10):
    """测试 URL 是否可以连通，并初步判断订阅是否有效"""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()  # 如果状态码不是 200，会抛出异常

        # 尝试读取内容，进行初步判断
        content = response.text.strip()
        if content:
            return True
        else:
            print(f"链接 {url} 返回空内容，可能无效")
            return False

    except requests.exceptions.RequestException as e:
        print(f"测试链接 {url} 失败: {e}")
        return False
    except Exception as e:
        print(f"测试链接 {url} 时发生错误: {e}")
        return False

def main():
    all_new_links = set()
    for config_url in config_urls:
        try:
            response = requests.get(config_url)
            response.raise_for_status()
            config = yaml.safe_load(response.text)

            if isinstance(config, dict) and ("clash订阅" in config or "v2订阅" in config):
                # 处理包含 "clash订阅" 和 "v2订阅" 键的格式
                if "clash订阅" in config and isinstance(config["clash订阅"], list):
                    for link in config["clash订阅"]:
                        if isinstance(link, str) and is_valid_url(link) and not any(keyword in link for keyword in exclude_keywords):
                            all_new_links.add(link)

                if "v2订阅" in config and isinstance(config["v2订阅"], list):
                    for link in config["v2订阅"]:
                        if isinstance(link, str) and is_valid_url(link) and not any(keyword in link for keyword in exclude_keywords):
                            all_new_links.add(link)
            elif isinstance(config, list):
                # 处理直接的链接列表格式
                for link in config:
                    if isinstance(link, str) and is_valid_url(link) and not any(keyword in link for keyword in exclude_keywords):
                        all_new_links.add(link)

            print(f"成功从 {config_url} 获取并处理了订阅链接")

        except requests.exceptions.RequestException as e:
            print(f"获取配置文件 {config_url} 失败: {e}")
        except yaml.YAMLError as e:
            print(f"解析 YAML 文件 {config_url} 失败: {e}")
        except Exception as e:
            print(f"处理配置文件 {config_url} 时发生错误: {e}")

    # 读取已存在的订阅链接
    existing_links = set()
    if os.path.exists(output_file):
        with open(output_file, "r") as f:
            for line in f:
                link = line.strip()
                if link:
                    existing_links.add(link)

    # 测试新链接的连通性和有效性并去重
    valid_links = set()
    for link in all_new_links:
        if link not in existing_links and test_connectivity(link):
            valid_links.add(link)
            print(f"链接 {link} 可连通且内容不为空，已添加到有效链接")
        elif link in existing_links:
            print(f"链接 {link} 已存在")
        else:
            print(f"链接 {link} 无法连通或内容为空")

    # 合并已存在的和新连接通且有效的链接并去重
    final_links = existing_links.union(valid_links)

    # 保存去重后的链接到文件
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        for link in sorted(list(final_links)):
            f.write(link + "\n")

    print(f"共保存 {len(final_links)} 个有效订阅链接到 {output_file}")

if __name__ == "__main__":
    main()
