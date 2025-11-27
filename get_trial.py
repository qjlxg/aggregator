import os
import string
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from datetime import timedelta
from random import choice
from time import time
from urllib.parse import urlsplit, urlunsplit
import multiprocessing

# 依赖的 apis.py 保持不变
from apis import PanelSession, TempEmail, guess_panel, panel_class_map
from subconverter import gen_base64_and_clash_config, get
from utils import (clear_files, g0, keep, list_file_paths, list_folder_paths,
                   read, read_cfg, remove, size2str, str2timestamp,
                   timestamp2str, to_zero, write, write_cfg)

# 全局配置
# 动态设置最大工作线程数，优化资源利用
MAX_WORKERS = min(16, multiprocessing.cpu_count() * 2)  
MAX_TASK_TIMEOUT = 45  # 单任务最大等待时间（秒），避免任务卡死
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
        # 优化点：更清晰的异常消息
        raise Exception("所有默认邮箱域名均被封禁，无法继续注册")
    return choice(available_domains)

def log_error(host: str, email: str, message: str, log: list):
    """记录错误日志，包含主机、邮箱和错误信息"""
    # 优化点：统一使用 f-string 格式化
    log.append(f"{host}({email}): {message}")

def get_sub(session: PanelSession, opt: dict, cache: dict[str, list[str]]):
    """
    获取订阅信息和内容，处理多链接订阅和重定向。
    """
    url = cache['sub_url'][0]
    # 优化点：使用 f-string 构造后缀
    suffix = f" - {g0(cache, 'name')}"
    if 'speed_limit' in opt:
        suffix += f" ⚠️限速 {opt['speed_limit']}"
    
    sub_info = None
    sub_rest = None
    
    try:
        sub_info, *sub_rest = get(url, suffix)
    except Exception:
        # 原始逻辑：处理多链接订阅（以 '|' 分隔）或 URL 重定向导致的失败
        origin = urlsplit(session.host)[:2]
        
        # 重新构造 URL，将每个链接的 scheme 和 netloc 替换为 session.host 的 scheme 和 netloc
        url = '|'.join(urlunsplit(origin + urlsplit(part)[2:]) for part in url.split('|'))
        
        sub_info, *sub_rest = get(url, suffix)
        # 更新缓存中的订阅链接
        cache['sub_url'][0] = url
        
    if not sub_info and hasattr(session, 'get_sub_info'):
        # 尝试通过 API 获取订阅信息
        session.login(cache['email'][0])
        sub_info = session.get_sub_info()

    return sub_info, *sub_rest

def should_turn(session: PanelSession, opt: dict, cache: dict[str, list[str]]):
    """
    判断是否需要轮换账号/续期。返回 (轮换代码, 订阅信息, ...)
    轮换代码: 0-不需要, 1-需要, 2-强制重新注册(邮箱被禁/黑)
    """
    if 'sub_url' not in cache:
        return 1, None, None, None

    now = time()
    try:
        info, *rest = get_sub(session, opt, cache)
    except Exception as e:
        msg = str(e)
        # 判断是否为邮箱被禁用的情况
        if '邮箱' in msg and ('不存在' in msg or '禁' in msg or '黑' in msg):
            if (domain := cache['email'][0].split('@')[1]) not in DEFAULT_EMAIL_DOMAINS:
                # 优化点：防止重复添加被禁用的域名
                if domain not in cache.get('banned_domains', []):
                    cache.setdefault('banned_domains', []).append(domain)
            return 2, None, None, None # 强制重新注册
        raise e

    # 逻辑判断是否需要轮换
    is_expired_or_low_traffic = (
        # 1. 没有订阅信息
        not info
        # 2. 强制轮换
        or opt.get('turn') == 'always'
        # 3. 剩余流量低于 256MB (1 << 28 Byte)
        or float(info['total']) - (float(info['upload']) + float(info['download'])) < (1 << 28)
        # 4. 剩余时间不足
        or (opt.get('expire') != 'never' and info.get('expire') and (
            str2timestamp(info.get('expire')) - now < (
                # 如果设置了 reg_limit，使用 1/7 的已使用时间作为阈值 (原脚本逻辑)
                (now - str2timestamp(cache['time'][0])) / 7 if 'reg_limit' in opt else 
                # 否则使用 2400 秒 (40 分钟) 作为阈值
                2400
            )
        ))
    )

    return int(is_expired_or_low_traffic), info, *rest

def _register(session: PanelSession, email: str, *args, **kwargs):
    """辅助函数：执行注册操作，并返回错误消息或 None"""
    try:
        if session.register(email, *args, **kwargs):
            return None # 注册成功，返回 None
        return "注册返回 False" 
    except Exception as e:
        return str(e)
        
def _register_get_email_code_workflow(kwargs, session: PanelSession, opt: dict, cache: dict[str, list[str]]):
    """尝试通过临时邮箱获取验证码并添加到 kwargs 中。"""
    max_retries = 5
    for retry in range(max_retries):
        tm = TempEmail(banned_domains=cache.get('banned_domains', []))
        try:
            email_domain = get_available_domain(cache)
            email = kwargs['email'] = f"{generate_random_username()}@{email_domain}"
            # 此处依赖 TempEmail 的实现细节，保留原样
            tm.email = email 
        except Exception as e:
            raise Exception(f'获取邮箱失败: {e}')
        
        try:
            session.send_email_code(email)
        except Exception as e:
            msg = str(e)
            if '禁' in msg or '黑' in msg:
                if email_domain not in cache.get('banned_domains', []):
                    cache.setdefault('banned_domains', []).append(email_domain)
                continue # 进入下一次重试
            raise Exception(f'发送邮箱验证码失败({email}): {e}')
        
        email_code = tm.get_email_code(g0(cache, 'name'))
        
        if email_code:
            kwargs['email_code'] = email_code
            return email
        
        # 没获取到验证码，禁用当前域名
        if email_domain not in cache.get('banned_domains', []):
            cache.setdefault('banned_domains', []).append(email_domain)

    raise Exception('获取邮箱验证码失败，重试次数过多')


def _handle_auto_invite_logic(session: PanelSession, opt: dict, cache: dict[str, list[str]], log: list, kwargs: dict, email: str) -> bool:
    """处理自动邀请码和购买的复杂嵌套逻辑。"""
    
    # 逻辑 1: 如果没有 invite_code 且不要求购买，尝试获取邀请码信息
    if 'buy' not in opt and 'invite_code' not in kwargs:
        session.login()
        try:
            code, num, money = session.get_invite_info()
        except Exception as e:
            log_error(session.host, email, str(e), log)
            if '邀请' in str(e):
                cache['auto_invite'] = 'F'
            return False

        if 'auto_invite' not in cache:
            if not money:
                cache['auto_invite'] = 'F'
                return False
            
            balance = session.get_balance()
            plan = session.get_plan(min_price=balance + 0.01, max_price=balance + money)
            if not plan:
                cache['auto_invite'] = 'F'
                return False
            cache['auto_invite'] = 'T'
        
        cache['invite_code'] = [code, num]
        kwargs['invite_code'] = code
        session.reset() # 假设 PanelSession 有 reset 方法
        
        if 'email_code' in kwargs:
            email = _register_get_email_code_workflow(kwargs, session, opt, cache)
        else:
            email_domain = email.split('@')[1]
            email = kwargs['email'] = f"{generate_random_username()}@{email_domain}"

        if (msg := _register(session, **kwargs)):
            log_error(session.host, email, f"使用邀请码重新注册失败: {msg}", log)
            return False
            
    # 逻辑 2: 如果已经有邀请码，判断是否需要购买/更新邀请码
    if 'invite_code' in kwargs:
        if 'invite_code' not in cache or int(cache['invite_code'][1]) == 1 or secrets.choice([0, 1]):
            session.login()
            try_buy(session, opt, cache, log)
            try:
                cache['invite_code'] = [*session.get_invite_info()[:2]]
            except Exception as e:
                if 'invite_code' not in cache:
                    cache['auto_invite'] = 'F'
                else:
                    log_error(session.host, email, str(e), log)
            return True 
        else:
            n = int(cache['invite_code'][1])
            if n > 0:
                cache['invite_code'][1] = str(n - 1)
            return True 
            
    return False 


def register(session: PanelSession, opt: dict, cache: dict[str, list[str]], log: list) -> bool:
    """
    注册新用户，处理多种注册失败和自动邀请码逻辑。
    优化点：将复杂的重试和失败处理流程结构化，提高可读性。
    """
    kwargs = keep(opt, 'name_eq_email', 'reg_fmt', 'aff')
    
    # 1. 初始化邀请码
    if 'invite_code' in cache:
        kwargs['invite_code'] = cache['invite_code'][0]
    elif 'invite_code' in opt:
        kwargs['invite_code'] = choice(opt['invite_code'].split())

    # 2. 准备初始邮箱
    try:
        email_domain = get_available_domain(cache)
    except Exception as e:
        log_error(session.host, '', str(e), log)
        return False
        
    email = kwargs['email'] = f"{generate_random_username()}@{email_domain}"
    
    max_retries = 5
    for retry in range(max_retries):
        msg = None
        try:
            msg = _register(session, **kwargs)
        except Exception as e:
            msg = str(e)

        if not msg:
            # 注册成功
            return True

        # 3. 注册失败处理逻辑
        if '后缀' in msg:
            email_domain = 'qq.com' if email_domain != 'qq.com' else 'gmail.com'
            email = kwargs['email'] = f"{generate_random_username()}@{email_domain}"
        elif '验证码' in msg:
            try:
                email = _register_get_email_code_workflow(kwargs, session, opt, cache)
            except Exception as e:
                log_error(session.host, email, str(e), log)
                raise e
        elif '联' in msg:
            kwargs['im_type'] = True
        elif '邀请人' in msg and g0(cache, 'invite_code', '') == kwargs.get('invite_code'):
            del cache['invite_code']
            if 'invite_code' in opt:
                kwargs['invite_code'] = choice(opt['invite_code'].split())
            else:
                del kwargs['invite_code']
        elif '邀请' in msg and g0(cache, 'auto_invite', 'T') == 'T' and hasattr(session, 'get_invite_info'):
            # 4. 自动邀请码/购买逻辑
            if _handle_auto_invite_logic(session, opt, cache, log, kwargs, email):
                return True
            
            if 'auto_invite' in cache and cache['auto_invite'] == 'F':
                 # 如果 auto_invite 被禁用，则不再重试此路径
                 pass
            elif retry == max_retries - 1:
                 log_error(session.host, email, f"注册失败: {msg}", log)
                 raise Exception(f'注册失败({email}): {msg}{" " + kwargs.get("invite_code") if "邀" in msg else ""}')
            else:
                # 重试
                pass
        else:
            # 5. 其他错误，不再重试
            log_error(session.host, email, f"注册失败: {msg}", log)
            raise Exception(f'注册失败({email}): {msg}{" " + kwargs.get("invite_code") if "邀" in msg else ""}')

    # 循环结束仍未成功
    log_error(session.host, email, f"注册失败: {msg}", log)
    raise Exception(f'注册失败({email}): {msg}{" " + kwargs.get("invite_code") if "邀" in msg else ""}')


def is_checkin(session, opt: dict):
    return hasattr(session, 'checkin') and opt.get('checkin') != 'F'

def try_checkin(session: PanelSession, opt: dict, cache: dict[str, list[str]], log: list):
    if is_checkin(session, opt) and cache.get('email'):
        if len(cache.setdefault('last_checkin', [])) < len(cache['email']):
            cache['last_checkin'] += ['0'] * (len(cache['email']) - len(cache['last_checkin']))
        last_checkin = to_zero(str2timestamp(cache['last_checkin'][0]))
        now = time()
        # 优化点：使用 24 小时作为签到间隔，更严谨
        if now - last_checkin > 24 * 3600:
            try:
                session.login(cache['email'][0])
                session.checkin()
                cache['last_checkin'][0] = timestamp2str(now)
                cache.pop('尝试签到失败', None)
            except Exception as e:
                cache['尝试签到失败'] = [e]
                log_error(session.host, cache['email'][0], f"尝试签到失败: {e}", log)
    else:
        cache.pop('last_checkin', None)

def try_buy(session: PanelSession, opt: dict, cache: dict[str, list[str]], log: list):
    try:
        if (plan := opt.get('buy')):
            return session.buy(plan)
        if (plan := g0(cache, 'buy')):
            if plan == 'pass':
                return False
            try:
                return session.buy(plan)
            except Exception as e:
                del cache['buy']
                cache.pop('auto_invite', None)
                cache.pop('invite_code', None)
                log_error(session.host, cache.get('email', [''])[0], f"上次购买成功但这次购买失败: {e}", log)
        plan = session.buy()
        cache['buy'] = plan or 'pass'
        return plan
    except Exception as e:
        log_error(session.host, cache.get('email', [''])[0], f"购买失败: {e}", log)
    return False

def do_turn(session: PanelSession, opt: dict, cache: dict[str, list[str]], log: list, force_reg=False) -> bool:
    is_new_reg = False
    login_and_buy_ok = False
    reg_limit = opt.get('reg_limit')
    
    # 修正：PanelSession 没有 session.email，应该使用 session.email_address 属性
    email_attr = 'email_address'
    
    if not reg_limit:
        # 1. 无 reg_limit：只用一个账号
        login_and_buy_ok = register(session, opt, cache, log)
        is_new_reg = True
        cache['email'] = [getattr(session, email_attr, 'unknown')]
        if is_checkin(session, opt):
            cache['last_checkin'] = ['0']
    else:
        # 2. 有 reg_limit：轮换使用多个账号
        reg_limit = int(reg_limit)
        
        # 2a. 如果账号数不足 reg_limit 或强制重新注册 (turn == 2)
        if len(cache.setdefault('email', [])) < reg_limit or force_reg:
            login_and_buy_ok = register(session, opt, cache, log)
            is_new_reg = True
            cache['email'].append(getattr(session, email_attr, 'unknown'))
            if is_checkin(session, opt):
                cache.setdefault('last_checkin', []) 
                cache['last_checkin'] += ['0'] * (len(cache['email']) - len(cache['last_checkin']))

        # 2b. 裁剪和轮换账号列表
        if len(cache['email']) > reg_limit:
            del cache['email'][:-reg_limit]
            if is_checkin(session, opt):
                del cache['last_checkin'][:-reg_limit]

        # 轮换到下一个账号
        if cache.get('email'):
            cache['email'] = cache['email'][-1:] + cache['email'][:-1]
            if is_checkin(session, opt):
                cache['last_checkin'] = cache['last_checkin'][-1:] + cache['last_checkin'][:-1]

    if not login_and_buy_ok and cache.get('email'):
        # 如果不是新注册，则尝试使用当前账号登录/购买/签到
        try:
            session.login(cache['email'][0])
        except Exception as e:
            raise Exception(f'登录失败: {e}')
        try_buy(session, opt, cache, log)

    try_checkin(session, opt, cache, log)
    
    # 获取订阅链接并记录时间
    try:
        cache['sub_url'] = [session.get_sub_url(**opt)]
    except Exception as e:
        # 如果 session.get_sub_url 失败，尝试用 session.get_sub
        sub_url = session.get_sub()
        if sub_url:
            cache['sub_url'] = [sub_url]
        else:
            raise Exception(f'获取订阅链接失败: {e}')

    cache['time'] = [timestamp2str(time())]
    
    action_text = "更新订阅链接(新注册)" if is_new_reg else "续费续签"
    log.append(f'{action_text}({session.host}) {cache["sub_url"][0]}')


def try_turn(session: PanelSession, opt: dict, cache: dict[str, list[str]], log: list):
    # 清除之前的错误缓存
    for key in ['更新旧订阅失败', '更新订阅链接/续费续签失败', '获取订阅失败']:
        cache.pop(key, None)

    try:
        turn, *sub = should_turn(session, opt, cache)
    except Exception as e:
        cache['更新旧订阅失败'] = [e]
        log_error(session.host, cache.get('email', [''])[0], f"更新旧订阅失败({cache.get('sub_url', ['N/A'])[0]}): {e}", log)
        return None

    if turn:
        try:
            do_turn(session, opt, cache, log, force_reg=turn == 2)
        except Exception as e:
            cache['更新订阅链接/续费续签失败'] = [e]
            log_error(session.host, cache.get('email', [''])[0], f"更新订阅链接/续费续签失败: {e}", log)
            return sub
        
        # 重新获取最新的订阅信息
        try:
            sub = get_sub(session, opt, cache)
        except Exception as e:
            cache['获取订阅失败'] = [e]
            log_error(session.host, cache.get('email', [''])[0], f"获取订阅失败({cache['sub_url'][0]}): {e}", log)

    return sub

def cache_sub_info(info, opt: dict, cache: dict[str, list[str]]):
    if not info:
        raise Exception('no sub info')
    used = float(info["upload"]) + float(info["download"])
    total = float(info["total"])
    rest_size_str = size2str(total - used)

    if opt.get('expire') == 'never' or not info.get('expire'):
        expire_str = '永不过期'
        rest_time_str = ''
    else:
        ts = str2timestamp(info['expire'])
        expire_str = timestamp2str(ts)
        rest_time_str = f' {timedelta(seconds=ts - time())}'
        
    rest = f'(剩余 {rest_size_str}{rest_time_str})'
    
    cache['sub_info'] = [size2str(used), size2str(total), expire_str, rest]

def save_sub_base64_and_clash(base64, clash, host, opt: dict):
    return gen_base64_and_clash_config(
        base64_path=f'trials/{host}',
        clash_path=f'trials/{host}.yaml',
        providers_dir=f'trials_providers/{host}',
        base64=base64,
        clash=clash,
        exclude=opt.get('exclude')
    )

def save_sub(info, base64, clash, base64_url, clash_url, host, opt: dict, cache: dict[str, list[str]], log: list):
    for key in ['保存订阅信息失败', '保存base64/clash订阅失败']:
        cache.pop(key, None)

    try:
        cache_sub_info(info, opt, cache)
    except Exception as e:
        cache['保存订阅信息失败'] = [e]
        log_error(host, cache.get('email', [''])[0], f"保存订阅信息失败({clash_url}): {e}", log)
    
    try:
        node_n = save_sub_base64_and_clash(base64, clash, host, opt)
        if (d := node_n - int(g0(cache, 'node_n', 0))) != 0:
            log.append(f'{host} 节点数 {"+" if d > 0 else ""}{d} ({node_n})')
        cache['node_n'] = [str(node_n)]
    except Exception as e:
        cache['保存base64/clash订阅失败'] = [e]
        log_error(host, cache.get('email', [''])[0], f"保存base64/clash订阅失败({base64_url})({clash_url}): {e}", log)

def get_and_save(session: PanelSession, host, opt: dict, cache: dict[str, list[str]], log: list):
    try:
        try_checkin(session, opt, cache, log)
        sub = try_turn(session, opt, cache, log)
        if sub:
            save_sub(*sub, host, opt, cache, log)
    except Exception as e:
        log_error(host, cache.get('email', [''])[0], f"get_and_save 异常: {e}", log)

def new_panel_session(host, cache: dict[str, list[str]], log: list) -> PanelSession | None:
    try:
        if 'type' not in cache:
            info = guess_panel(host) 
            if isinstance(info, dict):
                # 旧版 guess_panel 逻辑
                if 'type' not in info:
                    if (e := info.get('error')):
                        log.append(f"{host} 判别类型失败: {e}")
                    else:
                        log.append(f"{host} 未知类型")
                    return None
                cache.update(info)
            else:
                # 假设 guess_panel 直接返回 Class (PanelSession type)
                panel_class = info
                # 需要通过 host 猜测出 type 名称并存入 cache
                cache['type'] = [panel_class.__name__.replace('Session', '')] 
        
        panel_class = panel_class_map[g0(cache, 'type')]
        return panel_class(g0(cache, 'api_host', host), **keep(cache, 'auth_path', getitem=g0))
        
    except Exception as e:
        log.append(f"{host} new_panel_session 异常: {e}")
        return None

def get_trial(host, opt: dict, cache: dict[str, list[str]]):
    log = []
    try:
        session = new_panel_session(host, cache, log)
        if session:
            # 优化点：将必要的全局函数和配置注入到 session 对象中，方便 PanelSession 子类使用
            session.generate_random_username = generate_random_username
            session.get_available_domain = get_available_domain
            session.opt = opt 
            
            get_and_save(session, host, opt, cache, log)
            
            # 检查 session.host 是否是新的 API host
            if hasattr(session, 'host') and session.host != host:
                if urlsplit(session.host).netloc != urlsplit(host).netloc:
                    cache['api_host'] = [session.host] 
                
    except Exception as e:
        log.append(f"{host} 处理异常: {e}")
    return log

def build_options(cfg):
    opt = {
        host: dict(zip(opt[::2], opt[1::2]))
        for host, *opt in cfg
    }
    return opt

if __name__ == '__main__':
    pre_repo = read('.github/repo_get_trial')
    cur_repo = os.getenv('GITHUB_REPOSITORY')
    if pre_repo != cur_repo:
        remove('trial.cache')
        write('.github/repo_get_trial', cur_repo)

    cfg = read_cfg('trial.cfg')['default']
    opt = build_options(cfg)
    cache = read_cfg('trial.cache', dict_items=True)

    # 清理不再使用的缓存和文件
    for host in [*cache]:
        if host not in opt:
            del cache[host]

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

    # 并发执行和超时控制
    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        futures = []
        # 确保 cache.setdefault(h, {}) 被调用，防止 Key Error
        args = [(h, opt[h], cache.setdefault(h, {})) for h, *_ in cfg] 
        for h, o, c in args:
            futures.append(executor.submit(get_trial, h, o, c))
        
        # 收集结果并处理超时/异常
        for future in as_completed(futures):
            try:
                log = future.result(timeout=MAX_TASK_TIMEOUT)
                for line in log:
                    print(line, flush=True)
            except TimeoutError:
                print(f"有任务超时（超过{MAX_TASK_TIMEOUT}秒未完成），已跳过。", flush=True)
            except Exception as e:
                print(f"任务异常: {e}", flush=True)

    total_node_n = gen_base64_and_clash_config(
        base64_path='trial',
        clash_path='trial.yaml',
        providers_dir='trials_providers',
        # 优化点：生成器表达式
        base64_paths=(path for path in list_file_paths('trials') if os.path.splitext(path)[1].lower() != '.yaml'),
        providers_dirs=(path for path in list_folder_paths('trials_providers') if '.' in os.path.basename(path))
    )

    print('总节点数', total_node_n)
    write_cfg('trial.cache', cache)
