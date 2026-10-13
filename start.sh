#!/usr/bin/env bash
# 一键启动脚本

cd "$(dirname "$0")"

# 检查虚拟环境
if [ -d ".venv" ]; then
    echo "⚡ 激活虚拟环境 .venv..."
    source .venv/bin/activate
fi

# 检查依赖安装
if ! python3 -c "import fastapi, uvicorn, pymongo, bs4" 2>/dev/null; then
    echo "📦 正在安装依赖..."
    pip install -r requirements.txt
fi

# 确保 Playwright Chromium 已安装（用于抓取百度等有 JS 验证的网站）
if python3 -c "import playwright" 2>/dev/null; then
    if [ ! -d "$HOME/.cache/ms-playwright" ] && [ ! -d "$HOME/Library/Caches/ms-playwright" ]; then
        echo "🌐 首次运行：安装 Playwright Chromium 浏览器（约 150MB，仅需一次）..."
        playwright install chromium
    fi
else
    echo "⚠️  未安装 playwright，跳过浏览器安装（百度百科等有 JS 验证的网站可能无法抓取）"
fi

echo "🚀 启动通用爬虫与数据智能提取服务..."
python3 main.py
