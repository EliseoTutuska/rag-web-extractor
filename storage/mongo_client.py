import os
import re
import json
import uuid
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import pymongo
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from config import config

def detect_value_type(val: Any) -> str:
    """
    自动适配字段值类型：文本 / 数字 / 时间 / 数组 / 字典
    """
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "boolean"
    if isinstance(val, (int, float)):
        return "number"
    if isinstance(val, (list, tuple)):
        return "array"
    if isinstance(val, dict):
        return "object"
    if isinstance(val, str):
        # 尝试判断是否是纯数字
        if re.match(r"^-?\d+(\.\d+)?$", val.strip()):
            return "number"
        # 尝试判断是否是日期时间
        date_patterns = [
            r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}",
            r"^\d{4}年\d{1,2}月\d{1,2}日"
        ]
        if any(re.match(p, val.strip()) for p in date_patterns):
            return "datetime"
        return "text"
    return "text"

class StorageManager:
    """
    统一数据存储层：支持 MongoDB 与本地轻量持久化透明切换
    包含三张核心表：
    1. crawl_tasks (基础任务表)
    2. main_fields (主字段表)
    3. sub_fields  (子字段表)
    严格遵循关联唯一性校验与动态字段类型适配。
    """

    def __init__(self):
        self.client: Optional[pymongo.MongoClient] = None
        self.db = None
        self.is_connected = False
        self.mode = "init"  # "mongodb" 或 "local_fallback"
        self.local_dir = Path("data/local_storage")
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.connect()

    def connect(self, custom_uri: Optional[str] = None):
        uri = custom_uri or config.get("mongodb.uri", "mongodb://localhost:27017/rag_crawler")
        timeout_ms = config.get("mongodb.server_selection_timeout_ms", 2500)
        try:
            client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=timeout_ms, connectTimeoutMS=timeout_ms)
            # 测试 ping
            client.admin.command('ping')
            self.client = client
            # 解析 db 名称
            db_name = uri.split("/")[-1].split("?")[0] or "rag_crawler"
            self.db = self.client[db_name]
            self.is_connected = True
            self.mode = "mongodb"
            print(f"[Storage] 成功连接至远端 MongoDB: {uri} (DB: {db_name})")
            self._ensure_indexes()
        except Exception as e:
            self.is_connected = False
            self.mode = "local_fallback"
            print(f"[Storage] 连接 MongoDB [{uri}] 失败 ({e})，已智能开启本地持久化存储模式以确保平稳运行。")

    def _ensure_indexes(self):
        if self.mode == "mongodb" and self.db is not None:
            try:
                self.db.crawl_tasks.create_index("task_id")
                self.db.main_fields.create_index([("task_id", 1), ("main_field_id", 1)])
                # 唯一复合索引确保唯一性
                self.db.sub_fields.create_index(
                    [("task_id", 1), ("main_field_id", 1), ("sub_field_id", 1)],
                    unique=True
                )
            except Exception as e:
                print(f"[Storage] 创建索引警告: {e}")

    # --- 本地 Fallback 存储文件辅助方法 ---
    def _get_local_file(self, table_name: str) -> Path:
        return self.local_dir / f"{table_name}.json"

    def _load_local_table(self, table_name: str) -> List[Dict[str, Any]]:
        path = self._get_local_file(table_name)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_local_table(self, table_name: str, data: List[Dict[str, Any]]):
        path = self._get_local_file(table_name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    # --- 1. 基础任务表 (crawl_tasks) ---
    def save_task(self, task_data: Dict[str, Any]) -> str:
        """
        保存或更新基础任务表记录
        核心字段：任务 ID、网址、爬取时间、MD 文件存储路径、MD 文件名称
        """
        task_id = task_data.get("task_id")
        record = {
            "task_id": task_id,
            "url": task_data.get("url"),
            "domain": task_data.get("domain", ""),
            "crawl_time": task_data.get("crawl_time") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "md_file_path": task_data.get("md_file_path"),
            "md_file_name": task_data.get("md_file_name"),
            "status": task_data.get("status", "completed"),
            "error": task_data.get("error"),
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        if self.mode == "mongodb":
            self.db.crawl_tasks.update_one(
                {"task_id": task_id, "url": record["url"]},
                {"$set": record},
                upsert=True
            )
        else:
            table = self._load_local_table("crawl_tasks")
            # 过滤掉已存在的同一 task_id + url 记录
            table = [r for r in table if not (r.get("task_id") == task_id and r.get("url") == record["url"])]
            table.insert(0, record)
            self._save_local_table("crawl_tasks", table)
        return task_id

    def list_tasks(self, limit: int = 50, task_id_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.mode == "mongodb":
            query = {"task_id": {"$regex": task_id_filter, "$options": "i"}} if task_id_filter else {}
            cursor = self.db.crawl_tasks.find(query, {"_id": 0}).sort("crawl_time", -1).limit(limit)
            return list(cursor)
        else:
            table = self._load_local_table("crawl_tasks")
            if task_id_filter:
                table = [r for r in table if task_id_filter.lower() in str(r.get("task_id", "")).lower()]
            return table[:limit]

    # --- 2. 主字段表 (main_fields) 与 3. 子字段表 (sub_fields) 存储 ---
    def save_extracted_fields(
        self,
        task_id: str,
        main_fields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        保存主字段与子字段，严格执行关联唯一性校验
        """
        saved_main_count = 0
        saved_sub_count = 0

        # 如果已有该任务历史记录，做软清理或更新
        if self.mode == "mongodb":
            self.db.main_fields.delete_many({"task_id": task_id})
            self.db.sub_fields.delete_many({"task_id": task_id})

        local_main_table = self._load_local_table("main_fields") if self.mode != "mongodb" else []
        local_sub_table = self._load_local_table("sub_fields") if self.mode != "mongodb" else []

        if self.mode != "mongodb":
            local_main_table = [r for r in local_main_table if r.get("task_id") != task_id]
            local_sub_table = [r for r in local_sub_table if r.get("task_id") != task_id]

        seen_main_ids = set()
        seen_sub_keys = set()  # (task_id, main_field_id, sub_field_id)

        for mf in main_fields:
            m_id = mf.get("main_field_id") or f"mf_{uuid.uuid4().hex[:8]}"
            m_name = mf.get("name", "")
            m_desc = mf.get("desc", "")
            m_pos = mf.get("md_position", "")

            # 主字段查重
            if m_id in seen_main_ids:
                m_id = f"{m_id}_{uuid.uuid4().hex[:4]}"
            seen_main_ids.add(m_id)

            main_record = {
                "main_field_id": m_id,
                "name": m_name,
                "desc": m_desc,
                "task_id": task_id,
                "md_position": m_pos,
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            if self.mode == "mongodb":
                self.db.main_fields.insert_one(main_record)
            else:
                local_main_table.append(main_record)
            saved_main_count += 1

            # 处理其下的子字段
            for sf in mf.get("sub_fields", []):
                s_id = sf.get("sub_field_id") or f"sf_{uuid.uuid4().hex[:8]}"
                sub_key = (task_id, m_id, s_id)

                # 插入前验证子字段与主字段的关联唯一性
                if sub_key in seen_sub_keys:
                    s_id = f"{s_id}_{uuid.uuid4().hex[:4]}"
                    sub_key = (task_id, m_id, s_id)
                seen_sub_keys.add(sub_key)

                val = sf.get("extracted_value")
                val_type = sf.get("value_type") or detect_value_type(val)

                sub_record = {
                    "sub_field_id": s_id,
                    "name": sf.get("name", ""),
                    "desc": sf.get("desc", ""),
                    "extracted_value": val,
                    "value_type": val_type,
                    "main_field_id": m_id,
                    "task_id": task_id,
                    "md_position": sf.get("md_position", ""),
                    "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

                if self.mode == "mongodb":
                    self.db.sub_fields.insert_one(sub_record)
                else:
                    local_sub_table.append(sub_record)
                saved_sub_count += 1

        if self.mode != "mongodb":
            self._save_local_table("main_fields", local_main_table)
            self._save_local_table("sub_fields", local_sub_table)

        return {
            "task_id": task_id,
            "main_fields_saved": saved_main_count,
            "sub_fields_saved": saved_sub_count,
            "storage_mode": self.mode
        }

    # --- 查询接口 ---
    def list_main_fields(self, task_id_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.mode == "mongodb":
            q = {"task_id": {"$regex": task_id_filter, "$options": "i"}} if task_id_filter else {}
            return list(self.db.main_fields.find(q, {"_id": 0}).sort("created_at", -1))
        else:
            table = self._load_local_table("main_fields")
            if task_id_filter:
                table = [r for r in table if task_id_filter.lower() in str(r.get("task_id", "")).lower()]
            return table

    def list_sub_fields(self, task_id_filter: Optional[str] = None, main_id_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.mode == "mongodb":
            q = {}
            if task_id_filter:
                q["task_id"] = {"$regex": task_id_filter, "$options": "i"}
            if main_id_filter:
                q["main_field_id"] = main_id_filter
            return list(self.db.sub_fields.find(q, {"_id": 0}).sort("created_at", -1))
        else:
            table = self._load_local_table("sub_fields")
            if task_id_filter:
                table = [r for r in table if task_id_filter.lower() in str(r.get("task_id", "")).lower()]
            if main_id_filter:
                table = [r for r in table if r.get("main_field_id") == main_id_filter]
            return table

storage = StorageManager()
