import pytest
import re
from pathlib import Path
from crawler.spider import WebCrawler

@pytest.fixture
def spider():
    return WebCrawler()

def test_user_agents_generation(spider):
    headers = spider._get_random_headers()
    assert "User-Agent" in headers
    assert "Mozilla" in headers["User-Agent"]
    assert "Accept" in headers
    assert headers["DNT"] == "1"

def test_stop_task_mechanism(spider):
    test_id = "test_cancel_task_999"
    assert not spider.is_stopped(test_id)
    spider.stop_task(test_id)
    assert spider.is_stopped(test_id)

def test_sanitize_filename(spider):
    raw_domain = "https://sub.domain-test.com/path?arg=1"
    clean = spider._sanitize_filename("sub.domain-test.com")
    assert "/" not in clean
    assert "?" not in clean
    assert clean == "sub_domain-test_com"

def test_crawl_file_naming_convention(spider, tmp_path):
    spider.storage_dir = tmp_path
    task_id = "task_verify_001"
    # 模拟抓取或测试本地请求
    res = spider.run_crawl_task(
        task_id=task_id,
        urls=["https://httpbin.org/get"],
        delay=0
    )
    assert len(res) == 1
    item = res[0]
    if item["status"] == "success":
        # 验证文件命名规则: {任务ID}_{域名}_{爬取时间}.md
        pattern = rf"^{task_id}_[a-zA-Z0-9_\-]+_\d{{8}}_\d{{6}}\.md$"
        assert re.match(pattern, item["md_file_name"]) is not None
        assert Path(item["md_file_path"]).exists()
