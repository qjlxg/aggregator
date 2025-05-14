#!/bin/bash

# Clash path
current=$(cd "$(dirname "$0")";pwd)
clash_path="${current%/*}/clash"

# Change workspace
cd ${clash_path}

bin_name="clash-linux"

# Make executable
chmod +x ${bin_name}

# Read proxies from data/ss.txt
while IFS= read -r subscribe; do
  # Skip empty lines
  if [ -z "$subscribe" ]; then
    continue
  fi

  echo "start check proxy alive, proxy: $subscribe"

  # Delete config.yaml if it exists
  rm -rf config.yaml

  # Download config.yaml for this proxy using subconverter
  wget -q -t 2 "https://sub.xeton.dev/sub?target=clash&url=$subscribe&insert=false&emoji=true&list=false&udp=true&tfo=false&expand=true&scv=false&fdn=true&new_name=true&filename=config.yaml" -O config.yaml
  if [ $? -ne 0 ]; then
    echo "download config file error, proxy: $subscribe"
    continue
  fi

  # Start Clash
  nohup ./${bin_name} -d . -f config.yaml &
  if [ $? -ne 0 ]; then
    echo "startup clash failed, proxy: $subscribe"
    continue
  fi

  # Wait a moment
  sleep 2.5

  # Set system proxy
  export http_proxy=http://127.0.0.1:7890
  export https_proxy=http://127.0.0.1:7890

  # Test connectivity
  for((i=1;i<=3;i++))
  do
    curl --connect-timeout 6 -m 10 "https://www.youtube.com" >/dev/null 2>&1
    curl --connect-timeout 6 -m 10 "https://www.google.com" >/dev/null 2>&1
  done

  # Speed test
  wget -q --timeout=10 -t 2 --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.66 Safari/537.36 Edg/103.0.1264.44" "https://cachefly.cachefly.net/10mb.test" -O 10mb.test
  if [ $? -ne 0 ]; then
    echo "download file 10mb.test failed, proxy: $subscribe"
  else
    echo "proxy test succeeded, proxy: $subscribe"
  fi

  # Unset proxy
  unset http_proxy
  unset https_proxy

  # Clear test file
  rm -rf ./10mb.test

  # Close Clash
  pkill -9 ${bin_name}
done < data/ss.txt

exit 0
