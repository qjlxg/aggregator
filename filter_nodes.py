import yaml
import os

# 支持的节点类型
SUPPORTED_TYPES = ['vmess', 'ss', 'hysteria2', 'trojan', 'vless']

# 目标网站关键词，用于判断节点是否支持访问
TARGET_DOMAINS = ['google.com', 'youtube.com']

def load_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def save_yaml(data, file_path):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True)

def node_can_access(node):
    name = node.get('name', '').lower()
    for domain in TARGET_DOMAINS:
        domain_keyword = domain.replace('.', '')
        if domain_keyword in name:
            return True
    return False

def main():
    input_path = 'data/clash.yaml'
    output_path = 'data/google.yaml'

    if not os.path.exists(input_path):
        print(f"文件不存在: {input_path}")
        return

    clash_data = load_yaml(input_path)
    proxies = clash_data.get('proxies', [])

    valid_nodes = []

    for node in proxies:
        node_type = node.get('type', '').lower()
        if node_type in SUPPORTED_TYPES:
            if node_can_access(node):
                valid_nodes.append(node)

    save_yaml({'proxies': valid_nodes}, output_path)
    print(f"符合条件的节点已保存到 {output_path}")

if __name__ == "__main__":
    main()
