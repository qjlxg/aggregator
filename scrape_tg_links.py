def process(i_url):
    sem_pars.acquire()
    html_pages = []
    cur_url = i_url
    for itter in range(1, pars_dp + 1):
        while True:
            try:
                print(f"正在获取频道 {i_url} 的第 {itter} 页")
                response = requests.get(f'https://t.me/s/{cur_url}')
                base_url = response.url
            except Exception as e:
                print(f"获取页面失败: {e}")
                time.sleep(random.randint(5, 25))
                continue
            else:
                if itter == pars_dp:
                    print(f'{tg_name_json.index(i_url) + 1} of {len(tg_name_json)} - {i_url}')
                html_pages.append(response.text)
                last_datbef = re.findall(r'(?:data-before=")(\d*)', response.text)
                break
        if not last_datbef:
            break
        cur_url = f'{i_url}?before={last_datbef[0]}'
    for page in html_pages:
        soup = BeautifulSoup(page, 'html.parser')
        message_texts = soup.find_all(class_='tgme_widget_message_text')
        print(f"页面中找到 {len(message_texts)} 条消息")
        for message_text in message_texts:
            a_tags = message_text.find_all('a')
            print(f"消息中找到 {len(a_tags)} 个链接")
            for tag in a_tags:
                href = tag.get('href')
                if href:
                    absolute_url = urljoin(base_url, href)
                    if absolute_url.startswith(('http://', 'https://')):
                        with links_lock:
                            links.append(absolute_url)
                            print(f"提取到链接: {absolute_url}")
    sem_pars.release()
