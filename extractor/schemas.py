from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field

# --- 爬虫相关模型 ---
class CrawlRequest(BaseModel):
    task_id: Optional[str] = Field(None, description="任务ID，若为空则由系统自动生成")
    urls: List[str] = Field(..., description="待爬取网址列表（支持单行或多行批量输入）")
    delay: Optional[float] = Field(1.0, description="抓取间隔时间（秒），防反爬")

class CrawlLogItem(BaseModel):
    timestamp: str
    level: str
    message: str

class CrawlTaskStatus(BaseModel):
    task_id: str
    urls: List[str]
    status: str = Field("pending", description="pending / running / completed / failed")
    progress: float = 0.0
    crawl_time: Optional[str] = None
    md_file_path: Optional[str] = None
    md_file_name: Optional[str] = None
    md_content: Optional[str] = None
    domain: Optional[str] = None
    error: Optional[str] = None

# --- 字段配置与智能提取相关模型 ---
class SubFieldDef(BaseModel):
    name: str = Field(..., description="子字段名称，如 '市场售价'")
    desc: str = Field(..., description="子字段解释，如 '页面展示的实际折扣价格，纯数字'")

class MainFieldDef(BaseModel):
    name: str = Field(..., description="主字段名称，如 '商品基本信息'")
    desc: str = Field(..., description="主字段解释，如 '商品名称、品牌与分类归属'")
    sub_fields: List[SubFieldDef] = Field(default_factory=list, description="归属于该主字段的子字段列表")

class AIConfigOverride(BaseModel):
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    timeout: Optional[int] = None
    max_retries: Optional[int] = None

class ExtractRequest(BaseModel):
    task_id: str = Field(..., description="要提取的已完成爬虫任务ID")
    fields: List[MainFieldDef] = Field(..., description="用户配置的主字段与子字段定义")
    ai_config: Optional[AIConfigOverride] = None

class SubFieldResult(BaseModel):
    sub_field_id: str
    name: str
    desc: str
    extracted_value: Any
    value_type: str = Field("text", description="text / number / date / array / object")
    main_field_id: str
    task_id: str
    md_position: str = Field("", description="来源 MD 的原文引用或定位位置")

class MainFieldResult(BaseModel):
    main_field_id: str
    name: str
    desc: str
    task_id: str
    md_position: str = ""
    sub_fields: List[SubFieldResult] = Field(default_factory=list)

class ExtractResponse(BaseModel):
    task_id: str
    results: List[MainFieldResult]
    raw_json: Dict[str, Any]
    duration_seconds: float
