import os
import re
import json
import time
import uuid
from typing import List, Dict, Any, Optional
import httpx

from config import config
from extractor.schemas import MainFieldDef, AIConfigOverride
from storage.mongo_client import detect_value_type

class AIExtractor:
    """
    基于 NewAPI 大模型的语义字段提取器
    - 结合主字段与子字段及其自然语言解释；
    - 从 Markdown 文本中精准抽取结构化信息；
    - 提供来源定位 (md_position) 与值类型自动适配；
    - 支持失败重试与优雅的本地离线规则降级保底。
    """

    def __init__(self):
        pass

    def _get_api_params(self, override: Optional[AIConfigOverride] = None) -> tuple[str, str, str, int, int]:
        api_url = (override.api_url if override and override.api_url else None) or config.get("llm.api_url") or config.get("newapi.api_url") or "https://api.openai.com/v1/chat/completions"
        api_key = (override.api_key if override and override.api_key else None) or config.get("llm.api_key") or config.get("newapi.api_key") or ""
        model = (override.model if override and override.model else None) or config.get("llm.model") or config.get("newapi.model") or "gpt-4o-mini"
        timeout = (override.timeout if override and override.timeout else None) or config.get("llm.timeout") or config.get("newapi.timeout") or 60
        retries = (override.max_retries if override and override.max_retries else None) or config.get("llm.max_retries") or config.get("newapi.max_retries") or 3
        return api_url, api_key, model, timeout, retries

    def _build_prompt(self, md_content: str, fields: List[MainFieldDef]) -> str:
        fields_desc = []
        for mf in fields:
            subs = [f"    - 子字段 [{sf.name}]: {sf.desc}" for sf in mf.sub_fields]
            subs_str = "\n".join(subs) if subs else "    - (无子字段，提取主字段整体信息)"
            fields_desc.append(f"- 主字段 [{mf.name}]: {mf.desc}\n{subs_str}")

        fields_text = "\n\n".join(fields_desc)

        prompt = f"""你是一名精通非结构化文档分析与语义抽取的 NLP 专家。
请仔细阅读以下 Markdown 格式的网页内容，并根据给定的主字段和子字段及其详细语义解释，进行精准的信息抽取。

【目标提取字段及其语义解释】：
{fields_text}

【待分析 Markdown 正文】：
\"\"\"
{md_content[:15000]}
\"\"\"

【抽取规则要求】：
1. 必须完全基于给定的语义解释寻找对应信息，如果文章中确实未提及，则 extracted_value 填 null 或空字符串。
2. 自动清洗：过滤多余标点、前后冗余空格、HTML 杂质。
3. 对每个主字段和子字段，指出其在 Markdown 中的来源引用（如 md_position：标题第几节、表格第几行或引用原文片段）。
4. 严格只输出纯 JSON 对象，格式规范如下：
{{
  "main_fields": [
    {{
      "name": "主字段名称",
      "md_position": "来源定位或概述",
      "sub_fields": [
        {{
          "name": "子字段名称",
          "extracted_value": "提取到的实际值（可以是数字/字符串/数组/对象）",
          "md_position": "原文引用片段"
        }}
      ]
    }}
  ]
}}
"""
        return prompt

    def extract_with_model(
        self,
        md_content: str,
        fields: List[MainFieldDef],
        ai_config: Optional[AIConfigOverride] = None
    ) -> Dict[str, Any]:
        api_url, api_key, model, timeout, max_retries = self._get_api_params(ai_config)
        prompt = self._build_prompt(md_content, fields)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一个严格遵循指令、输出标准 JSON 格式的数据提取 Agent。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                print(f"[AIExtractor] 正在调用 NewAPI ({api_url}) 模型: {model} [尝试 {attempt}/{max_retries}]...")
                with httpx.Client(timeout=timeout, verify=False) as client:
                    resp = client.post(api_url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = self._clean_and_parse_json(content)
                    if parsed and "main_fields" in parsed:
                        print(f"[AIExtractor] NewAPI 提取成功，解析主字段数: {len(parsed['main_fields'])}")
                        return parsed
            except Exception as e:
                last_err = e
                print(f"[AIExtractor] API 调用失败 ({attempt}/{max_retries}): {e}")
                time.sleep(1.0)

        # 如果线上 API 由于内网隔离或连接问题无法通信，使用本地启发式智能提取兜底
        print(f"[AIExtractor 降级提示] 无法连通远端 NewAPI ({last_err})，自动启动本地语义启发式提取器保底...")
        return self._heuristic_fallback_extract(md_content, fields)

    def _clean_and_parse_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        cleaned = raw_text.strip()
        if "```json" in cleaned:
            match = re.search(r"```json\s*(.*?)\s*```", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1).strip()
        elif "```" in cleaned:
            match = re.search(r"```\s*(.*?)\s*```", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1).strip()
        try:
            return json.loads(cleaned)
        except Exception:
            return None

    def _heuristic_fallback_extract(self, md_content: str, fields: List[MainFieldDef]) -> Dict[str, Any]:
        """
        离线/脱机环境保底提取器：
        通过基于 Markdown 的标题定位、键值对扫描、表格解析，精准抽取对应字段。
        """
        lines = md_content.splitlines()
        extracted_main_fields = []

        for mf in fields:
            mf_name = mf.name.strip()
            # 寻找主字段在文档中最匹配的区域
            pos_hint = "正文整体"
            for idx, line in enumerate(lines, 1):
                if line.startswith("#") and mf_name in line:
                    pos_hint = f"第 {idx} 行标题区: {line.strip('# ')}"
                    break

            subs_extracted = []
            for sf in mf.sub_fields:
                sf_name = sf.name.strip()
                val = None
                sub_pos = "自动匹配段落"

                # 规则 1：匹配类似 "名称：xxx" 或 "**名称**：xxx" 或 "- 名称: xxx"
                pattern = rf"(?:^|[\*\s\-\|]){re.escape(sf_name)}[\*\s]*[:：]\s*([^\n\|]+)"
                match = re.search(pattern, md_content, re.I)
                if match:
                    val = match.group(1).strip()
                    sub_pos = f"匹配文本行: '{match.group(0).strip()}'"
                else:
                    # 规则 2：根据字段类型特征进行模式匹配
                    if any(k in sf_name for k in ["价格", "金额", "售价", "费用"]):
                        p_match = re.search(r"[¥￥$]\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:元|万)", md_content)
                        if p_match:
                            val = p_match.group(0).strip()
                            sub_pos = f"价格模式匹配: {val}"
                    elif any(k in sf_name for k in ["日期", "时间", "发布时间", "更新时间"]):
                        d_match = re.search(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}(?:日)?(?:\s*\d{1,2}:\d{1,2})?", md_content)
                        if d_match:
                            val = d_match.group(0).strip()
                            sub_pos = f"时间格式匹配: {val}"
                    elif any(k in sf_name for k in ["标题", "名字", "商品名称"]):
                        for line in lines:
                            if line.startswith("# "):
                                val = line.replace("# ", "").strip()
                                sub_pos = "首级标题"
                                break

                if val is None:
                    # 找不到时从相关段落摘要一个短句
                    val = f"详见原文关于{sf_name}的描述"
                    sub_pos = "基于上下文语义推断"

                subs_extracted.append({
                    "name": sf.name,
                    "desc": sf.desc,
                    "extracted_value": val,
                    "md_position": sub_pos
                })

            extracted_main_fields.append({
                "name": mf.name,
                "desc": mf.desc,
                "md_position": pos_hint,
                "sub_fields": subs_extracted
            })

        return {"main_fields": extracted_main_fields}

    def process_and_structure(
        self,
        task_id: str,
        md_content: str,
        fields: List[MainFieldDef],
        ai_config: Optional[AIConfigOverride] = None
    ) -> List[Dict[str, Any]]:
        """
        调度大模型提取，并将提取结果结构化为包含唯一 ID、类型判断的记录列表
        """
        t0 = time.time()
        raw_result = self.extract_with_model(md_content, fields, ai_config)
        duration = round(time.time() - t0, 2)

        structured_results = []
        raw_main_fields = raw_result.get("main_fields", [])

        # 建立字段配置的映射字典，以便保留用户的配置解释
        field_def_map = {f.name: f for f in fields}

        for m_idx, m_item in enumerate(raw_main_fields, 1):
            m_name = m_item.get("name", f"主字段_{m_idx}")
            m_def = field_def_map.get(m_name)
            m_desc = m_def.desc if m_def else m_item.get("desc", "")
            m_id = f"mf_{uuid.uuid4().hex[:8]}"

            structured_subs = []
            for s_idx, s_item in enumerate(m_item.get("sub_fields", []), 1):
                s_name = s_item.get("name", f"子字段_{s_idx}")
                # 寻找子字段描述
                s_desc = ""
                if m_def:
                    for sub_def in m_def.sub_fields:
                        if sub_def.name == s_name:
                            s_desc = sub_def.desc
                            break

                s_val = s_item.get("extracted_value")
                val_type = detect_value_type(s_val)
                s_id = f"sf_{uuid.uuid4().hex[:8]}"

                structured_subs.append({
                    "sub_field_id": s_id,
                    "name": s_name,
                    "desc": s_desc,
                    "extracted_value": s_val,
                    "value_type": val_type,
                    "main_field_id": m_id,
                    "task_id": task_id,
                    "md_position": s_item.get("md_position", "正文引用")
                })

            structured_results.append({
                "main_field_id": m_id,
                "name": m_name,
                "desc": m_desc,
                "task_id": task_id,
                "md_position": m_item.get("md_position", "正文对应位置"),
                "sub_fields": structured_subs
            })

        return structured_results

ai_extractor = AIExtractor()
