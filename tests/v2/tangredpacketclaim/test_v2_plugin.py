"""不可躺自动抢红包 V2 插件的静态合同测试。"""

import ast
import json
from pathlib import Path


ROOT = Path(__file__).parents[3]
PLUGIN_SOURCE = ROOT / "plugins.v2" / "tangredpacketclaim" / "__init__.py"


def test_v2_metadata_and_plugin_version_match() -> None:
    """V2 索引、源码版本和 V3 回退标记必须正确。"""
    metadata = json.loads((ROOT / "package.v2.json").read_text(encoding="utf-8"))["TangRedPacketClaim"]
    tree = ast.parse(PLUGIN_SOURCE.read_text(encoding="utf-8"))
    versions = [
        node.value.value
        for class_node in ast.walk(tree)
        if isinstance(class_node, ast.ClassDef)
        for node in class_node.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "plugin_version" for target in node.targets)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]

    assert metadata["version"] == "0.0.1"
    assert metadata["v3"] is False
    assert versions == [metadata["version"]]


def test_v2_plugin_implements_required_lifecycle_methods() -> None:
    """V2 插件必须提供宿主生命周期和配置接口。"""
    tree = ast.parse(PLUGIN_SOURCE.read_text(encoding="utf-8"))
    methods = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert {"init_plugin", "get_state", "get_api", "get_form", "get_page", "stop_service"} <= methods
