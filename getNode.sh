#!/bin/bash

# 日期变量
currentdate=$(date +%Y%m%d)
currentmonth=$(date +%Y%m)
currentmonths=$(date +%m)
currentyears=$(date +%Y)

# 订阅链接（Clash 和 V2Ray）
clash_urls=(
  "https://proxy.v2gh.com/https://raw.bgithub.xyz/Pawdroid/Free-servers/main/sub"
  "https://proxy.v2gh.com/https://raw.bgithub.xyz/ermaozi01/free_clash_vpn/main/subscribe/clash.yml"
)

v2ray_urls=(
  "https://proxy.v2gh.com/https://raw.bgithub.xyz/Pawdroid/Free-servers/main/sub"
  "https://proxy.v2gh.com/https://raw.bgithub.xyz/ermaozi01/free_clash_vpn/main/subscribe/clash.yml"
)

config_url="https://raw.bgithub.xyz/NZESupB/Profile/main/outpref/pypref/pyfull.ini"
filename="GitHub-GetNode"
subscribe_url="https://api-suc.0z.gs/sub?target="

# 函数：构造订阅链接
construct_subscribe_url() {
  local target="$1"
  local urls=("${!2}") # Indirect reference to the array
  local complete_url="${subscribe_url}${target}&url="
  local first=true

  for url in "${urls[@]}"; do
    if $first; then
      complete_url+="${url}"
      first=false
    else
      complete_url+="|${url}"
    fi
  done

  complete_url+="&insert=false&config=${config_url}&filename=${filename}&append_type=true&emoji=true&list=false&tfo=false&scv=true&fdn=false&sort=true&udp=true&new_name=true"
  echo "$complete_url"
}

# 清理旧文件（可选，如果文件存在，则删除）
if [ -f "./clash.yaml" ]; then
  rm ./clash.yaml
fi

if [ -f "./v2ray.txt" ]; then
  rm ./v2ray.txt
fi

# 下载订阅
echo "Getting subscribe..."

subscribeclash=$(construct_subscribe_url "clash" clash_urls[@])
subscribeV2ray=$(construct_subscribe_url "v2ray" v2ray_urls[@])

wget -q "$subscribeclash" -O ./clash.yaml
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
