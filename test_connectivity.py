import yaml
import subprocess
import os
import re

def test_node_connectivity(node, clash_path, temp_config="temp_config.yaml"):
    """测试单个节点的连通性，返回延迟 (毫秒) 或 None (如果连接失败)。"""
    proxy_name = node.get('name', 'unknown')
    proxies_config = {'proxies': [node]}
    try:
        with open(temp_config, 'w') as f:
            yaml.dump(proxies_config, f)

        command = [clash_path, '-t', '-f', temp_config]
        process = subprocess.run(command, capture_output=True, text=True, timeout=10)  # 设置超时时间

        output = process.stdout
        match = re.search(r"delay:\s*(\d+)ms", output)
        if match:
            delay = int(match.group(1))
            print(f"节点 '{proxy_name}' 连接成功，延迟: {delay}ms")
            return delay
        else:
            print(f"节点 '{proxy_name}' 连接失败或无法获取延迟信息。输出: {output.strip()}")
            return None

    except subprocess.TimeoutExpired:
        print(f"节点 '{proxy_name}' 测试超时。")
        return None
    except FileNotFoundError:
        print(f"错误: Clash 可执行文件 '{clash_path}' 未找到。")
        return None
    except Exception as e:
        print(f"测试节点 '{proxy_name}' 时发生错误: {e}")
        return None
    finally:
        if os.path.exists(temp_config):
            os.remove(temp_config)

def process_hysteria2_node(node):
    """处理 hysteria2:// 格式的节点，提取标准 Clash 格式的配置。"""
    name = node.get('name', 'hysteria2_node')
    server_match = re.search(r"hysteria2:\/\/([^@]+)@", node['server'])
    auth_match = re.search(r"@([^:]+):(\d+)", node['server'])
    params_match = re.search(r"\?(.*)", node['server'])

    if server_match and auth_match:
        server = server_match.group(1)
        host = auth_match.group(1)
        port = int(auth_match.group(2))
        password = ""
        alpn = ""
        obfs = ""
        obfs_host = ""
        sni = host  # 默认 SNI 与 host 相同

        if params_match:
            params = params_match.group(1).split('&')
            for param in params:
                if param.startswith("password="):
                    password = param.split("=")[1]
                elif param.startswith("alpn="):
                    alpn_values = param.split("=")[1].split(',')
                    alpn = alpn_values if alpn_values else []
                elif param.startswith("obfs="):
                    obfs = param.split("=")[1]
                elif param.startswith("obfsParam="):
                    obfs_host = param.split("=")[1]
                elif param.startswith("sni="):
                    sni = param.split("=")[1]

        clash_node = {
            'name': name,
            'type': 'hysteria2',
            'server': host,
            'port': port,
            'auth': password,
            'up': '5-100',  # 可调整
            'down': '10-500', # 可调整
            'alpn': alpn,
            'obfs': obfs,
            'obfs-host': obfs_host,
            'sni': sni
        }
        return clash_node
    else:
        print(f"警告: 无法解析 hysteria2 节点 '{name}' 的服务器信息。")
        return None

if __name__ == "__main__":
    clash_config_path = "data/clash.yaml"
    output_config_path = "data/ss.yaml"
    successful_nodes = {'proxies': []}
    clash_executable_path = os.environ.get('CLASH_PATH', '/clash/clash-linux') # 从环境变量获取，默认路径

    try:
        with open(clash_config_path, 'r') as f:
            clash_config = yaml.safe_load(f)
            if 'proxies' in clash_config:
                for node in clash_config['proxies']:
                    node_type = node.get('type')
                    server_address = node.get('server', '')

                    if server_address.startswith('hysteria2://'):
                        processed_node = process_hysteria2_node(node)
                        if processed_node:
                            delay = test_node_connectivity(processed_node, clash_executable_path)
                            if delay is not None:
                                successful_nodes['proxies'].append(node) # 保存原始 hysteria2 格式
                    elif node_type in ['ss', 'vmess', 'trojan', 'snell']:
                        delay = test_node_connectivity(node, clash_executable_path)
                        if delay is not None:
                            successful_nodes['proxies'].append(node)
                    else:
                        print(f"不支持的节点类型或格式: {node.get('name')}")

        with open(output_config_path, 'w') as f:
            yaml.dump(successful_nodes, f, sort_keys=False)

        print(f"\n已将连通的节点保存到 '{output_config_path}'")

    except FileNotFoundError:
        print(f"错误: 配置文件 '{clash_config_path}' 未找到。")
    except yaml.YAMLError as e:
        print(f"解析 YAML 文件时发生错误: {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")
