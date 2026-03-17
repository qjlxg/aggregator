import asyncio
import random
import os
from playwright.async_api import async_playwright

# --- 配置区 ---
# 建议通过环境变量传递搜索 URL，或者直接在这里修改
SEARCH_URL = "https://www.onyphe.io/search/?q=category:datascan+app:v2board"
MAX_PAGES = 10  # 自动运行建议先设置较小的页数，稳定后再调大
OUTPUT_FILE = "onyphe_results.txt"

async def scrape():
    async with async_playwright() as p:
        # GitHub Actions 环境必须使用 headless=True
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        all_targets = set()
        print(f"[*] 启动抓取: {SEARCH_URL}")

        try:
            await page.goto(SEARCH_URL, wait_until="networkidle", timeout=60000)
            
            for page_num in range(1, MAX_PAGES + 1):
                print(f"[*] 正在处理第 {page_num} 页...")
                
                # 等待资产列表加载
                await page.wait_for_selector(".asset", timeout=15000)

                # 提取数据
                found = await page.evaluate('''() => {
                    const res = [];
                    document.querySelectorAll('.asset').forEach(asset => {
                        // 提取域名
                        const dLabel = Array.from(asset.querySelectorAll('div,td')).find(el => el.innerText.trim() === 'Domain(s)');
                        if (dLabel && dLabel.nextElementSibling) {
                            dLabel.nextElementSibling.innerText.split('\\n').forEach(d => { if(d.trim()) res.push(d.trim()); });
                        }
                        // 提取 IP
                        const iLabel = Array.from(asset.querySelectorAll('div,td')).find(el => el.innerText.trim() === 'IP');
                        if (iLabel && iLabel.nextElementSibling) {
                            const ip = iLabel.nextElementSibling.innerText.trim();
                            if(ip) res.push(ip);
                        }
                    });
                    return res;
                }''')

                all_targets.update(found)
                print(f"    - 当前累计抓取到 {len(all_targets)} 条唯一记录")

                # 翻页
                next_btn = page.locator('a:has-text("next"), a[aria-label="Next"]').first
                if await next_btn.is_visible():
                    await next_btn.click()
                    await asyncio.sleep(random.uniform(5, 8)) # 稍微久一点，模拟真人
                else:
                    print("[!] 无法翻页，抓取结束。")
                    break
        except Exception as e:
            print(f"[!] 抓取过程出错: {e}")
        finally:
            await browser.close()

        # 结果持久化
        if all_targets:
            # 简单清洗：去重、转小写、排除常见干扰域名
            blacklist = ['onyphe.io', 'google.com', 'cloudflare.com', 'pages.dev']
            clean_list = [t.lower() for t in all_targets if not any(b in t.lower() for b in blacklist)]
            
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(list(set(clean_list)))))
            print(f"[+] 结果已写入 {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(scrape())
