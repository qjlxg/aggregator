# cf-optimizer.py
import sys

# 经过验证的 Cloudflare 核心稳定节点
STABLE_IPS = [
    "104.16.0.1", "104.16.1.1", "104.16.2.1", "172.64.0.1", 
    "172.64.1.1", "162.159.1.1", "162.159.1.2", "1.0.0.1"
]

def main():
    try:
        # 直接生成 candidate_ips.txt
        with open("candidate_ips.txt", "w") as f:
            for ip in STABLE_IPS:
                f.write(ip + "\n")
        print(f"成功生成 {len(STABLE_IPS)} 个稳定 IP")
    except Exception as e:
        print(f"写入失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
