import base64
import json
import yaml
from urllib.parse import urlparse, parse_qs
import binascii
import hashlib
import urllib.parse # 导入 urllib.parse 用于 URL 编码

def generate_ss_uri(method, password, server, port, remarks=""):
    """
    生成兼容 UTF-8 的 Shadowsocks URI.

    Args:
        method: 加密方法 (例如: aes-256-cfb).
        password: 密码 (可以是 Unicode 字符).
        server: 服务器地址.
        port: 端口号.
        remarks: 备注信息 (可选).

    Returns:
        一个 Shadowsocks URI 字符串.
    """
    try:
        method_password = f"{method}:{password}".encode('utf-8')
        encoded_method_password = base64.b64encode(method_password).decode('utf-8').strip('=')

        uri = f"ss://{encoded_method_password}@{server}:{port}"

        if remarks:
            uri += "#" + urllib.parse.quote(remarks)

        return uri

    except Exception as e:
        print(f"生成 SS URI 失败: {e}")
        return None

def parse_vmess(uri):
    try:
        vmess_data = base64.b64decode(uri.split("://")[1]).decode()
        vmess_config = json.loads(vmess_data)
        return {
            "name": vmess_config["ps"],
            "type": "vmess",
            "server": vmess_config["add"],
            "port": int(vmess_config["port"]),
            "uuid": vmess_config["id"],
            "alterId": int(vmess_config["aid"]),
            "cipher": "auto",
            "network": vmess_config.get("net", "tcp"),
            "tls": vmess_config.get("tls", "") == "tls",
            "ws-path": vmess_config.get("path", "/"),
            "ws-headers": {"Host": vmess_config.get("host", "")}
        }
    except (base64.binascii.Error, json.JSONDecodeError) as e:
        print(f"警告: 解析 Vmess URI '{uri}' 时遇到错误: {e}，已跳过该节点。")
        return None
    except Exception as e:
        print(f"警告: 解析 Vmess URI '{uri}' 时遇到其他错误: {e}，已跳过该节点。")
        return None

def parse_ss(uri):
    try:
        parts = uri.split("://")[1].split("@")
        encoded_method_password = parts[0]
        try:
            method_password = base64.b64decode(encoded_method_password).decode("utf-8").split(":")
        except UnicodeDecodeError:
            method_password = base64.b64decode(encoded_method_password).decode("latin-1").split(":")

        server_port = parts[1].split("#")[0].split(":")
        return {
            "name": "ss-" + server_port[0],
            "type": "ss",
            "server": server_port[0],
            "port": int(server_port[1]),
            "cipher": method_password[0],
            "password": method_password[1]
        }
    except binascii.Error:
        print(f"警告: 解析 Shadowsocks URI '{uri}' 时遇到 Base64 解码错误，已跳过该节点。")
        return None
    except Exception as e:
        print(f"警告: 解析 Shadowsocks URI '{uri}' 时遇到其他错误: {e}，已跳过该节点。")
        return None

def parse_trojan(uri):
    try:
        parsed = urlparse(uri)
        return {
            "name": "trojan-" + parsed.hostname,
            "type": "trojan",
            "server": parsed.hostname,
            "port": int(parsed.port),
            "password": parsed.netloc.split("@")[0]
        }
    except Exception as e:
        print(f"警告: 解析 Trojan URI '{uri}' 时遇到错误: {e}，已跳过该节点。")
        return None

def generate_clash_config(nodes):
    proxies = []
    seen_names = set()
    for node in nodes:
        uri = node.strip()
        proxy_info = None
        if uri.startswith("vmess://"):
            proxy_info = parse_vmess(uri)
        elif uri.startswith("ss://"):
            proxy_info = parse_ss(uri)
        elif uri.startswith("trojan://"):
            proxy_info = parse_trojan(uri)

        if proxy_info:
            name = proxy_info["name"]
            if name in seen_names:
                unique_suffix = hashlib.md5(uri.encode()).hexdigest()[:8]
                proxy_info["name"] = f"{name}-{unique_suffix}"
            elif not name:
                unique_name = hashlib.md5(uri.encode()).hexdigest()[:16]
                proxy_info["name"] = unique_name

            if proxy_info["name"] not in seen_names:
                proxies.append(proxy_info)
                seen_names.add(proxy_info["name"])
            else:
                print(f"警告: 节点 '{uri}' 生成的名称 '{proxy_info['name']}' 仍然重复，已跳过。")

    config = {
        "port": 7890,
        "socks-port": 7891,
        "external-controller": "127.0.0.1:9090",
        "secret": "",
        "proxies": proxies,
        "proxy-groups": [
            {"name": "auto", "type": "select", "proxies": [p["name"] for p in proxies]}
        ],
        "rules": ["MATCH,auto"]
    }
    with open("config.yaml", "w") as f:
        yaml.dump(config, f, indent=2, sort_keys=False, allow_unicode=True) # 加上 indent，sort_keys 和 allow_unicode

# 示例用法 (生成 SS URI)
# method = "aes-256-cfb"
# password = "密码包含中文测试123"
# server = "your_server.com"
# port = 8888
# remarks = "我的中文节点备注"
# ss_uri = generate_ss_uri(method, password, server, port, remarks)
# if ss_uri:
#     print(f"生成的 Shadowsocks URI: {ss_uri}")


# 读取节点信息并生成 Clash 配置
with open("data/ji.txt", "r") as f:
    nodes = f.readlines()

generate_clash_config(nodes)
