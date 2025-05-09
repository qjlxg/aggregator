import json

def generate_mirror_json(filename="github_mirror_list.json"):
    """
    生成包含 GitHub 镜像站点列表的 JSON 文件。
    """

    mirrors = [
        "https://hub.fastgit.org",
        "https://gitlink.org.cn",
        "https://ghproxy.com/",
        "https://mirrors.tuna.tsinghua.edu.cn/",
        "http://mirrors.ustc.edu.cn/",
        "https://toolwa.com/github/"
    ]

    data = {
        "mirrors": mirrors,
        "description": "GitHub 镜像站点列表 (请验证可用性)",
        "last_updated": "2024-01-26"  # 更新日期, 每次更新都应修改此日期
    }

    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)  # 缩进并确保非 ASCII 字符正确编码
        print(f"JSON 文件 '{filename}' 生成成功。")
    except Exception as e:
        print(f"生成 JSON 文件时出错: {e}")

if __name__ == "__main__":
    generate_mirror_json()
