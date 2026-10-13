import re
from typing import Optional
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

class HTMLToMarkdownConverter:
    """
    负责将杂乱的 HTML 网页源码清洗并高保真转换为结构化 Markdown 文本。
    - 自动剔除导航栏、页脚、广告条、脚本与内联样式等杂质；
    - 精准保留标题层级（# / ## / ###）、无序/有序列表、代码块、引用以及表格（Table）；
    - 保留核心段落与语义，消除乱码与冗余空白。
    """

    NOISE_TAGS = [
        "script", "style", "noscript", "meta", "link", "iframe",
        "header", "footer", "nav", "aside", "form", "button", "svg", "canvas"
    ]

    NOISE_PATTERNS = re.compile(
        r"(ad|banner|cookie|copyright|footer|share|comment|recommend|sidebar|widget|popup|modal)",
        re.I
    )

    def convert(self, html_content: str, title_hint: str = "") -> str:
        if not html_content or not html_content.strip():
            return ""

        soup = BeautifulSoup(html_content, "html.parser")

        # 1. 移除无用标签与注释
        for tag_name in self.NOISE_TAGS:
            for element in soup.find_all(tag_name):
                element.decompose()

        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # 2. 移除常见的广告或辅助侧边栏元素
        for tag in soup.find_all(True):
            if not getattr(tag, "attrs", None):
                continue
            classes = tag.get("class", [])
            class_str = " ".join(classes) if isinstance(classes, list) else str(classes or "")
            id_str = str(tag.get("id", "") or "")
            if (class_str and self.NOISE_PATTERNS.search(class_str)) or (id_str and self.NOISE_PATTERNS.search(id_str)):
                # 如果是核心正文容器则不误删
                if not any(k in (class_str + id_str).lower() for k in ["content", "article", "main", "body", "post"]):
                    tag.decompose()

        # 3. 优先寻找主内容区域
        content_root = (
            soup.find("article") or
            soup.find("main") or
            soup.find("div", class_=re.compile(r"(content|article-body|post-content|main-content)", re.I)) or
            soup.find("body") or
            soup
        )

        # 4. 递归转换节点为 Markdown 文本
        md_lines = []
        if title_hint:
            md_lines.append(f"# {title_hint.strip()}\n")

        self._process_node(content_root, md_lines)

        # 5. 后处理清洗多余空行
        raw_md = "".join(md_lines)
        cleaned_md = re.sub(r"\n{3,}", "\n\n", raw_md).strip()
        return cleaned_md

    def _process_node(self, node, out: list, list_depth=0):
        if isinstance(node, NavigableString):
            text = str(node)
            if text.strip():
                # 规范化行内空白
                out.append(re.sub(r"[ \t]+", " ", text))
            return

        if not isinstance(node, Tag):
            return

        tag_name = node.name.lower()

        # 标题处理
        if tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(tag_name[1])
            text = node.get_text(separator=" ", strip=True)
            if text:
                out.append(f"\n\n{'#' * level} {text}\n\n")
            return

        # 段落与换行
        elif tag_name == "p":
            out.append("\n\n")
            for child in node.children:
                self._process_node(child, out, list_depth)
            out.append("\n\n")
            return

        elif tag_name == "br":
            out.append("\n")
            return

        elif tag_name == "hr":
            out.append("\n\n---\n\n")
            return

        # 列表处理
        elif tag_name == "ul":
            out.append("\n")
            for li in node.find_all("li", recursive=False):
                indent = "  " * list_depth
                out.append(f"\n{indent}* ")
                for child in li.children:
                    self._process_node(child, out, list_depth + 1)
            out.append("\n")
            return

        elif tag_name == "ol":
            out.append("\n")
            for idx, li in enumerate(node.find_all("li", recursive=False), 1):
                indent = "  " * list_depth
                out.append(f"\n{indent}{idx}. ")
                for child in li.children:
                    self._process_node(child, out, list_depth + 1)
            out.append("\n")
            return

        # 表格处理 (转换为标准 Markdown 表格)
        elif tag_name == "table":
            out.append("\n\n")
            self._process_table(node, out)
            out.append("\n\n")
            return

        # 代码块
        elif tag_name == "pre":
            code_text = node.get_text()
            out.append(f"\n\n```\n{code_text.strip()}\n```\n\n")
            return

        elif tag_name == "code":
            if node.parent and node.parent.name.lower() == "pre":
                out.append(node.get_text())
            else:
                out.append(f" `{node.get_text(strip=True)}` ")
            return

        # 引用
        elif tag_name == "blockquote":
            text = node.get_text(separator="\n", strip=True)
            if text:
                quoted = "\n".join([f"> {line}" for line in text.splitlines() if line.strip()])
                out.append(f"\n\n{quoted}\n\n")
            return

        # 粗体与斜体
        elif tag_name in ["strong", "b"]:
            out.append(f" **{node.get_text(strip=True)}** ")
            return

        elif tag_name in ["em", "i"]:
            out.append(f" *{node.get_text(strip=True)}* ")
            return

        # 默认递归子节点
        for child in node.children:
            self._process_node(child, out, list_depth)

    def _process_table(self, table_tag: Tag, out: list):
        rows = table_tag.find_all("tr")
        if not rows:
            return

        table_data = []
        for tr in rows:
            cells = tr.find_all(["th", "td"])
            row_vals = [c.get_text(separator=" ", strip=True).replace("|", "\\|") for c in cells]
            if any(row_vals):
                table_data.append(row_vals)

        if not table_data:
            return

        col_count = max(len(r) for r in table_data)
        # 对齐列数
        normalized_data = [r + [""] * (col_count - len(r)) for r in table_data]

        header = normalized_data[0]
        out.append("| " + " | ".join(header) + " |\n")
        out.append("| " + " | ".join(["---"] * col_count) + " |\n")

        for row in normalized_data[1:]:
            out.append("| " + " | ".join(row) + " |\n")
