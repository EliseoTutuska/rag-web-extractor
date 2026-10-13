# CLAUDE.md - 项目指南与开发规范

## 项目目标
开发一个面向 RAG & Agent 知识库摄取的通用爬虫 + Markdown 转换 + 基于大模型（OpenAI/NewAPI/OneAPI/DeepSeek等兼容接口）自定义语义字段提取 + MongoDB 存储系统。包含轻量级可视化单页控制台（SPA）。

## 技术栈与设计原则
- **后端**：Python 3.10+、FastAPI、Uvicorn、Pydantic、HTTPX、Playwright
- **网页与 Markdown 清洗**：BeautifulSoup4、HTMLToMarkdownConverter（递归降噪、标题/列表/表格结构保留，支持 JS 挑战页浏览器无头渲染）
- **大模型抽取**：兼容 OpenAI API 规范的 LLM 接口，支持主/子字段语义理解与 JSON 抽取
- **数据持久化**：PyMongo（三张核心表：crawl_tasks、main_fields、sub_fields，支持自动类型适配与关联唯一性校验）
- **前端**：轻量级单页应用（Vue 3 + Tailwind CSS，位于 `static/` 目录，无复杂 npm 构建，开箱即用）
- **禁止硬编码**：所有配置均在 `config.yaml` 中声明，并支持前端全局配置界面动态修改。

## 启动与运行命令
```bash
# 1. 激活虚拟环境或安装依赖
source .venv/bin/activate  # 或 pip install -r requirements.txt

# 2. 启动服务 (默认端口 8000)
python3 main.py
# 或使用启动脚本
./start.sh
```

## 核心接口
- `GET /`：前端单页应用可视化界面
- `POST /api/crawl`：发起爬取任务并生成 Markdown
- `POST /api/extract`：基于主/子字段配置执行 AI 语义抽取并入库
- `GET /api/tasks`：查询最近任务列表
- `GET /api/tasks/{task_id}`：获取单任务详情与 Markdown 文本
- `GET /api/tasks/{task_id}/download-md`：下载 Markdown 文件
- `GET /api/storage/data?table={tasks|main_fields|sub_fields}`：查看 MongoDB 三张表数据
- `POST /api/system/config`：动态更新系统配置
