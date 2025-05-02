import yaml
import os

# 支持的节点类型
SUPPORTED_TYPES = ['vmess', 'ss', 'hysteria2', 'trojan', 'vless']

def load_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def save_yaml(data, file_path):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True)

def main():
    input_path = 'data/clash.yaml'
    output_path = 'data/google.yaml'

    if not os.path.exists(input_path):
        print(f"文件不存在: {input_path}")
        return

    clash_data = load_yaml(input_path)
    proxies = clash_data.get('proxies', [])

    # 只筛选类型在支持列表中的节点
    valid_nodes = [
        node for node in proxies
        if node.get('type', '').lower() in SUPPORTED_TYPES
    ]

    print(f"共有 {len(proxies)} 个节点，筛选出 {len(valid_nodes)} 个支持类型节点。")

    if valid_nodes:
        save_yaml({'proxies': valid_nodes}, output_path)
        print(f"支持访问Google和YouTube节点已保存到 {output_path}")
    else:
        # 如果没有符合条件的节点
        if os.path.exists(output_path):
            print("没有支持的节点，已覆盖原有文件为空内容。")
        else:
            print("没有支持的节点，未生成文件。")

if __name__ == "__main__":
    main()
