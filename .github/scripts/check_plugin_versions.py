#!/usr/bin/env python3
"""校验 V3 市场索引、插件目录和类级 plugin_version。"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path


def semantic_version(value: object) -> tuple[int, ...] | None:
    """解析普通语义版本号。"""
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", str(value or "").strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def source_version(path: Path) -> str | None:
    """从插件主类中读取类级 plugin_version。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            target = item.targets[0] if isinstance(item, ast.Assign) and item.targets else getattr(item, "target", None)
            if isinstance(target, ast.Name) and target.id == "plugin_version":
                value = item.value
                return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None
    return None


def main() -> int:
    """检查 package.v3.json 的全部插件条目。"""
    package_path = Path("package.v3.json")
    package = json.loads(package_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for plugin_id, metadata in package.items():
        if not isinstance(metadata, dict):
            errors.append(f"{plugin_id}: 索引条目必须是对象")
            continue
        version = str(metadata.get("version") or "")
        if semantic_version(version) is None:
            errors.append(f"{plugin_id}: version 不是合法语义版本：{version}")
        history = metadata.get("history")
        if not isinstance(history, dict) or not history:
            errors.append(f"{plugin_id}: history 不能为空")
        elif next(iter(history)) not in {version, f"v{version}"}:
            errors.append(f"{plugin_id}: history 首项必须是当前版本 {version}")
        plugin_dir = Path("plugins.v3") / plugin_id.lower()
        init_file = plugin_dir / "__init__.py"
        if not init_file.is_file():
            errors.append(f"{plugin_id}: 缺少插件文件 {init_file}")
            continue
        actual = source_version(init_file)
        if actual != version:
            errors.append(f"{plugin_id}: package={version}, plugin_version={actual}")
    if errors:
        print("插件版本门禁失败：")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("插件版本门禁通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
