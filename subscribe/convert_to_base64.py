import base64
import requests
import os

# 第一步：下载、聚合、重命名、去重并保存节点
def process_and_save_nodes(urls, output_file='processed_nodes.txt'):
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
    
    # 将新节点名称保存到文件
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(new_nodes))
        print(f"处理后的节点已保存到 {output_file}")
    except Exception as e:
        print(f"写入文件 {output_file} 时出错: {e}")

# 第二步：读取处理后的文件并转换为 base64
def convert_to_base64(input_file='processed_nodes.txt', output_file='base64.txt'):
    if not os.path.exists(input_file):
        print(f"错误: {input_file} 不存在。请先运行第一步。")
        return
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 调试：打印读取的内容
        print(f"从 {input_file} 读取的内容:\n", content if content else "【文件为空】")
        
        # 编码为 base64
        encoded_bytes = base64.b64encode(content.encode('utf-8'))
        encoded_text = encoded_bytes.decode('utf-8')
        
        # 保存 base64 编码内容
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(encoded_text)
        print(f"base64 编码内容已保存到 {output_file}")
    except Exception as e:
        print(f"转换或写入 base64 文件时出错: {e}")

if __name__ == "__main__":
    urls = [
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/base.txt",
        "https://github.com/qjlxg/aggregator/raw/refs/heads/main/data/ss.txt",
        "https://github.com/qjlxg/hy2/raw/refs/heads/main/configtg.txt",
    ]
    
    # 执行第一步
    process_and_save_nodes(urls)
    
    # 执行第二步
    convert_to_base64()
