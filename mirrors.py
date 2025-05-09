import requests
from bs4 import BeautifulSoup
import json

def load_mirrors_from_json(filename="github_mirror_list.json"):
    """从 JSON 文件加载镜像站点列表."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("mirrors", [])  # 返回 "mirrors" 列表
    except FileNotFoundError:
        print(f"File not found: {filename}")
        return []
    except json.JSONDecodeError:
        print(f"Error decoding JSON from {filename}")
        return []

def is_github_up(mirror):
    """检查 GitHub 镜像站点是否可用."""
    try:
        response = requests.get(mirror, timeout=5)
        response.raise_for_status()  # 抛出 HTTPError 异常（如果状态码不是 200）
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error checking {mirror}: {e}")
        return False

def find_github_mirrors():
    """查找并验证 GitHub 镜像站点."""
    mirrors = load_mirrors_from_json()

    validated_mirrors = []
    for mirror in mirrors:
        if is_github_up(mirror):
            validated_mirrors.append(mirror)
            print(f"Found valid mirror: {mirror}") #输出有效的镜像站点
        else:
             print(f"Invalid mirror: {mirror}") #输出无效的镜像站点

    write_mirrors_to_file(validated_mirrors) #调用函数写入mirrors.txt
    write_mirrors_to_json(validated_mirrors)   #调用函数写入github_mirror_list.json

    return validated_mirrors
def write_mirrors_to_file(mirrors, filename="mirrors.txt"):
    """将镜像站点写入到文件."""
    try:
        with open(filename, "w") as f:
            for mirror in mirrors:
                f.write(mirror + "\n")
        print(f"Mirror list written to {filename}")
    except Exception as e:
        print(f"Error writing to {filename}: {e}")

def write_mirrors_to_json(mirrors, filename="github_mirror_list.json"):
    """将有效的镜像站点列表写入JSON文件，更新日期"""
    import datetime

    data = {
        "mirrors": mirrors,
        "description": "Validated GitHub 镜像站点列表",
        "last_updated": datetime.date.today().strftime("%Y-%m-%d")  # 使用当前日期
    }
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Validated mirror list written to {filename}")
    except Exception as e:
        print(f"Error writing to {filename}: {e}")

if __name__ == "__main__":
    find_github_mirrors()
