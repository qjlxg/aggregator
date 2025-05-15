import base64
import requests
import os

def convert_multiple_to_base64(urls):
    combined_text = ""
    
    # 从每个URL下载文本并聚合
    for url in urls:
        response = requests.get(url)
        if response.status_code == 200:
            combined_text += response.text + "\n"  
        else:
            print(f"Failed to fetch data from URL: {url}")

    # 将聚合的文本按行分割
    lines = combined_text.splitlines()
    
    # 使用集合去重，获取唯一的节点
    unique_nodes = list(set(lines))
    
    # 对唯一节点排序（确保数字升序排列的基础）
    unique_nodes.sort()
    
    # 生成新的节点名称，格式为"yahoo-001"、"yahoo-002"等
    new_nodes = []
    for i, node in enumerate(unique_nodes, start=1):
        new_node_name = f"yahoo-{i:03d}"  # 使用 :03d 确保数字是三位数，如001、002
        new_nodes.append(new_node_name)
    
    # 将新节点名称重新组合成文本
    new_combined_text = "\n".join(new_nodes)
    
    # 将新文本编码为base64
    encoded_bytes = base64.b64encode(new_combined_text.encode('utf-8'))
    encoded_text = encoded_bytes.decode('utf-8')

    # 检查是否需要更新文件
    needs_update = True
    if os.path.exists('base64.txt'):
        with open('base64.txt', 'r') as f:
            existing_content = f.read()
            if encoded_text == existing_content:
                needs_update = False

    # 仅在内容变化时保存base64编码文本
    if needs_update:
        with open('base64.txt', 'w') as f:
            f.write(encoded_text)
        print("Conversion complete and changes saved.")
    else:
        print("No changes detected.")

if __name__ == "__main__":
    urls = [
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/base.txt",
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/ss.txt",
        "https://github.com/qjlxg/hy2/raw/refs/heads/main/configtg.txt",
    ]
    convert_multiple_to_base64(urls)
