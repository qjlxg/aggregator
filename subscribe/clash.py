# -*- coding: utf-8 -*-
import json
import os
import executable  # 假设这个模块用于查找可执行文件
import utils      # 假设这个模块包含工具函数
import yaml

# Clash API 默认地址
EXTERNAL_CONTROLLER = "127.0.0.1:9090"

def generate_config(path: str, proxies: list, filename: str) -> list:
    """生成 Clash 配置文件"""
    os.makedirs(path, exist_ok=True)
    config = {
        "mixed-port": 7890,
        "external-controller": EXTERNAL_CONTROLLER,
        "mode": "Rule",
        "log-level": "silent",
        "proxies": proxies,  # 直接使用传入的代理列表
        "proxy-groups": [
            {
                "name": "automatic",
                "type": "url-test",
                "proxies": [p["name"] for p in proxies],
                "url": "https://www.google.com/favicon.ico",
                "interval": 300,
            },
            {"name": "🌐 Proxy", "type": "select", "proxies": ["automatic"] + [p["name"] for p in proxies]},
        ],
        "rules": ["MATCH,🌐 Proxy"],
    }

    with open(os.path.join(path, filename), "w+", encoding="utf8") as f:
        yaml.dump(config, f, allow_unicode=True)

    return config.get("proxies", [])

def main():
    # 1. 加载代理数据
    json_path = "data/singbox.json"
    if not os.path.exists(json_path):
        print(f"错误：{json_path} 文件不存在")
        return
    
    with open(json_path, "r", encoding="utf-8") as f:
        proxies_data = json.load(f)
        # 假设 singbox.json 中的代理在 'proxies' 键下
        proxies = proxies_data.get("proxies", [])
        if not proxies:
            print("错误：代理列表为空")
            return

    # 2. 设置配置参数
    config_path = "./config"         # 配置文件保存目录
    config_filename = "config.yaml"  # 配置文件名

    # 3. 生成配置文件
    generate_config(config_path, proxies, config_filename)
    print(f"配置文件已生成：{os.path.join(config_path, config_filename)}")

    # 4. 启动 Clash
    clash_bin = "clash-linux"  # Clash 可执行文件名
    bin_path = os.path.join(os.getcwd(), "clash", clash_bin)  # 完整路径
    if not os.path.exists(bin_path):
        print(f"错误：Clash 可执行文件 {bin_path} 不存在")
        return
    
    # 确保 Clash 可执行文件有执行权限（Linux 系统）
    os.chmod(bin_path, 0o755)
    # 后台运行 Clash
    cmd = f"{bin_path} -d {config_path} -f {os.path.join(config_path, config_filename)} &"
    os.system(cmd)
    print(f"Clash 已启动，配置文件路径：{config_path}")

if __name__ == "__main__":
    main()
