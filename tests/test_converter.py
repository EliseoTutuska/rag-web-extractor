import pytest
from crawler.md_converter import HTMLToMarkdownConverter

@pytest.fixture
def converter():
    return HTMLToMarkdownConverter()

def test_strip_scripts_styles_and_ads(converter):
    raw_html = """
    <html>
        <head>
            <title>测试网页</title>
            <style>body { color: red; }</style>
            <script>console.log("bad script");</script>
        </head>
        <body>
            <div class="sidebar ad-banner">广告内容：买一送一</div>
            <article>
                <h1>核心文章标题</h1>
                <p>这是正文第一段，包含真实价值信息。</p>
            </article>
            <footer>版权所有 (c) 2026</footer>
        </body>
    </html>
    """
    md = converter.convert(raw_html)
    assert "bad script" not in md
    assert "body { color: red; }" not in md
    assert "买一送一" not in md
    assert "核心文章标题" in md
    assert "这是正文第一段" in md

def test_headers_and_hierarchy(converter):
    raw_html = """
    <div>
        <h1>一级标题</h1>
        <p>正文内容</p>
        <h2>二级小节</h2>
        <p>小节描述</p>
        <h3>三级更详细</h3>
    </div>
    """
    md = converter.convert(raw_html)
    assert "# 一级标题" in md
    assert "## 二级小节" in md
    assert "### 三级更详细" in md

def test_lists_and_tables(converter):
    raw_html = """
    <div>
        <ul>
            <li>列表项 A</li>
            <li>列表项 B</li>
        </ul>
        <table>
            <thead>
                <tr><th>参数名</th><th>类型</th><th>说明</th></tr>
            </thead>
            <tbody>
                <tr><td>username</td><td>str</td><td>用户登录账号</td></tr>
                <tr><td>age</td><td>int</td><td>用户年龄</td></tr>
            </tbody>
        </table>
    </div>
    """
    md = converter.convert(raw_html)
    assert "* 列表项 A" in md
    assert "* 列表项 B" in md
    assert "| 参数名 | 类型 | 说明 |" in md
    assert "| username | str | 用户登录账号 |" in md
    assert "| age | int | 用户年龄 |" in md

def test_clean_extra_newlines(converter):
    raw_html = """
    <p>段落 1</p>
    <br><br><br>
    <p>段落 2</p>
    """
    md = converter.convert(raw_html)
    assert "\n\n\n\n" not in md
    assert "段落 1" in md
    assert "段落 2" in md
