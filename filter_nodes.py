import yaml
import os

# 定义支持的节点类型
SUPPORTED_TYPES = ['vmess', 'ss', 'hysteria2', 'trojan', 'vless']

# 要检测的网站关键词，用于判断是否能访问
TARGET_DOMAINS = ['google.com', 'youtube.com']

def load_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def save_yaml(data, file_path):
    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True)

def node_can_access(node):
    """
    简单判断节点是否支持访问目标网站
    这里的策略是根据节点名称中的关键词判断。
    """
    name = node.get('name', '').lower()
    # 如果节点名称中包含目标域名（去除点），视为可能支持
    for domain in TARGET_DOMAINS:
        domain_keyword = domain.replace('.', '')
        if domain_keyword in name:
            return True
    return False

def main():
    # 文件路径
    clash_yaml_path = 'data/clash.yaml'
    output_yaml_path = 'data/google.yaml'
    
    # 检查文件是否存在
    if not os.path.exists(clash_yaml_path):
        print(f"文件不存在: {clash_yaml_path}")
        return

    # 读取原始配置
    clash_data = load_yaml(clash_yaml_path)

    # 获取代理节点列表
    proxies = clash_data.get('proxies', [])

    # 存放符合条件的节点
    valid_nodes = []

    for node in proxies:
        node_type = node.get('type', '').lower()
        if node_type in SUPPORTED_TYPES:
            if node_can_access(node):
                valid_nodes.append(node)

    # 构建输出配置
    output_yaml = {
        'proxies': valid_nodes
    }

    # 保存到目标文件
    save_yaml(output_yaml, output_yaml_path)

    print(f"符合条件的节点已保存到 {output_yaml_path}")

if __name__ == "__main__":
    main()
