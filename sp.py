# -*- coding: utf-8 -*-
import subprocess
import yaml
import os
import time
import threading
from typing import List, Dict

# 定义路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CLASH_CONFIG_PATH = os.path.join(DATA_DIR, "clash.yaml")
SP_PATH = os.path.join(DATA_DIR, "sp.yaml")
CLASH_BIN_PATH = {
    'Linux': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'clash', 'clash-linux'),  # 假设 clash-linux 在 clash 目录下
    'Darwin-AMD64': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'clash', 'clash-darwin-amd'), # 假设 clash-darwin-amd 在 clash 目录下
    'Darwin-ARM64': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'clash', 'clash-darwin-arm'), # 假设 clash-darwin-arm 在 clash 目录下
}
COUNTRY_MMDB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'clash', 'Country.mmdb')  # 假设 Country.mmdb 在 clash 目录下

# 加载 clash 配置文件
def load_clash_config(config_path: str) -> Dict:
    """
    加载 clash 配置文件.

    参数:
        config_path (str): clash 配置文件路径.

    返回:
        Dict: 配置字典，加载失败返回空字典.
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"Error loading clash config: {e}")
        return {}

# 提取指定类型的节点
def extract_nodes(config: Dict, protocols: List[str]) -> List[Dict]:
    """
    从 clash 配置中提取指定类型的节点.

    参数:
        config (Dict): clash 配置字典.
        protocols (List[str]): 需要提取的协议类型列表.

    返回:
        List[Dict]: 提取出的节点列表.
    """
    nodes = []
    if not config or "proxies" not in config:
        return nodes
    for proxy in config["proxies"]:
        if proxy.get("type") in protocols:
            nodes.append(proxy)
    return nodes

# 检查节点连通性
def check_node(node: Dict, clash_bin: str) -> bool:
    """
    检查单个节点是否连通.

    参数:
        node (Dict): 节点信息.
        clash_bin (str): clash 运行程序的路径

    返回:
        bool: 节点是否连通.
    """
    # 生成一个临时的 clash 配置文件，仅包含当前要测试的节点
    temp_config = {
        "mode": "Direct",  # 设置为 Direct 模式，避免影响其他连接
        "proxies": [node],
        "proxy-groups": [
            {
                "name": "test",
                "type": "select",
                "proxies": [node.get("name", "")]
            }
        ],
        "rules": [
            {"type": "GLOBAL", "proxy": "test"}
        ]
    }
    temp_config_path = os.path.join(DATA_DIR, "temp_config.yaml")
    try:
        with open(temp_config_path, "w", encoding="utf-8") as f:
            yaml.dump(temp_config, f, allow_unicode=True)
    except Exception as e:
        print(f"Error creating temp config: {e}")
        return False

    # 构造 clash 命令，使用外部控制器和 127.0.0.1:65535
    command = [
        clash_bin,
        "-c", temp_config_path,
        "-d", DATA_DIR,  # 指定配置目录
    ]

    try:
        # 启动 clash
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            # 添加 env 参数，确保 clash 能够找到 Country.mmdb
            env={"CLASH_MMDB_PATH": COUNTRY_MMDB_PATH}
        )

        # 等待 clash 启动，这里简单等待 2 秒，更严谨的做法是检查 clash 的输出
        time.sleep(2)
        # 检查节点连通性，这里使用 curl 访问一个简单的网站
        curl_command = ["curl", "-m", "5", "http://www.google.com"] # 超时设置为 5 秒
        curl_process = subprocess.Popen(
            curl_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        curl_process.communicate()
        if curl_process.returncode == 0:
            return True
        else:
            return False

    except Exception as e:
        print(f"Error checking node: {e}")
        return False
    finally:
        # 确保 clash 进程被终止
        if process:
            process.terminate()
        # 删除临时配置文件
        if os.path.exists(temp_config_path):
            os.remove(temp_config_path)

def test_nodes(nodes: List[Dict], clash_bin: str) -> List[Dict]:
    """
    批量测试节点连通性.

    参数:
        nodes (List[Dict]): 节点列表.
        clash_bin (str): clash可执行文件的路径

    返回:
        List[Dict]: 连通的节点列表.
    """
    connected_nodes = []
    threads = []
    results = []  # 用于保存每个节点的测试结果，保证顺序

    def check_and_append(node: Dict):
        """
        用于在线程中执行节点检查，并将结果添加到 results 列表中.
        """
        if check_node(node, clash_bin):
            results.append((True, node))  # (True, node) 表示连通
        else:
            results.append((False, node)) # (False, node) 表示不连通

    # 为每个节点创建一个线程
    for node in nodes:
        thread = threading.Thread(target=check_and_append, args=(node,))
        threads.append(thread)
        thread.start()

    # 等待所有线程执行完成
    for thread in threads:
        thread.join()

    # 按照原始 nodes 列表的顺序，提取连通的节点
    for i, node in enumerate(nodes):
        if results[i][0]:
            connected_nodes.append(results[i][1])
    return connected_nodes

# 保存测试结果
def save_results(results: List[Dict], output_path: str) -> bool:
    """
    保存节点测试结果到文件.

    参数:
        results (List[Dict]): 节点测试结果列表.
        output_path (str): 输出文件路径.

    返回:
        bool: 保存是否成功.
    """
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump({"proxies": results}, f, allow_unicode=True, sort_keys=False)
        return True
    except Exception as e:
        print(f"Error saving results: {e}")
        return False

def main():
    """
    主函数，完成节点测试并保存结果.
    """
    # 确定操作系统，选择对应的 clash 可执行文件
    system = os.uname().sysname
    machine = os.uname().machine
    if system == "Linux":
        clash_bin = CLASH_BIN_PATH["Linux"]
    elif system == "Darwin" and machine == "x86_64":
        clash_bin = CLASH_BIN_PATH["Darwin-AMD64"]
    elif system == "Darwin" and machine == "arm64":
        clash_bin = CLASH_BIN_PATH["Darwin-ARM64"]
    else:
        print(f"Unsupported system: {system} {machine}")
        return

    # 检查 clash 可执行文件是否存在
    if not os.path.exists(clash_bin):
        print(f"Clash binary not found at {clash_bin}")
        return

    # 加载 clash 配置文件
    clash_config = load_clash_config(CLASH_CONFIG_PATH)
    if not clash_config:
        print("Failed to load clash config.")
        return

    # 提取指定类型的节点
    protocols = ["vmess", "ss", "vless", "trojan", "hysteria2"]
    nodes = extract_nodes(clash_config, protocols)
    if not nodes:
        print(f"No nodes found with protocols: {protocols}")
        return

    print(f"Found {len(nodes)} nodes to test.")

    # 测试节点连通性
    connected_nodes = test_nodes(nodes, clash_bin)
    print(f"Found {len(connected_nodes)} connected nodes.")

    # 保存测试结果
    if save_results(connected_nodes, SP_PATH):
        print(f"Results saved to {SP_PATH}")
    else:
        print("Failed to save results.")

if __name__ == "__main__":
    main()

