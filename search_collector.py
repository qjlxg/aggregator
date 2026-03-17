import asyncio
import random
import os
from playwright.async_api import async_playwright

# --- 配置区 ---
SEARCH_URL = "https://www.onyphe.io/search/?q=category:datascan+app:v2board"
MAX_PAGES = 10
OUTPUT_FILE = "onyphe_results.txt"

async def scrape():
    # 使用 stealth 策略需要安装额外的库 (见下方的 YML 修改)
    async with async_playwright() as p:
        # 尝试模拟真实的启动参数
        browser = await p.chromium.launch(headless=True, args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-setuid-sandbox'
        ])
        
        # 模拟高分辨率显示器，避免移动端布局干扰
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = await context.new_page()
        
        # 隐藏 webdriver 痕迹
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        all_targets = set()
        print(f"[*] 启动抓取: {SEARCH_URL}")

        try:
            # 增加等待时间，并模拟人类滚动行为
            response = await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=90000)
            print(f"[*] 页面响应状态: {response.status if response else '无响应'}")
            
            # 模拟随机滚动
            await page.mouse.wheel(0, 500)
            await asyncio.sleep(5)

            for page_num in range(1, MAX_PAGES + 1):
                # 尝试等待资产加载，如果失败则截屏
                try:
                    await page.wait_for_selector(".asset", timeout=30000)
                except Exception as e:
                    print(f"[!] 无法找到数据节点，正在截屏排查...")
                    await page.screenshot(path="error.png")
                    print("[*] 错误截图已保存为 error.png，请稍后在仓库查看。")
                    break

                # 提取逻辑保持不变
                found = await page.evaluate('''() => {
                    const res = [];
                    document.querySelectorAll('.asset').forEach(asset => {
                        const dLabel = Array.from(asset.querySelectorAll('div,td,span')).find(el => el.innerText.trim() === 'Domain(s)');
                        if (dLabel && dLabel.nextElementSibling) {
                            dLabel.nextElementSibling.innerText.split('\\n').forEach(d => { if(d.trim()) res.push(d.trim()); });
                        }
                        const iLabel = Array.from(asset.querySelectorAll('div,td,span')).find(el => el.innerText.trim() === 'IP');
                        if (iLabel && iLabel.nextElementSibling) {
                            const ip = iLabel.nextElementSibling.innerText.trim();
                            if(ip) res.push(ip);
                        }
                    });
                    return res;
                }''')

                all_targets.update(found)
                print(f"[*] 第 {page_num} 页完成，捕获 {len(found)} 条。总计: {len(all_targets)}")

                # 翻页
                next_btn = page.locator('a:has-text("next"), a[aria-label="Next"]').first
                if await next_btn.is_visible() and await next_btn.is_enabled():
                    await next_btn.click()
                    await asyncio.sleep(random.uniform(7, 12)) # 延长等待，防止频率过快
                else:
                    break
                    
        except Exception as e:
            print(f"[!] 脚本异常: {e}")
        finally:
            await browser.close()

        if all_targets:
            blacklist = ['onyphe.io', 'google.com', 'cloudflare.com', 'pages.dev']
            clean_list = [t.lower() for t in all_targets if not any(b in t.lower() for b in blacklist)]
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(list(set(clean_list)))))
            print(f"[+] 任务成功，保存 {len(clean_list)} 个目标。")

if __name__ == "__main__":
    asyncio.run(scrape())
