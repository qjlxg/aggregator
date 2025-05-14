#!/bin/bash

# 获取脚本所在目录并设置 clash_path
clash_path="$(dirname "$0")/data"

# 更改工作目录
cd "${clash_path}"

bin_name="clash-linux"

# 确保可执行
chmod +x "${bin_name}"

# 下载配置文件
config_url="https://raw.githubusercontent.com/qjlxg/aggregator/main/data/clash.yaml"
wget -q -t 2 "${config_url}" -O config.yaml

if [ $? -ne 0 ]; then
    echo "download config file error"
    exit 1
fi

# 启动 Clash
nohup ./"${bin_name}" -d . -f config.yaml &

if [ $? -ne 0 ]; then
    echo "startup clash failed"
    cat config.yaml
    exit 1
fi

# 等待 Clash 启动
sleep 2.5

# 设置系统代理
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890

# 测试连通性（Google 和 YouTube）
for ((i=1; i<=3; i++))
do
  curl --connect-timeout 6 -m 10 "https://www.youtube.com" >/dev/null 2>&1
  curl --connect-timeout 6 -m 10 "https://www.google.com" >/dev/null 2>&1
done

# 下载速度测试
wget -q --timeout=10 -t 2 --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.66 Safari/537.36 Edg/103.0.1264.44" "https://cachefly.cachefly.net/10mb.test" -O 10mb.test

if [ $? -ne 0 ]; then
    echo "download file 10mb.test failed"
else
    echo "download file 10mb.test succeeded"
fi

# 取消代理设置
unset http_proxy
unset https_proxy

# 清理
rm -rf ./10mb.test

# 关闭 Clash
pkill -9 "${bin_name}"

exit 0
