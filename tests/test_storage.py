import pytest
import uuid
from storage.mongo_client import StorageManager

@pytest.fixture
def storage_mgr(tmp_path):
    mgr = StorageManager()
    # 使用临时测试目录替代实际存储
    mgr.local_dir = tmp_path
    mgr.mode = "local_fallback"
    return mgr

def test_task_save_and_retrieve(storage_mgr):
    task_id = f"test_task_{uuid.uuid4().hex[:6]}"
    task_data = {
        "task_id": task_id,
        "url": "https://test.org/article",
        "domain": "test.org",
        "crawl_time": "2026-10-13 12:00:00",
        "md_file_path": "/tmp/test.md",
        "md_file_name": f"{task_id}_test_org_20261013_120000.md",
        "status": "completed"
    }
    storage_mgr.save_task(task_data)
    tasks = storage_mgr.list_tasks(task_id_filter=task_id)
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == task_id
    assert tasks[0]["url"] == "https://test.org/article"

def test_relational_uniqueness_and_subfield_association(storage_mgr):
    task_id = f"test_task_{uuid.uuid4().hex[:6]}"
    main_fields = [
        {
            "main_field_id": "mf_001",
            "name": "公司信息",
            "desc": "基本概览",
            "md_position": "第1行",
            "sub_fields": [
                {
                    "sub_field_id": "sf_001",
                    "name": "公司名称",
                    "desc": "法定全称",
                    "extracted_value": "测试科技有限公司",
                    "value_type": "text",
                    "md_position": "正文"
                },
                # 测试故意传入相同的 sub_field_id，系统应自动解决冲突，确保关联唯一性
                {
                    "sub_field_id": "sf_001",
                    "name": "注册资本",
                    "desc": "资金规模",
                    "extracted_value": 5000000,
                    "value_type": "number",
                    "md_position": "表格第2行"
                }
            ]
        }
    ]

    summary = storage_mgr.save_extracted_fields(task_id, main_fields)
    assert summary["main_fields_saved"] == 1
    assert summary["sub_fields_saved"] == 2

    # 查询子字段验证
    subs = storage_mgr.list_sub_fields(task_id_filter=task_id)
    assert len(subs) == 2
    sub_ids = [s["sub_field_id"] for s in subs]
    # 确保子字段 ID 唯一，无重复
    assert len(set(sub_ids)) == 2
    # 验证主子字段关联外键
    assert all(s["main_field_id"] == "mf_001" for s in subs)
    assert all(s["task_id"] == task_id for s in subs)

def test_filter_subfields_by_main_id(storage_mgr):
    task_id = "task_multi_001"
    main_fields = [
        {
            "main_field_id": "mf_A",
            "name": "模块 A",
            "sub_fields": [{"sub_field_id": "sf_A1", "name": "A1", "extracted_value": "valA"}]
        },
        {
            "main_field_id": "mf_B",
            "name": "模块 B",
            "sub_fields": [{"sub_field_id": "sf_B1", "name": "B1", "extracted_value": "valB"}]
        }
    ]
    storage_mgr.save_extracted_fields(task_id, main_fields)
    subs_a = storage_mgr.list_sub_fields(task_id_filter=task_id, main_id_filter="mf_A")
    assert len(subs_a) == 1
    assert subs_a[0]["name"] == "A1"
