import asyncio
import random
import sys  # sys 应该单独导入
from playwright.asyncio import async_playwright # 正确的导入方式

# 搜索关键词列表
KEYWORDS = [
    'intext:"v2board" OR intext:"xboard"',
    'intext:"SSPanel-Uim" OR intext:"/theme/Rocket/assets/"',
    'intext:"layouts__index.async.js"'
]

async def run_search():
    # 使用 async_playwright()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 模拟真实的浏览器环境
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()
        
        all_links = set()

        for query in KEYWORDS:
            # 编码 Query 防止 URL 出错
            import urllib.parse
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://www.google.com/search?q={encoded_query}&tbs=cdr:1,cd_min:3/13/2026,cd_max:3/17/2026"
            
            print(f"正在搜索: {query}")
            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(random.uniform(3, 7))

                for page_num in range(5): 
                    # 提取当前页链接
                    links = await page.evaluate('''() => {
                        return Array.from(document.querySelectorAll('div.g a'))
                            .map(a => a.href)
                            .filter(href => href && href.startsWith('http') && !href.includes('google.com'));
                    }''')
                    all_links.update(links)
                    print(f"第 {page_num + 1} 页抓取完成，当前累计 {len(all_links)} 条链接")

                    # 查找“下一页”按钮
                    # Google 的下一页按钮通常有特定的 ID 或文本
                    next_button = page.get_by_role("link", name="下一页")
                    if await next_button.count() > 0:
                        await next_button.click()
                        await asyncio.sleep(random.uniform(4, 8))
                    else:
                        break
            except Exception as e:
                print(f"搜索 {query} 时发生错误: {e}")

        await browser.close()

        # 写入文件
        if all_links:
            with open("search_results.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(list(all_links))))
            print(f"任务成功：保存了 {len(all_links)} 条链接到 search_results.txt")
        else:
            print("未抓取到任何链接，请检查 Google 是否触发了验证码。")

if __name__ == "__main__":
    asyncio.run(run_search())
