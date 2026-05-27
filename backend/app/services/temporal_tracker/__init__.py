"""时间线追踪服务（Sprint 17-B 全局时间线）。

每场写完后由 LLM 反推 3 个结构化时间字段写回 scenes 表：
- in_story_day_offset：距开篇第 0 天的偏移
- time_of_day：morning / noon / afternoon / evening / night / dawn / dusk
- duration_minutes：本场在故事时间内持续的分钟数

与 character/world/plot extract 模式对齐（同步触发、失败不抛、写库与主流程合 session）。
直接写 scenes 表（不走 revision 链）——这些是结构化客观事实而非创作字段，
不需要 user_edit / pending 审核流程。
"""
from __future__ import annotations
