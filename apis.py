import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from random import choice
from threading import RLock, Thread
from time import sleep, time
from urllib.parse import (parse_qsl, unquote_plus, urlencode, urljoin,
                          urlsplit, urlunsplit)

import json5
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
# from requests.structures import CaseInsensitiveDict
# from selenium.webdriver.support.expected_conditions import any_of, title_is
# from selenium.webdriver.support.ui import WebDriverWait
# from undetected_chromedriver import Chrome, ChromeOptions
from urllib3 import Retry
from urllib3.util import parse_url

from utils import (cached, get, keep, parallel_map, rand_id, str2size,
                   str2timestamp)

REDIRECT_TO_GET = 1
REDIRECT_ORIGIN = 2
REDIRECT_PATH_QUERY = 4

re_scheme = re.compile(r'^(?:([a-z]*):)?[\\\\/]*', re.I)

re_checked_in = re.compile(r'(?:已经?|重复)签到')
re_var_sub_token = re.compile(r'var sub_token = \"(.+?)\"')
re_email_code = re.compile(r'(?:码|碼|証|code).*?(?<![\da-z])([\da-z]{6})(?![^\da-z])', re.I | re.S)

re_snapmail_domains = re.compile(r'emailDomainList.*?(\[.*?\])')
re_mailcx_js_path = re.compile(r'(\/[^\s"]+\/js\/vendor\.js)')


class Response:
    def __init__(self, r: requests.Response, session: 'Session'):
        self.r = r
        self.session = session
        self.text = r.text
        self.status_code = r.status_code
        self.ok = r.ok
        self.url = r.url

    def json(self):
        return self.r.json()

    def raise_for_status(self):
        return self.r.raise_for_status()


class Session:
    def __init__(self, host: str, redirect_mode: int, verify=True, **kwargs):
        self.host = host
        self.redirect_mode = redirect_mode
        self.__session = requests.Session()
        self.__session.verify = verify
        self.__session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36'

        # ==================== 优化点：网络加速和重试配置 ====================
        # 配置重试策略：总共重试 3 次，针对 500 级别错误进行重试
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=frozenset(['GET', 'POST', 'PATCH', 'HEAD'])
        )
        # 挂载适配器
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.__session.mount('http://', adapter)
        self.__session.mount('https://', adapter)
        
        # 强制短超时（连接 5s，读取 10s）。这是提速的关键。
        self.default_timeout = (5, 10)
        # ==================== 优化点：网络加速和重试配置 (结束) ====================


    def urljoin(self, url: str) -> str:
        if not re_scheme.match(url):
            url = urljoin(self.host, url)
        return url

    def __request(self, method: str, url: str, **kwargs) -> Response:
        url = self.urljoin(url)

        # 优化点：传入短超时
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.default_timeout

        if self.redirect_mode & REDIRECT_TO_GET and method == 'post':
            r = self.__session.request(method, url, **kwargs)
            if r.status_code == 302 and parse_url(r.headers.get('location', '')).query:
                method = 'get'
                url = self.urljoin(r.headers['location'])
                kwargs.pop('data', None)
                kwargs.pop('json', None)
            else:
                return Response(r, self)

        if self.redirect_mode & REDIRECT_ORIGIN and method == 'get' and self.host:
            kwargs.setdefault('allow_redirects', False)
            while True:
                r = self.__session.request(method, url, **kwargs)
                if r.status_code != 302:
                    break
                location = r.headers.get('location')
                if not location:
                    break
                url = self.urljoin(location)
                if urlsplit(url).netloc == urlsplit(self.host).netloc:
                    continue
                url_parsed = urlsplit(url)
                if url_parsed.query:
                    url = urlunsplit(url_parsed._replace(query=urlencode(parse_qsl(url_parsed.query), doseq=True)))
                if urlsplit(url).query != urlsplit(r.headers.get('location', '')).query:
                    url = urlunsplit(urlsplit(url)._replace(query=urlsplit(r.headers.get('location', '')).query))

                if self.redirect_mode & REDIRECT_PATH_QUERY:
                    url_parsed = urlsplit(url)
                    url = urlunsplit(url_parsed._replace(scheme='', netloc=urlsplit(self.host).netloc))
                else:
                    return Response(r, self)

        r = self.__session.request(method, url, **kwargs)
        return Response(r, self)


    def get(self, url, **kwargs):
        return self.__request('get', url, **kwargs)

    def post(self, url, **kwargs):
        return self.__request('post', url, **kwargs)

    def patch(self, url, **kwargs):
        return self.__request('patch', url, **kwargs)

    def head(self, url, **kwargs):
        return self.__request('head', url, **kwargs)


class TempEmailSession(Session):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.domains = []

    def set_email_address(self, address: str):
        self.email_address = address

    def get_domains(self) -> list[str]:
        raise NotImplementedError

    def get_messages(self) -> list[str]:
        raise NotImplementedError


class SnapmailSession(TempEmailSession):
    def get_domains(self) -> list[str]:
        if self.domains:
            return self.domains
        r = self.get('https://www.snapmail.cc/js/main.js')
        m = re_snapmail_domains.search(r.text)
        self.domains = json.loads(m[1])
        return self.domains

    def set_email_address(self, address: str):
        super().set_email_address(address)
        self.__email_id, self.__domain = address.split('@')

    def get_messages(self) -> list[str]:
        r = self.get(f'https://www.snapmail.cc/mail/inbox/{self.__domain}/{self.__email_id}')
        bs = BeautifulSoup(r.text, 'html.parser')
        return [msg.get_text() for msg in bs.find_all('div', class_='mail_content')]


class MailcxSession(TempEmailSession):
    def get_domains(self) -> list[str]:
        if self.domains:
            return self.domains
        r = self.get('https://mail.cx/')
        m = re_mailcx_js_path.search(r.text)
        r = self.get(f'https://mail.cx/{m[1]}')
        self.domains = [row[0] for row in json5.loads(re.search(r'domains = (\[.*?\])', r.text, re.S)[1])]
        return self.domains

    def set_email_address(self, address: str):
        super().set_email_address(address)
        self.__session.cookies.set('email', address, domain='.mail.cx')

    def get_messages(self) -> list[str]:
        r = self.get('https://mail.cx/api/messages')
        return [msg['body'] for msg in r.json()['data']]


class TempEmail:
    temp_email_sessions: list[TempEmailSession] = [
        SnapmailSession('https://www.snapmail.cc', 0),
        MailcxSession('https://mail.cx', 0)
    ]

    def __init__(self, banned_domains: list[str]):
        self.__banned = banned_domains
        self.__lock = RLock()
        self.__queues = []

    @cached(lambda: choice(TempEmail.temp_email_sessions).host)
    def __session(self) -> TempEmailSession:
        return choice(TempEmail.temp_email_sessions)

    def get_email_address(self, email_domains: list[str]) -> str:
        while True:
            domains = [domain for domain in self.__session().get_domains() if domain not in self.__banned]
            if email_domains:
                domains = [domain for domain in domains if domain in email_domains]
            if domains:
                break
            else:
                self.__banned.append(self.__session().host)
                del self.__session
        
        while True:
            email_id = rand_id(randint(8, 16))
            domain = choice(domains)
            address = f'{email_id}@{domain}'
            if not self.__session().set_email_address(address):
                continue
            return address

    def set_email_address(self, address: str):
        self.__session().set_email_address(address)
        del self.__banned

    def get_email_code(self, keyword, timeout=60) -> str | None:
        queue = Queue(1)
        with self.__lock:
            self.__queues.append((keyword, queue, time() + timeout))
            if not hasattr(self, f'_{TempEmail.__name__}__th'):
                self.__th = Thread(target=self.__run)
                self.__th.start()
        return queue.get()

    def __run(self):
        while True:
            sleep(1)
            try:
                messages = self.__session().get_messages()
            except Exception as e:
                messages = []
                print(f'TempEmail.__run: {e}')
            with self.__lock:
                new_len = 0
                for item in self.__queues:
                    keyword, queue, end_time = item
                    for message in messages:
                        if keyword in message:
                            m = re_email_code.search(message)
                            queue.put(m[1] if m else m)
                            break
                    else:
                        if time() > end_time:
                            queue.put(None)
                        else:
                            self.__queues[new_len] = item
                            new_len += 1
                del self.__queues[new_len:]
                if new_len == 0:
                    del self.__th
                    break


class PanelSession(Session):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host = ''
        self.opt = {}
        self.cache = {}
        self.generate_random_username = None
        self.get_available_domain = None
        self.get = None

    def should_turn(self) -> bool:
        raise NotImplementedError

    def try_turn(self):
        raise NotImplementedError

    def try_checkin(self):
        raise NotImplementedError

    def try_buy(self):
        raise NotImplementedError

    def get_sub(self) -> str | None:
        raise NotImplementedError

    def save_sub_base64_and_clash(self, url: str):
        raise NotImplementedError

    def _get_email_and_email_code(self, email_domains: list[str], keyword: str, timeout=60) -> tuple[str, str] | tuple[None, None]:
        if not self.cache.get('email'):
            temp_email = TempEmail(self.cache.get('banned_domains', []))
            self.cache['email'] = temp_email.get_email_address(email_domains)
            self.cache['temp_email_host'] = temp_email.__session().host
        
        temp_email = TempEmail(self.cache.get('banned_domains', []))
        temp_email.set_email_address(self.cache['email'])
        email_code = temp_email.get_email_code(keyword, timeout)
        
        if email_code:
            return self.cache['email'], email_code
        
        self.cache.get('banned_domains', []).append(self.cache.pop('temp_email_host'))
        del self.cache['email']
        return None, None


class V2BoardSession(PanelSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, redirect_mode=REDIRECT_TO_GET, **kwargs)

    def should_turn(self) -> bool:
        if self.opt.get('force_turn'):
            return True
        if not self.cache.get('sub_url'):
            return True
        if self.cache.get('expire_time', 0) - time() < timedelta(days=7).total_seconds():
            return True
        if str2size(self.cache.get('rest_size', '0MB')) < str2size('256MB'):
            return True
        return False

    def login(self, username, password) -> bool:
        r = self.post('/auth/login', json={'email': username, 'password': password})
        if r.ok:
            self.cache['email'] = username
            self.cache['password'] = password
            self.cache['expire_time'] = time() + timedelta(days=1).total_seconds() # 临时设置
            self.cache['checkin_time'] = 0
            return True
        return False

    def register(self, email, password, email_code=None, invite_code=None) -> bool:
        data = {'email': email, 'password': password, 'password_confirm': password}
        if email_code:
            data['email_code'] = email_code
        if invite_code:
            data['invite_code'] = invite_code
        r = self.post('/auth/register', json=data)
        return r.ok

    def checkin(self) -> bool:
        r = self.post('/user/checkin')
        return r.ok

    def try_checkin(self):
        if self.cache.get('checkin_time', 0) < time() - timedelta(hours=23).total_seconds():
            if self.checkin():
                self.cache['checkin_time'] = time()
                
    def try_buy(self):
        pass

    def try_turn(self):
        email, password = self.cache.get('email'), self.cache.get('password')
        if not email or not self.login(email, password):
            email = self.generate_random_username() + '@' + self.get_available_domain(self.cache)
            password = rand_id()
            if not self.register(email, password):
                email, email_code = self._get_email_and_email_code(self.opt.get('email_domains', []), 'V2Board')
                if email:
                    self.register(email, password, email_code)
                else:
                    raise Exception('无法获取邮箱验证码')
            self.login(email, password)

    def get_sub(self) -> str | None:
        r = self.get('/user/getSubscribe')
        if r.ok:
            r = r.json()
            self.cache['rest_size'] = str2size(r['data']['transfer_enable'] - r['data']['u'] - r['data']['d'])
            self.cache['expire_time'] = str2timestamp(r['data']['expire_date'])
            return r['data']['subscribe_url']
        return None

    def get_user_info(self):
        r = self.get('/user/info')
        if r.ok:
            return r.json()['data']
        return {}


class SSPanSession(V2BoardSession):
    def try_turn(self):
        email, password = self.cache.get('email'), self.cache.get('password')
        if not email or not self.login(email, password):
            email = self.generate_random_username() + '@' + self.get_available_domain(self.cache)
            password = rand_id()
            r = self.post('/auth/register', json={'email': email, 'password': password, 'password_confirm': password})
            if not r.ok:
                raise Exception(f'注册失败: {r.text}')
            self.login(email, password)

    def get_sub(self) -> str | None:
        r = self.get('/user/subscribe')
        if r.ok:
            r = r.json()
            self.cache['rest_size'] = str2size(r['data']['transfer_enable'] - r['data']['u'] - r['data']['d'])
            self.cache['expire_time'] = str2timestamp(r['data']['expire_date'])
            return r['data']['subscribe_url']
        return None


panel_class_map = {
    'V2Board': V2BoardSession,
    'SSPan': SSPanSession,
}


def guess_panel(host: str) -> type[PanelSession]:
    # 简单的面板猜测逻辑：这里仅返回 V2Board 作为默认，
    # 实际应用中需要更复杂的识别逻辑。
    return V2BoardSession
