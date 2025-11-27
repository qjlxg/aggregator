import os
import string
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from datetime import timedelta
from random import choice
from time import time
from urllib.parse import urlsplit, urlunsplit
import multiprocessing

# 导入 requests 以便进行精确的异常捕获
import requests

from apis import PanelSession, TempEmail, guess_panel, panel_class_map, new_panel_session
from subconverter import gen_base64_and_clash_config, get
from utils import (clear_files, g0, keep, list_file_paths, list_folder_paths,
                   read, read_cfg, remove, size2str, str2timestamp,
                   timestamp2str, to_zero, write, write_cfg)

# 全局配置
MAX_WORKERS = min(16, multiprocessing.cpu_count() * 2)  # 动态设置最大工作线程数
MAX_TASK_TIMEOUT = 30  # **优化点：单任务最大等待时间（秒），已缩短**
DEFAULT_EMAIL_DOMAINS = ['gmail.com', 'qq.com', 'outlook.com']  # 默认邮箱域名池


def generate_random_username(length=12) -> str:
    """生成指定长度的随机用户名，仅包含字母和数字"""
    chars = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def get_available_domain(cache: dict[str, list[str]]) -> str:
    """从域名池中选择一个未被封禁的域名"""
    banned_domains = cache.get('banned_domains', [])
    available_domains = [d for d in DEFAULT_EMAIL_DOMAINS if d not in banned_domains]
    if not available_domains:
        used_emails = cache.get('used_emails', [])
        banned_domains_only = [e.split('@')[1] for e in used_emails]
        available_domains = [d for d in banned_domains_only if d not in banned_domains]

    if available_domains:
        return choice(available_domains)
    return choice(DEFAULT_EMAIL_DOMAINS)


def get_trial(host: str, opt: dict, cache: dict) -> list[str]:
    """获取单个主机的试用订阅并保存配置，返回日志信息"""
    log = []

    if host not in cache:
        cache[host] = {}
    c = cache[host]

    try:
        log.append(f"[{host}] 开始处理...")

        # 1. 建立会话
        session = new_panel_session(host, opt, c)

        # 2. 检查是否需要续订或轮换
        if session.should_turn():
            log.append(f"[{host}] 需要轮换（过期、流量不足或强制刷新）。")

            # 3. 注册新账户/登录
            session.try_turn()

            # 4. 尝试签到
            session.try_checkin()

            # 5. 尝试购买（免费）套餐
            session.try_buy()
        else:
            log.append(f"[{host}] 订阅有效，无需轮换。")

        # 6. 获取和保存订阅链接
        sub_url = session.get_sub()
        if sub_url:
            log.append(f"[{host}] 成功获取订阅链接。")

            node_n = session.save_sub_base64_and_clash(sub_url)
            log.append(f"[{host}] 订阅保存完毕，包含 {node_n} 个节点。")

            # 更新缓存
            c['sub_url'] = sub_url
            c['node_n'] = node_n
            c['timestamp'] = timestamp2str(time())
        else:
            log.append(f"[{host}] ⚠️ 未能获取到订阅链接，请检查。")
            c['node_n'] = 0

    # **优化点：更清晰的异常捕获和日志**
    except requests.exceptions.Timeout:
        log.append(f"[{host}] ❌ 任务失败：网络连接或读取超时（已启用强制短超时）。")
    except requests.exceptions.RequestException as e:
        log.append(f"[{host}] ❌ 任务失败：网络请求异常，原因：{type(e).__name__}。")
    except Exception as e:
        # 捕获其他如 API 解析错误、逻辑错误等
        log.append(f"[{host}] ❌ 任务失败：内部逻辑或 API 错误。")
        log.append(f"[{host}] 错误详情: {e}")

    log.append(f"[{host}] 处理结束。")
    return log


def new_panel_session(host: str, opt: dict, cache: dict) -> PanelSession:
    """创建并配置 PanelSession 实例"""
    if host.startswith('http'):
        url_parsed = urlsplit(host)
        host = urlunsplit(url_parsed[:2] + ('', '', ''))
    
    # 获取会话类
    panel_class = guess_panel(host)

    # 实例化会话
    session = panel_class(host, **opt)

    # 补充公共配置
    session.host = host
    session.opt = opt
    session.cache = cache
    session.generate_random_username = generate_random_username
    session.get_available_domain = get_available_domain
    session.get = get

    # 将常用的方法添加到会话对象
    session.save_sub_base64_and_clash = lambda url: save_sub_base64_and_clash(host, url)
    session._get_email_and_email_code = lambda *args: _get_email_and_email_code(session, *args)
    session.should_turn = lambda: should_turn(session)
    session.try_turn = lambda: try_turn(session)
    session.try_checkin = lambda: try_checkin(session)
    session.try_buy = lambda: try_buy(session)

    return session

# ... (should_turn, try_turn, try_checkin, try_buy, save_sub_base64_and_clash, _get_email_and_email_code 等依赖函数与原脚本保持一致) ...


if __name__ == '__main__':
    # 1. 读取配置和缓存
    cfg = read_cfg('trial.cfg')
    opt = {h: o for h, o, c in cfg}
    cache = read('trial.cache', {})

    # 清理不再需要的订阅文件
    for path in list_file_paths('trials'):
        host, ext = os.path.splitext(os.path.basename(path))
        if ext != '.yaml':
            host += ext
        else:
            host = host.split('_')[0]
        if host not in opt:
            remove(path)

    for path in list_folder_paths('trials_providers'):
        host = os.path.basename(path)
        if '.' in host and host not in opt:
            clear_files(path)
            remove(path)

    print("========== 开始多任务并发执行 ==========", flush=True)

    # 2. **优化点：改进并发执行和超时捕获**
    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        futures = []
        args = [(h, opt[h], cache.get(h, {})) for h, *_ in cfg] # 修正缓存访问，避免键错误
        
        # 提交任务
        for h, o, c in args:
            futures.append(executor.submit(get_trial, h, o, c))

        # 收集结果
        for future in as_completed(futures):
            try:
                log = future.result(timeout=MAX_TASK_TIMEOUT)
                for line in log:
                    print(line, flush=True)
            except TimeoutError:
                # 优化点：更清晰的超时日志
                print(f"**任务超时**（超过 {MAX_TASK_TIMEOUT} 秒未完成），已强制跳过。", flush=True)
            except Exception as e:
                print(f"任务异常: {e}", flush=True)

    print("========== 任务执行完毕，开始合并配置 ==========", flush=True)

    # 3. 合并配置和写入缓存
    total_node_n = gen_base64_and_clash_config(
        base64_path='trial',
        clash_path='trial.yaml',
        providers_dir='trials_providers',
        base64_paths=(path for path in list_file_paths('trials') if os.path.splitext(path)[1] not in ('.yaml', '.json')),
        provider_paths=list_file_paths('trials_providers')
    )
    print(f"总节点数: {total_node_n}", flush=True)
    write_cfg('trial.cfg', cfg)
    write('trial.cache', cache)
    print("========== 脚本运行结束 ==========", flush=True)
