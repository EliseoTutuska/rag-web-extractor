import os
import uuid
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import config
from crawler.spider import crawler
from crawler.md_converter import HTMLToMarkdownConverter
from extractor.ai_extractor import ai_extractor
from extractor.schemas import (
    CrawlRequest, ExtractRequest, MainFieldDef, SubFieldDef, AIConfigOverride
)
from storage.mongo_client import storage, detect_value_type

app = FastAPI(
    title="通用爬虫与数据智能提取系统",
    description="面向 RAG & Agent 数据管线的网页爬取、Markdown清洗、基于 NewAPI 语义提取与 MongoDB 存储服务",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 实时任务运行状态与日志缓存
TASK_LOGS: Dict[str, List[Dict[str, str]]] = {}
ACTIVE_TASKS: Dict[str, Dict[str, Any]] = {}

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# --- 1. 系统与配置接口 ---
@app.get("/api/system/status")
def get_system_status():
    return {
        "status": "online",
        "storage_mode": storage.mode,
        "mongodb_connected": storage.is_connected,
        "mongodb_uri": config.get("mongodb.uri"),
        "llm_url": config.get("llm.api_url") or config.get("newapi.api_url"),
        "llm_model": config.get("llm.model") or config.get("newapi.model"),
        "newapi_url": config.get("llm.api_url") or config.get("newapi.api_url"),
        "newapi_model": config.get("llm.model") or config.get("newapi.model"),
        "storage_dir": config.get("crawler.storage_dir")
    }

@app.post("/api/system/config")
def update_system_config(payload: Dict[str, Any]):
    if "mongodb_uri" in payload and payload["mongodb_uri"]:
        config.set("mongodb.uri", payload["mongodb_uri"])
        storage.connect(payload["mongodb_uri"])
    if "llm_url" in payload and payload["llm_url"]:
        config.set("llm.api_url", payload["llm_url"])
    elif "newapi_url" in payload and payload["newapi_url"]:
        config.set("llm.api_url", payload["newapi_url"])
    if "llm_key" in payload and payload["llm_key"]:
        config.set("llm.api_key", payload["llm_key"])
    elif "newapi_key" in payload and payload["newapi_key"]:
        config.set("llm.api_key", payload["newapi_key"])
    if "llm_model" in payload and payload["llm_model"]:
        config.set("llm.model", payload["llm_model"])
    elif "newapi_model" in payload and payload["newapi_model"]:
        config.set("llm.model", payload["newapi_model"])
    config.save()
    return {"status": "success", "message": "配置更新成功", "storage_mode": storage.mode}

# --- 2. 爬虫任务控制与日志接口 ---
@app.post("/api/crawl")
def start_crawl(req: CrawlRequest):
    task_id = req.task_id or f"task_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    urls = [u.strip() for u in req.urls if u.strip()]
    if not urls:
        raise HTTPException(status_code=400, detail="爬取网址列表不可为空")

    TASK_LOGS[task_id] = []
    ACTIVE_TASKS[task_id] = {
        "task_id": task_id,
        "urls": urls,
        "status": "running",
        "start_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    def append_log(msg: str, level: str = "INFO"):
        TASK_LOGS[task_id].append({
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "message": msg
        })

    # 同步或后台运行爬虫
    try:
        append_log(f"任务初始化完成，准备抓取 {len(urls)} 个网址...")
        results = crawler.run_crawl_task(
            task_id=task_id,
            urls=urls,
            delay=req.delay or 1.0,
            log_callback=append_log
        )

        for res in results:
            storage.save_task(res)

        ACTIVE_TASKS[task_id]["status"] = "completed"
        append_log("任务全部处理完毕，已同步至 MongoDB 基础任务表！", "SUCCESS")

        return {
            "task_id": task_id,
            "status": "completed",
            "results_count": len(results),
            "results": results
        }
    except Exception as e:
        ACTIVE_TASKS[task_id]["status"] = "failed"
        append_log(f"任务异常终止: {str(e)}", "ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tasks/{task_id}/stop")
def stop_crawl_task(task_id: str):
    crawler.stop_task(task_id)
    if task_id in TASK_LOGS:
        TASK_LOGS[task_id].append({
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "level": "WARN",
            "message": "用户触发了停止任务操作"
        })
    return {"task_id": task_id, "status": "stopping"}

@app.get("/api/tasks/{task_id}/logs")
def get_task_logs(task_id: str):
    logs = TASK_LOGS.get(task_id, [])
    task_info = ACTIVE_TASKS.get(task_id, {})
    return {"task_id": task_id, "logs": logs, "info": task_info}

@app.get("/api/tasks")
def list_tasks(task_id: Optional[str] = None):
    return storage.list_tasks(limit=100, task_id_filter=task_id)

@app.get("/api/tasks/{task_id}")
def get_task_detail(task_id: str):
    tasks = storage.list_tasks(limit=10, task_id_filter=task_id)
    if not tasks:
        raise HTTPException(status_code=404, detail="未找到该任务")

    task = tasks[0]
    # 读取 MD 原文
    md_path = task.get("md_file_path")
    md_content = ""
    if md_path and Path(md_path).exists():
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                md_content = f.read()
        except Exception as e:
            md_content = f"[读取文件错误]: {e}"
    task["md_content"] = md_content
    return task

@app.get("/api/tasks/{task_id}/download-md")
def download_task_md(task_id: str):
    tasks = storage.list_tasks(limit=1, task_id_filter=task_id)
    if not tasks:
        raise HTTPException(status_code=404, detail="未找到该任务")
    task = tasks[0]
    md_path = task.get("md_file_path")
    if not md_path or not Path(md_path).exists():
        raise HTTPException(status_code=404, detail="MD 文件不存在")
    return FileResponse(
        path=md_path,
        filename=task.get("md_file_name") or f"{task_id}.md",
        media_type="text/markdown"
    )

# --- 3. 自定义字段提取接口 ---
@app.post("/api/extract")
def extract_fields(req: ExtractRequest):
    # 获取任务及对应 MD 文件
    tasks = storage.list_tasks(limit=1, task_id_filter=req.task_id)
    if not tasks:
        raise HTTPException(status_code=404, detail=f"未找到任务 {req.task_id}，请先爬取")

    task = tasks[0]
    md_path = task.get("md_file_path")
    if not md_path or not Path(md_path).exists():
        raise HTTPException(status_code=400, detail="该任务对应的 MD 文件未落盘或已丢失")

    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    # 执行智能语义提取
    structured_results = ai_extractor.process_and_structure(
        task_id=req.task_id,
        md_content=md_content,
        fields=req.fields,
        ai_config=req.ai_config
    )

    # 存入 MongoDB 主字段表与子字段表（带关联唯一性校验）
    save_summary = storage.save_extracted_fields(req.task_id, structured_results)

    return {
        "status": "success",
        "task_id": req.task_id,
        "results": structured_results,
        "storage_summary": save_summary
    }

# --- 4. 数据存储与分析查看接口 ---
@app.get("/api/storage/data")
def get_storage_data(table: str = Query("tasks"), task_id: Optional[str] = None):
    if table == "tasks":
        return storage.list_tasks(limit=100, task_id_filter=task_id)
    elif table == "main_fields":
        return storage.list_main_fields(task_id_filter=task_id)
    elif table == "sub_fields":
        return storage.list_sub_fields(task_id_filter=task_id)
    else:
        raise HTTPException(status_code=400, detail="未知的数据表名")

# --- 5. 快速预置模板 (参考面试题目要求) ---
@app.get("/api/templates")
def get_preset_templates():
    return [
        {
            "id": "wiki",
            "name": "百科词条模板（百度百科/维基百科）",
            "description": "用于人物、概念、机构条目的结构化提取",
            "fields": [
                {
                    "name": "基础概览",
                    "desc": "词条的名称、身份定位与核心一句话定义",
                    "sub_fields": [
                        {"name": "词条名称", "desc": "页面主词条全称"},
                        {"name": "人物身份/领域", "desc": "该人物或事物的专业领域或职务角色"},
                        {"name": "生卒年/创建日期", "desc": "出生日期、创立年份等时间维度"}
                    ]
                },
                {
                    "name": "核心成就与经历",
                    "desc": "词条记载的代表性荣誉、重大历史事件或作品",
                    "sub_fields": [
                        {"name": "主要成就", "desc": "获得的重大奖项或历史地位"},
                        {"name": "代表作品", "desc": "出版的专著、发明的技术或代表作列表"}
                    ]
                }
            ]
        },
        {
            "id": "ecommerce",
            "name": "电商商品详情模板",
            "description": "用于电商网站商品价格、规格与评价信息提取",
            "fields": [
                {
                    "name": "商品基本信息",
                    "desc": "商品标题、品牌、商品型号与所属类目",
                    "sub_fields": [
                        {"name": "商品标题", "desc": "页面展示的完整商品售卖标题"},
                        {"name": "品牌名称", "desc": "制造或销售该商品的品牌"},
                        {"name": "商品分类", "desc": "所属一级或二级商品品类"}
                    ]
                },
                {
                    "name": "交易属性",
                    "desc": "商品的定价、库存与售后承诺",
                    "sub_fields": [
                        {"name": "实际售价", "desc": "用户当前能下单的实际到手单价（纯数值）"},
                        {"name": "原价/划线价", "desc": "商品吊牌原价或划线参考价格"},
                        {"name": "发货地/运费", "desc": "商品发货城市或运费政策"}
                    ]
                }
            ]
        },
        {
            "id": "news",
            "name": "新闻资讯详情模板",
            "description": "用于新闻门户网站标题、作者、正文要素与时间提取",
            "fields": [
                {
                    "name": "文章元数据",
                    "desc": "新闻发布的基本要素",
                    "sub_fields": [
                        {"name": "新闻标题", "desc": "新闻报道的主标题"},
                        {"name": "发布时间", "desc": "报道发布的具体年-月-日 时:分"},
                        {"name": "发布机构/作者", "desc": "撰写记者姓名或来源媒体名称"}
                    ]
                },
                {
                    "name": "核心事件要素",
                    "desc": "新闻报道中 5W1H 的核心事实",
                    "sub_fields": [
                        {"name": "核心事件总结", "desc": "用一两句话总结本次新闻的核心事实"},
                        {"name": "关键涉及人员/主体", "desc": "报道中重点提及的机构、官员或公众人物"}
                    ]
                }
            ]
        }
    ]

# 静态资源挂载
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = config.get("app.port", 8000)
    host = config.get("app.host", "0.0.0.0")
    print(f"🚀 系统已启动，请在浏览器打开访问: http://localhost:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=False)
