import pytest
from extractor.ai_extractor import AIExtractor
from extractor.schemas import MainFieldDef, SubFieldDef
from storage.mongo_client import detect_value_type

@pytest.fixture
def extractor():
    return AIExtractor()

def test_detect_value_type():
    assert detect_value_type(123) == "number"
    assert detect_value_type(99.9) == "number"
    assert detect_value_type("199.50") == "number"
    assert detect_value_type("2026-10-13") == "datetime"
    assert detect_value_type("2026年10月13日") == "datetime"
    assert detect_value_type(["tag1", "tag2"]) == "array"
    assert detect_value_type({"key": "val"}) == "object"
    assert detect_value_type(True) == "boolean"
    assert detect_value_type("普通纯文本描述") == "text"
    assert detect_value_type(None) == "null"

def test_build_prompt(extractor):
    md_sample = "# 苹果 iPhone 16\n售价：¥5999\n发布时间：2026年9月"
    fields = [
        MainFieldDef(
            name="商品属性",
            desc="商品的销售基本要素",
            sub_fields=[
                SubFieldDef(name="售价", desc="页面展示的实际售价"),
                SubFieldDef(name="发布时间", desc="官方发布日期")
            ]
        )
    ]
    prompt = extractor._build_prompt(md_sample, fields)
    assert "商品属性" in prompt
    assert "售价" in prompt
    assert "页面展示的实际售价" in prompt
    assert "苹果 iPhone 16" in prompt

def test_heuristic_fallback_extraction(extractor):
    md_sample = """# 华为 Mate 70 Pro
- **商品分类**：智能手机
- **官方售价**：¥6999
- **发布日期**：2026-11-05
这是关于该旗舰手机的详细介绍。
    """
    fields = [
        MainFieldDef(
            name="基本信息",
            desc="手机基本信息",
            sub_fields=[
                SubFieldDef(name="官方售价", desc="手机销售价格"),
                SubFieldDef(name="发布日期", desc="手机上市日期")
            ]
        )
    ]
    result = extractor._heuristic_fallback_extract(md_sample, fields)
    assert "main_fields" in result
    mf = result["main_fields"][0]
    assert mf["name"] == "基本信息"
    assert len(mf["sub_fields"]) == 2
    sub1 = mf["sub_fields"][0]
    assert "6999" in str(sub1["extracted_value"])
    sub2 = mf["sub_fields"][1]
    assert "2026-11-05" in str(sub2["extracted_value"])
