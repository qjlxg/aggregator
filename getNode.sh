#!/bin/bash

# 日期变量
currentdate=$(date +%Y%m%d)
currentmonth=$(date +%Y%m)
currentmonths=$(date +%m)
currentyears=$(date +%Y)

#  订阅链接（Clash 和 V2Ray），使用换行符和续行符 \ 使其更易读
# 注意：这里的缩进是为了代码可读性，实际执行时会被忽略
subscribe_url="https://api-suc.0z.gs/sub?target="  # 公共前缀

clash_urls=(
  "https://proxy.v2gh.com/https://raw.bgithub.xyz/Pawdroid/Free-servers/main/sub"
  "https://raw.githubusercontent.com//ermaozi01/free_clash_vpn/main/subscribe/clash.yml"
)
v2ray_urls=(
  "https://proxy.v2gh.com/https://raw.bgithub.xyz/Pawdroid/Free-servers/main/sub"
  "https://raw.githubusercontent.com/ermaozi01/free_clash_vpn/main/subscribe/clash.yml"
)

config_url="https://raw.githubusercontent.com/NZESupB/Profile/main/outpref/pypref/pyfull.ini"
filename="GitHub-GetNode"

construct_subscribe_url() {
  local target=$1
  local urls=("$@")
  shift
  local url_string=""
  for url in "${urls[@]}"; do
    url_string+="$url%7C" #使用%7C代替管道符号|
  done
  url_string=${url_string%?} #去掉最后一个管道符

  echo "${subscribe_url}${target}&url=${url_string}&insert=false&config=${config_url}&filename=${filename}&append_type=true&emoji=true&list=false&tfo=false&scv=true&fdn=false&sort=true&udp=true&new_name=true"
}

subscribeclash=$(construct_subscribe_url "clash" "${clash_urls[@]}")
subscribeV2ray=$(construct_subscribe_url "v2ray" "${v2ray_urls[@]}")


# 清理旧文件（可选，如果文件存在，则删除）
if [ -f "./clash.yaml" ]; then
  rm ./clash.yaml
fi

if [ -f "./v2ray.txt" ]; then
  rm ./v2ray.txt
fi

# 下载订阅
echo "Getting subscribe..."
wget -q "$subscribeclash" -O ./clash.yaml  # 使用 -q 减少 wget 输出
wget -q "$subscribeV2ray" -O ./v2ray.txt

# 检查下载结果
if [ $? -eq 0 ]; then
  echo "Get subscribe successfully!"
else
  echo "Failed to get subscribe! Check the URLs and network connection."
  exit 1  # 退出脚本，表示发生错误
fi

echo "Hope you have a good day~"
echo "Bye~"
