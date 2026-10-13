import os
import re
import time
import random
import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import List, Dict, Any, Callable, Optional
import httpx
from bs4 import BeautifulSoup
import charset_normalizer

from crawler.md_converter import HTMLToMarkdownConverter
from config import config

# JS 挑战页特征关键词（百度反爬、Cloudflare 等）
_JS_CHALLENGE_PATTERNS = [
    "__PARIS_CHALLENGE__",
    "__CHALLENGE_CONFIG__",
    "window._cf_chl_opt",
    "cf-browser-verification",
    "var bstToken",
    "acs-token",
    "请稍后再试",
    "访问过于频繁",
]

def _is_js_challenge_page(html: str, content_length: int) -> bool:
    """
    检测响应是否为 JS 人机验证挑战页。
    特征：页面极小（<50KB）且包含已知反爬关键词。
    """
    if content_length > 50000:
        return False
    for pattern in _JS_CHALLENGE_PATTERNS:
        if pattern in html:
            return True
    return False


def _fetch_with_playwright(url: str, wait_seconds: int = 5) -> tuple[str, str]:
    """
    使用 Playwright 无头 Chromium 浏览器抓取需要 JS 渲染的页面（如百度百科）。
    等待 JS 挑战完成后返回完整渲染后的 HTML 与网页标题。
    返回 (html, title)。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "检测到需要 Playwright 才能抓取该网站（存在 JS 人机验证）。\n"
            "请先安装：uv pip install playwright && playwright install chromium"
        )

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",  # 隐藏 webdriver 特征
                "--disable-dev-shm-usage",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/128.0.0.0 Safari/537.36",
            locale="zh-CN",
            viewport={"width": 1280, "height": 800},
            java_script_enabled=True,
        )

        # 注入脚本：覆盖 navigator.webdriver 为 undefined，防止被检测
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = context.new_page()
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            # 等待 JS 挑战脚本运行完毕（最多等 wait_seconds 秒后页面应跳转或刷新）
            page.wait_for_timeout(wait_seconds * 1000)
            # 再等网络请求稳定
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            html = page.content()
            title = page.title() or ""
        finally:
            page.close()
            context.close()
            browser.close()

    return html, title



class WebCrawler:
    """
    通用反爬策略爬虫引擎
    - 随机 User-Agent 请求头
    - 自动编码智能识别（防乱码）
    - 请求间隔与速率控制
    - 自动清洗转换 Markdown 并生成标准命名文件
    """

    def __init__(self):
        self.converter = HTMLToMarkdownConverter()
        self.storage_dir = Path(config.get("crawler.storage_dir", "data/md_storage"))
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.user_agents = config.get("crawler.user_agents", [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ])
        self._stopped_tasks = set()

    def stop_task(self, task_id: str):
        self._stopped_tasks.add(task_id)

    def is_stopped(self, task_id: str) -> bool:
        return task_id in self._stopped_tasks

    def _get_random_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1"
        }

    def _sanitize_filename(self, text: str) -> str:
        return re.sub(r"[\\/*?:\'\"<>|.]", "_", text).strip("_")

    def fetch_url(self, url: str, timeout: int = 15) -> tuple[str, str]:
        """
        抓取单个 URL，自动识别编码并返回 (html_content, page_title)。
        如果检测到 JS 人机验证挑战页（如百度百科的 PARIS_CHALLENGE），
        自动降级使用 Playwright 无头浏览器渲染后获取真实内容。
        """
        headers = self._get_random_headers()
        with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True, verify=False) as client:
            resp = client.get(url)
            resp.raise_for_status()

            raw_bytes = resp.content
            # 智能检测编码
            encoding = resp.encoding
            if not encoding or encoding.lower() in ["iso-8859-1", "ascii"]:
                detected = charset_normalizer.from_bytes(raw_bytes).best()
                encoding = detected.encoding if detected else "utf-8"

            try:
                html = raw_bytes.decode(encoding or "utf-8", errors="replace")
            except Exception:
                html = raw_bytes.decode("utf-8", errors="ignore")

            # ✅ 检测是否为 JS 挑战拦截页
            if _is_js_challenge_page(html, len(raw_bytes)):
                print(f"[Spider] 检测到 JS 人机验证挑战页（如百度百科反爬），自动切换 Playwright 无头浏览器抓取: {url}")
                html, title = _fetch_with_playwright(url, wait_seconds=6)
                return html, title

            # 提取网页标题
            title = ""
            try:
                soup = BeautifulSoup(html[:50000], "html.parser")
                if soup.title and soup.title.string:
                    title = soup.title.string.strip()
            except Exception:
                pass

            return html, title


    def run_crawl_task(
        self,
        task_id: str,
        urls: List[str],
        delay: float = 1.0,
        log_callback: Optional[Callable[[str, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        执行批量爬取任务
        """
        results = []
        total = len(urls)

        def log(msg: str, level: str = "INFO"):
            if log_callback:
                log_callback(msg, level)
            print(f"[{level}] [Task {task_id}] {msg}")

        log(f"任务启动：待抓取网址共 {total} 个，请求间隔 {delay} 秒")

        for idx, url in enumerate(urls, 1):
            if self.is_stopped(task_id):
                log("检测到终止指令，抓取任务已由用户手动停止", "WARN")
                break

            parsed = urlparse(url)
            domain = parsed.netloc or "unknown_domain"
            safe_domain = self._sanitize_filename(domain)
            now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            md_filename = f"{task_id}_{safe_domain}_{now_str}.md"
            md_filepath = str((self.storage_dir / md_filename).resolve())

            log(f"[{idx}/{total}] 正在抓取: {url} ...")
            start_time = time.time()

            try:
                html, title = self.fetch_url(url)
                log(f"抓取成功 (耗时 {time.time()-start_time:.2f}s)，网页标题: {title or '无标题'}")

                log("正在进行 HTML 降噪清洗并转为结构化 Markdown...")
                md_content = self.converter.convert(html, title_hint=title)

                # 本地写入 MD 文件
                with open(md_filepath, "w", encoding="utf-8") as f:
                    f.write(md_content)

                file_size_kb = len(md_content.encode("utf-8")) / 1024
                log(f"Markdown 转换完成并已落盘: {md_filename} ({file_size_kb:.2f} KB)")

                results.append({
                    "task_id": task_id,
                    "url": url,
                    "domain": domain,
                    "status": "success",
                    "crawl_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "md_file_path": md_filepath,
                    "md_file_name": md_filename,
                    "md_content": md_content,
                    "error": None
                })

            except Exception as e:
                err_msg = f"抓取失败 [{url}]: {str(e)}"
                log(err_msg, "ERROR")
                results.append({
                    "task_id": task_id,
                    "url": url,
                    "domain": domain,
                    "status": "failed",
                    "crawl_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "md_file_path": None,
                    "md_file_name": None,
                    "md_content": None,
                    "error": str(e)
                })

            # 控制请求间隔防反爬
            if idx < total and delay > 0:
                time.sleep(delay)

        log(f"任务结束：共完成 {len(results)} 个网址抓取")
        return results

crawler = WebCrawler()
