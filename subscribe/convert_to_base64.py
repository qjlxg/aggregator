import base64
import requests
import os

def convert_multiple_to_base64(urls):
    combined_text = ""
    
    # 从每个 URL 下载文本并聚合
    for url in urls:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                combined_text += response.text + "\n"
            else:
                print(f"无法从 URL 获取数据: {url} (状态码: {response.status_code})")
        except Exception as e:
            print(f"获取 URL {url} 时出错: {e}")
    
    # 调试：打印下载的原始文本
    print("下载的聚合文本:\n", combined_text if combined_text else "【无内容】")
    
    # 将聚合文本按行分割
    lines = combined_text.splitlines()
    
    # 移除空行并去重
    unique_nodes = list(set(line.strip() for line in lines if line.strip()))
    
    # 调试：打印去重后的唯一行
    print("去重后的唯一行:\n", unique_nodes if unique_nodes else "【无唯一节点】")
    
    # 对唯一节点排序
    unique_nodes.sort()
    
    # 生成新的节点名称，格式为 "yahoo-001"、"yahoo-002" 等
    new_nodes = []
    for i, _ in enumerate(unique_nodes, start=1):
        new_node_name = f"yahoo-{i:03d}"  # 仅生成新名称，忽略原始内容
        new_nodes.append(new_node_name)
    
    # 调试：打印生成的新节点名称
    print("生成的新节点名称:\n", new_nodes if new_nodes else "【无新节点】")
    
    # 将新节点名称重新组合成文本
    new_combined_text = "\n".join(new_nodes)
    
    # 将新文本编码为 base64
    encoded_bytes = base64.b64encode(new_combined_text.encode('utf-8'))
    encoded_text = encoded_bytes.decode('utf-8')
    
    # 检查是否需要更新文件
    needs_update = True
    if os.path.exists('base64.txt'):
        with open('base64.txt', 'r') as f:
            existing_content = f.read()
            if encoded_text == existing_content:
                needs_update = False
    
    # 仅在内容变化时保存 base64 编码文本
    if needs_update:
        try:
            with open('base64.txt', 'w') as f:
                f.write(encoded_text)
            print("文件写入成功，base64.txt 已更新。")
        except Exception as e:
            print(f"写入文件时出错: {e}")
    else:
        print("未检测到变化，文件未更新。")

if __name__ == "__main__":
    urls = [
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/base.txt",
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/ss.txt",
        "https://github.com/qjlxg/hy2/raw/refs/heads/main/configtg.txt",
    ]
    convert_multiple_to_base64(urls)
