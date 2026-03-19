import os

def main():
    search_filename = 'valid-domains.txt'
    output_path = 'data/all-unique-domains.txt' # 汇总后的去重文件
    unique_domains = set()

    # 1. 递归搜索 data 目录
    data_dir = 'data'
    if not os.path.exists(data_dir):
        print(f"未找到 {data_dir} 目录，请检查路径。")
        return

    for root, dirs, files in os.walk(data_dir):
        if search_filename in files:
            file_path = os.path.join(root, search_filename)
            print(f"正在处理文件: {file_path}")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        domain = line.strip()
                        if domain:
                            unique_domains.add(domain)
            except Exception as e:
                print(f"读取 {file_path} 失败: {e}")

    # 2. 去重后写入目标文件
    if unique_domains:
        # 排序可以让 Git Diff 更清晰
        sorted_domains = sorted(list(unique_domains))
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted_domains) + '\n')
        print(f"成功！去重后共保存 {len(sorted_domains)} 个域名到 {output_path}")
    else:
        print("未发现有效域名数据。")

if __name__ == "__main__":
    main()
