@echo off
:: 通用爬虫与数据智能提取系统 - Windows 一键启动脚本
:: 适用于 Windows 10/11 + uv 环境
:: 使用前请先安装 uv: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

setlocal enabledelayedexpansion

cd /d "%~dp0"
echo.
echo =================================================
echo  通用爬虫与数据智能提取系统 (Windows)
echo  RAG ^& Agent 数据管线工具
echo =================================================
echo.

:: 检查 uv 是否安装
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] 未检测到 uv，正在尝试自动安装...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    if !errorlevel! neq 0 (
        echo [ERROR] uv 安装失败，请手动访问 https://docs.astral.sh/uv/getting-started/installation/ 安装后重试
        pause
        exit /b 1
    )
    :: 重新刷新 PATH（在当前进程中识别新安装的 uv）
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
)

echo [1/3] 检查/创建 Python 虚拟环境...
if not exist ".venv" (
    uv venv --python 3.11
)

echo [2/3] 同步安装项目依赖 (自动跳过 Windows 不兼容库如 uvloop)...
uv pip install -e ".[dev]"
if %errorlevel% neq 0 (
    echo [WARN] 带 [dev] 安装失败，尝试仅安装核心依赖...
    uv pip install fastapi "uvicorn[standard]" pydantic httpx requests beautifulsoup4 html2text charset-normalizer pymongo pyyaml python-multipart python-dotenv playwright
)

echo [2.5/3] 安装 Playwright Chromium 浏览器（用于抓取百度等有 JS 验证的网站）...
.venv\Scripts\playwright.exe install chromium
if %errorlevel% neq 0 (
    echo [WARN] Playwright Chromium 安装失败，JS 验证页面可能无法正常抓取，其他功能不受影响
)

echo [3/3] 启动服务...
echo.
echo 服务启动后，请在浏览器访问: http://localhost:8000
echo 按 Ctrl+C 可停止服务
echo.

:: Windows 下 uvicorn 不使用 uvloop，--loop asyncio 是默认且稳定的选项
.venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000 --loop asyncio

pause
