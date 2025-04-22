
#!/bin/bash

# 获取当前时间的月份和日期（格式化为 04 月 25 日 → 0425）
current_date=$(date +%y%m%d)

# 定义目标路径（例如 sub/0425/）
target_dir="sub/${current_date}"

# 创建目标目录（自动处理多层路径）
mkdir -p "$target_dir"

# 检查 data 目录是否存在
if [ -d "data" ]; then
  # 复制 data 目录下的所有内容到目标目录（保留文件结构）
  cp -r data/* "$target_dir" 2>/dev/null

  # 检查是否复制成功
  if [ $? -eq 0 ]; then
    echo "✅ 文件已复制到: $target_dir"
  else
    echo "⚠️  data 目录为空，未复制任何文件"
  fi
else
  echo "❌ 错误: data 目录不存在"
fi
