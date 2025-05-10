import yaml
import subprocess
import os
import re
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def standardize_clash_config(input_path="data/clash.yaml", output_path="temp_clash.yaml"):
    """读取 Clash 配置文件，标准化格式，并写入新的临时文件 (强制转换布尔值)。"""
    try:
        with open(input_path, 'r') as f:
            clash_config = yaml.safe_load(f)
            if 'proxies' in clash_config and isinstance(clash_config['proxies'], list):
                standardized_proxies = []
                for proxy in clash_config['proxies']:
                    if isinstance(proxy, dict):
                        standardized_proxy = proxy.copy()
                        # 强制转换布尔值
                        for key in ['tls', 'udp', 'allow-insecure', 'insecure']:
                            if key in standardized_proxy:
                                if standardized_proxy[key] in ['true', True, 1]:
                                    standardized_proxy[key] = True
                                elif standardized_proxy[key] in ['false', False, 0, None, '']:
                                    standardized_proxy[key] = False
                                else:
                                    logging.warning(f"代理 '{standardized_proxy.get('name', 'unknown')}' 的字段 '{key}' 的值 '{standardized_proxy[key]}' 不是标准的布尔值，已强制转换为 False。")
                                    standardized_proxy[key] = False

                        # 标准化端口为整数
                        if 'port' in standardized_proxy and isinstance(standardized_proxy['port'], str) and standardized_proxy['port'].isdigit():
                            standardized_proxy['port'] = int(standardized_proxy['port'])
                        elif 'port' in standardized_proxy and not isinstance(standardized_proxy['port'], int):
                            logging.warning(f"代理 '{standardized_proxy.get('name', 'unknown')}' 的端口 '{standardized_proxy['port']}' 不是整数类型。")

                        standardized_proxies.append(standardized_proxy)
                    else:
                        logging.warning("proxies 列表中包含非字典类型的元素，已忽略。")

                standardized_config = {'proxies': standardized_proxies}
                with open(output_path, 'w') as outfile:
                    yaml.dump(standardized_config, outfile, sort_keys=False)
                logging.info(f"已将标准化后的配置写入到 '{output_path}'")
                return output_path
            else:
                logging.error("配置文件中没有 'proxies' 列表或格式不正确。")
                return None
    except FileNotFoundError:
        logging.error(f"配置文件 '{input_path}' 未找到。")
        return None
    except yaml.YAMLError as e:
        logging.error(f"解析 YAML 文件时发生错误: {e}")
        return None
    except Exception as e:
        logging.error(f"标准化配置时发生未知错误: {e}")
        return None

def test_node_connectivity(node, clash_path, temp_config="temp_config.yaml"):
    """测试单个节点的连通性，返回 True (连接成功) 或 False (连接失败)。"""
    proxy_name = node.get('name', 'unknown')
    proxies_config = {'proxies': [node]}
    try:
        with open(temp_config, 'w') as f:
            yaml.dump(proxies_config, f)

        command = [clash_path, '-t', '-f', temp_config]
        process = subprocess.run(command, capture_output=True, text=True, timeout=10)

        output = process.stdout
        # 如果测试成功，clash-linux 通常会输出 "configuration file ... test is successful"
        if "test is successful" in output:
            print(f"节点 '{proxy_name}' 连接成功。")
            return True
        else:
            print(f"节点 '{proxy_name}' 连接失败。输出: {output.strip()}")
            return False

    except subprocess.TimeoutExpired:
        print(f"节点 '{proxy_name}' 测试超时。")
        return False
    except FileNotFoundError:
        print(f"错误: Clash 可执行文件 '{clash_path}' 未找到。")
        return False
    except Exception as e:
        print(f"测试节点 '{proxy_name}' 时发生错误: {e}")
        return False
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
            'sni': sni,
            'insecure': node.get('insecure', False) # 从原始节点继承 insecure 参数
        }
        return clash_node
    else:
        print(f"警告: 无法解析 hysteria2 节点 '{name}' 的服务器信息。")
        return None

if __name__ == "__main__":
    clash_config_path = "data/clash.yaml"
    output_config_path = "data/ss.yaml"
    successful_nodes = {'proxies': []}
    clash_executable_path = os.environ.get('CLASH_PATH', '/clash/clash-linux')

    # 标准化 Clash 配置文件
    standardized_config_path = standardize_clash_config(clash_config_path)

    if standardized_config_path:
        try:
            with open(standardized_config_path, 'r') as f:
                standardized_config = yaml.safe_load(f)
                if 'proxies' in standardized_config:
                    for original_node in yaml.safe_load(open(clash_config_path, 'r')).get('proxies', []): # 保持原始节点信息
                        processed_node = original_node
                        node_type = processed_node.get('type')
                        server_address = processed_node.get('server', '')

                        if server_address.startswith('hysteria2://'):
                            processed_node_for_test = process_hysteria2_node(processed_node)
                            if processed_node_for_test:
                                if test_node_connectivity(processed_node_for_test, clash_executable_path):
                                    successful_nodes['proxies'].append(processed_node) # 保存原始 hysteria2 格式
                        elif node_type in ['ss', 'vmess', 'trojan', 'snell', 'hysteria2']:
                            if test_node_connectivity(processed_node, clash_executable_path):
                                successful_nodes['proxies'].append(processed_node)
                        else:
                            print(f"不支持的节点类型或格式: {processed_node.get('name')}")

            os.makedirs(os.path.dirname(output_config_path), exist_ok=True)
            with open(output_config_path, 'w') as f:
                yaml.dump(successful_nodes, f, sort_keys=False)

            print(f"\n已将连接成功的节点保存到 '{output_config_path}'")

        except FileNotFoundError:
            print(f"错误: 临时配置文件 '{standardized_config_path}' 未找到。")
        except yaml.YAMLError as e:
            print(f"解析临时 YAML 文件时发生错误: {e}")
        except Exception as e:
            print(f"发生未知错误: {e}")
        finally:
            # 清理临时配置文件
            if os.path.exists(standardized_config_path):
                os.remove(standardized_config_path)
    else:
        print("标准化配置文件失败，无法进行测试。")
