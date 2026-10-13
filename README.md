# 通用爬虫与数据智能提取系统 (Demo)

> 面向 RAG & Agent 知识摄取的前端可视化 + 智能爬虫 + Markdown转换 + AI语义字段提取 + MongoDB 存储全流程闭环系统。

## 🌟 核心功能闭环
1. **工作台与通用爬虫**：
   - 自动生成唯一任务 ID，支持单行/多行批量网址输入；
   - 随机 User-Agent 请求头与请求间隔控制，集成字符集智能检测（防乱码）；
   - 实时终端风格日志流输出。
2. **Markdown 高保真转换与预览**：
   - 剔除广告、导航、脚本等干扰元素，保留标题、列表、表格（Table）结构；
   - 遵循 `{任务ID}_{网址域名}_{爬取时间}.md` 规范命名，支持文件下载与双栏渲染预览。
3. **自定义主/子字段智能提取**：
   - 用户可自由定义主字段、子字段及详细**字段解释**（语义描述）；
   - 支持调用 NewAPI 大模型（`gpt-oss-120b`）进行语义推理与结构化提取，输出整洁 JSON；
   - 提供原文定位引用（`md_position`）与动态数据类型推断（文本/数字/时间/数组/对象）；
   - 内置百科、电商、新闻等常见场景预设模板，一键加载。
4. **MongoDB 数据存储与查看**：
   - 三张核心表：基础任务表 (`crawl_tasks`)、主字段表 (`main_fields`)、子字段表 (`sub_fields`)；
   - 严格保障主/子字段关联唯一性；
   - 具备本地持久化与 MongoDB 集群透明切换能力。

---

## 🚀 快速启动

### 🪟 Windows 环境（推荐 uv）

**前提**：已安装 [uv](https://docs.astral.sh/uv/)，若未安装在 PowerShell 执行：
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

然后双击运行 `start.bat`，或在 CMD/PowerShell 中执行：
```bat
start.bat
```

如需手动操作：
```powershell
# 创建虚拟环境
uv venv --python 3.11
# 安装依赖（自动跳过 uvloop 等仅 Unix 库）
uv pip install -e ".[dev]"
# 启动服务（Windows 使用 asyncio 事件循环）
.venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000 --loop asyncio
```

### 🍎 macOS / 🐧 Linux 环境

**方式一：uv（推荐）**
```bash
uv venv && uv pip install -e ".[dev]"
python3 main.py
```

**方式二：一键脚本**
```bash
./start.sh
```

**方式三：手动 pip**
```bash
pip install -r requirements.txt
python3 main.py
```

服务启动后，在浏览器访问：
👉 **http://localhost:8000** 即可使用完整的可视化控制台！

---

## 📁 目录结构
```text
├── CLAUDE.md                   # Claude Code 规范指南
├── README.md                   # 本文件
├── 设计说明文档.md              # 题目要求的四点设计思路说明
├── requirements.txt            # 依赖清单
├── config.yaml                 # 配置文件（无硬编码）
├── config.py                   # 配置管理热更新类
├── main.py                     # FastAPI 服务入口
├── start.sh                    # 一键启动脚本
├── crawler/
│   ├── spider.py               # 通用反爬虫引擎
│   └── md_converter.py         # 高保真 HTML->Markdown 转换器
├── extractor/
│   ├── ai_extractor.py         # 基于大模型的语义字段抽取器
│   └── schemas.py              # Pydantic 字段数据模型
├── storage/
│   └── mongo_client.py         # MongoDB 客户端与关联唯一性校验
├── static/
│   ├── index.html              # 前端单页应用
│   ├── app.js                  # 前端 Vue 3 交互逻辑
│   └── app.css                 # 现代化 UI 样式
└── data/
    └── md_storage/             # 生成的 Markdown 文件存储目录
```
