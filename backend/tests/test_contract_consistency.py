"""契约 lint 测试。

扫描 backend/app/ 中所有 Python 文件，验证以下契约字面量都已在
backend/app/contracts.py 集合中登记：

- generation_jobs.job_type
- generation_jobs.status
- projects.status
- 业务异常的 code/message（AppError 子类的第一个位置参数）

新增任何契约级值必须先更新 app/contracts.py 与 docs/api_contract_v1.md，
否则本测试会失败，给出 file:line 与未知字面量。

测试用正则而非 AST，足够覆盖现有代码模式：
- ``job_type="xxx"`` / ``project.status = "xxx"`` 等关键字赋值
- ``mark_job_status(job_id, "xxx", ...)`` 的位置参数
- ``raise NotFoundError("xxx")`` 等业务异常的位置参数
"""
from __future__ import annotations

import re
from pathlib import Path

from app.contracts import (
    ERROR_CODES,
    JOB_STATUSES,
    JOB_TYPES,
    PROJECT_STATUSES,
)
from app.core import exceptions as _exc_module

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

# 不应被 lint 的文件：
# - contracts.py 本身（定义集合时会出现所有字面量，会自我命中）
# - alembic 迁移目录（迁移文件包含旧值字面量是合规的）
_EXCLUDED_RELPATHS = {
    "contracts.py",
}


def _iter_app_files() -> list[Path]:
    files: list[Path] = []
    for path in APP_ROOT.rglob("*.py"):
        rel = path.relative_to(APP_ROOT).as_posix()
        if rel in _EXCLUDED_RELPATHS:
            continue
        files.append(path)
    return files


def _scan(pattern: str) -> list[tuple[Path, int, str]]:
    rx = re.compile(pattern)
    hits: list[tuple[Path, int, str]] = []
    for path in _iter_app_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in rx.finditer(line):
                hits.append((path, lineno, match.group(1)))
    return hits


def _format(unknown: list[tuple[Path, int, str]]) -> str:
    return "\n".join(
        f"  {p.relative_to(APP_ROOT.parent)}:{ln} → {value!r}"
        for p, ln, value in unknown
    )


def _all_app_error_subclasses() -> set[str]:
    """递归收集 AppError 的所有后代类名。"""
    found: set[str] = set()
    stack = [_exc_module.AppError]
    while stack:
        cls = stack.pop()
        found.add(cls.__name__)
        stack.extend(cls.__subclasses__())
    return found


def test_job_types_registered_in_contracts() -> None:
    """所有 ``job_type="..."`` 字面量必须出现在 contracts.JOB_TYPES。"""
    hits = _scan(r'\bjob_type\s*=\s*["\']([a-z_][a-z0-9_]*)["\']')
    unknown = [h for h in hits if h[2] not in JOB_TYPES]
    assert not unknown, (
        "未登记的 job_type 字面量。请同步更新 app/contracts.py 与 "
        "docs/api_contract_v1.md §4.1：\n" + _format(unknown)
    )


def test_project_statuses_registered_in_contracts() -> None:
    """所有 ``project.status = "..."`` 字面量必须出现在 contracts.PROJECT_STATUSES。"""
    hits = _scan(r'project\.status\s*=\s*["\']([a-z_][a-z0-9_]*)["\']')
    unknown = [h for h in hits if h[2] not in PROJECT_STATUSES]
    assert not unknown, (
        "未登记的 project.status 字面量。请同步更新 app/contracts.py 与 "
        "docs/api_contract_v1.md §4.3：\n" + _format(unknown)
    )


def test_job_statuses_registered_in_contracts() -> None:
    """job.status / mark_job_status / job_row.status 的状态字面量必须登记。"""
    patterns = [
        r'\bjob\.status\s*=\s*["\']([a-z_][a-z0-9_]*)["\']',
        r'\bjob_row\.status\s*=\s*["\']([a-z_][a-z0-9_]*)["\']',
        r'mark_job_status\(\s*[^,()]+,\s*["\']([a-z_][a-z0-9_]*)["\']',
    ]
    hits: list[tuple[Path, int, str]] = []
    for pat in patterns:
        hits.extend(_scan(pat))
    unknown = [h for h in hits if h[2] not in JOB_STATUSES]
    assert not unknown, (
        "未登记的 generation_jobs.status 字面量。请同步更新 "
        "app/contracts.py 与 docs/api_contract_v1.md §4.2：\n" + _format(unknown)
    )


def test_business_exception_messages_registered_in_contracts() -> None:
    """所有业务异常（AppError 子类）的第一位置参数必须在 ERROR_CODES。

    该项目约定 raise NotFoundError("project_not_found") 等用法里第一参数同时
    充当 message 与 code（即使 AppError.__init__ 把它存到 message，前端读取
    时常用 message 做分支判断；契约层面统一登记可避免漂移）。
    """
    subclasses = _all_app_error_subclasses()
    # 转义类名拼成 alternation，匹配 raise <SubclassName>("...")
    alt = "|".join(re.escape(name) for name in subclasses)
    pattern = rf'raise\s+(?:{alt})\(\s*["\']([a-z_][a-z0-9_]*)["\']'
    hits = _scan(pattern)
    unknown = [h for h in hits if h[2] not in ERROR_CODES]
    assert not unknown, (
        "未登记的业务异常 code/message 字面量。请同步更新 "
        "app/contracts.py 与 docs/api_contract_v1.md §4.4：\n" + _format(unknown)
    )


def test_contracts_module_has_all_collections() -> None:
    """守护性检查：contracts 模块导出的集合非空，避免被无意清空。"""
    assert JOB_TYPES, "JOB_TYPES 不能为空"
    assert JOB_STATUSES, "JOB_STATUSES 不能为空"
    assert PROJECT_STATUSES, "PROJECT_STATUSES 不能为空"
    assert ERROR_CODES, "ERROR_CODES 不能为空"
