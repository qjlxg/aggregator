import asyncio
import random
import sys
import urllib.parse
from playwright.asyncio import async_playwright

# 搜索关键词列表
KEYWORDS = [
    'intext:"v2board" OR intext:"xboard"',
    'intext:"SSPanel-Uim" OR intext:"/theme/Rocket/assets/"',
    'intext:"layouts__index.async.js"'
]

# 随机等待，模拟真实用户
async def human_delay(a=2, b=5):
    await asyncio.sleep(random.uniform(a, b))

async def run_search():
    async with async_playwright() as p:
        # 建议关闭 headless，降低验证码概率
        browser = await p.chromium.launch(headless=False)

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={'width': 1920, 'height': 1080},
            locale="zh-CN",
            geolocation={"longitude": 116.4074, "latitude": 39.9042},
            permissions=["geolocation"]
        )

        all_links = set()

        for query in KEYWORDS:
            page = await context.new_page()

            encoded_query = urllib.parse.quote(query)
            search_url = (
                f"https://www.google.com/search?q={encoded_query}"
                f"&tbs=cdr:1,cd_min:3/13/26,cd_max:3/17/26"
            )

            print(f"\n🔍 正在搜索: {query}")

            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                await human_delay(3, 7)

                for page_num in range(5):
                    # 提取链接（更稳健）
                    links = await page.evaluate('''() => {
                        return Array.from(document.querySelectorAll('a[href]'))
                            .map(a => a.href)
                            .filter(href => href.startsWith('http')
                                && !href.includes('google.')
                                && !href.includes('webcache'));
                    }''')

                    all_links.update(links)
                    print(f"📄 第 {page_num + 1} 页抓取完成，累计 {len(all_links)} 条链接")

                    # 查找下一页按钮（使用更稳定的 pnnext）
                    next_button = page.locator("a#pnnext")

                    if await next_button.count() > 0:
                        await next_button.click()
                        await human_delay(4, 8)
                    else:
                        print("➡️ 没有下一页，停止翻页")
                        break

            except Exception as e:
                print(f"❌ 搜索 {query} 时发生错误: {e}")

            await page.close()

        await browser.close()

        # 写入文件
        if all_links:
            with open("search_results.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(all_links)))
            print(f"\n🎉 任务成功：保存了 {len(all_links)} 条链接到 search_results.txt")
        else:
            print("\n⚠️ 未抓取到任何链接，请检查 Google 是否触发验证码。")

if __name__ == "__main__":
    asyncio.run(run_search())
