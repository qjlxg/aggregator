#!/bin/bash

# Determine root directory and set paths
current=$(cd "$(dirname "$0")"; pwd)
root_dir="${current%/*}"
clash_path="${root_dir}/clash"
log_file="${root_dir}/data/ji.txt"

# Define log function to append messages with timestamps
log() {
  echo "$(date): $1" >> "$log_file"
}

# Change to Clash directory
cd "${clash_path}"

bin_name="clash-linux"

# Ensure the executable has proper permissions
chmod +x "${bin_name}"

# Read proxies from data/ss.txt
while IFS= read -r subscribe; do
  # Skip empty lines
  if [ -z "$subscribe" ]; then
    continue
  fi

  # Log the start of the proxy test
  log "start check proxy alive, proxy: $subscribe"

  # Remove existing config.yaml to avoid conflicts
  rm -rf config.yaml

  # Download Clash configuration using subconverter
  wget -q -t 2 "https://sub.xeton.dev/sub?target=clash&url=$subscribe&insert=false&emoji=true&list=false&udp=true&tfo=false&expand=true&scv=false&fdn=true&new_name=true&filename=config.yaml" -O config.yaml
  if [ $? -ne 0 ]; then
    log "download config file error, proxy: $subscribe"
    continue
  fi

  # Start Clash in the background and capture its PID
  nohup ./"${bin_name}" -d . -f config.yaml > clash.log 2>&1 &
  clash_pid=$!
  if [ $? -ne 0 ]; then
    log "startup clash failed, proxy: $subscribe"
    continue
  fi

  # Wait for Clash to initialize
  sleep 2.5

  # Set proxy environment variables
  export http_proxy="http://127.0.0.1:7890"
  export https_proxy="http://127.0.0.1:7890"

  # Test connectivity to YouTube and Google (3 attempts each)
  for ((i=1; i<=3; i++)); do
    curl --connect-timeout 6 -m 10 "https://www.youtube.com" >/dev/null 2>&1
    curl --connect-timeout 6 -m 10 "https://www.google.com" >/dev/null 2>&1
  done

  # Perform speed test by downloading a 10MB file
  wget -q --timeout=10 -t 2 --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.66 Safari/537.36 Edg/103.0.1264.44" "https://cachefly.cachefly.net/10mb.test" -O 10mb.test
  if [ $? -ne 0 ]; then
    log "download file 10mb.test failed, proxy: $subscribe"
  else
    log "proxy test succeeded, proxy: $subscribe"
  fi

  # Unset proxy environment variables
  unset http_proxy
  unset https_proxy

  # Remove the test file
  rm -rf ./10mb.test

  # Terminate the specific Clash process
  kill "$clash_pid"
done < "${root_dir}/data/ss.txt"

# Exit cleanly
exit 0
