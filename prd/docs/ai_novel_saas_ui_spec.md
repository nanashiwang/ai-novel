# AI 小说自动生产 SaaS 平台 UI / 产品工作台规格文档

**文档版本**：v1.0  
**适配架构文档**：`ai_novel_saas_final_architecture.md`  
**目标用途**：交给 Codex / 工程团队实现前端 UI、页面结构、组件体系、权限展示、任务状态流和管理后台。  
**推荐前端技术栈**：Next.js App Router + React + TypeScript + Tailwind CSS + shadcn/ui + TanStack Query + Zustand + Tiptap。

---

## 1. UI 总目标

本 UI 不是简单的 AI 写作页面，而是一个面向商业化运营的 **AI 小说自动生产 SaaS 平台前端**。

前端需要同时服务两类用户：

```text
1. 普通用户 / 付费用户：使用 Web Studio 创建小说、生成内容、审稿、重写、导出。
2. 平台管理员 / 运营人员：使用 Admin Console 管理用户、组织、套餐、额度、任务、日志、审核。
```

前端必须与最终架构中的以下模块强绑定：

```text
Auth Service
Organization Service
RBAC Permission Service
Plan / Entitlement Service
Quota / Usage Service
Novel Generation Core
Workflow / Generation Job Service
Model Gateway Logs
Admin Service
Billing Service
```

---

## 2. 产品信息架构

整体前端拆成 5 个区域：

```text
1. Public Site：官网、价格页、登录注册入口。
2. Auth：注册、登录、找回密码。
3. Web Studio：用户端小说生产工作台。
4. Billing / Account：套餐、额度、账单、组织设置。
5. Admin Console：平台管理后台。
```

推荐 Next.js App Router 路由结构：

```text
frontend/
├── app/
│   ├── (public)/
│   │   ├── page.tsx                         # 官网首页
│   │   ├── pricing/page.tsx                 # 价格页
│   │   └── terms/page.tsx                   # 协议/条款
│   │
│   ├── (auth)/
│   │   ├── login/page.tsx
│   │   ├── register/page.tsx
│   │   ├── forgot-password/page.tsx
│   │   └── onboarding/page.tsx
│   │
│   ├── studio/
│   │   ├── layout.tsx                       # 用户工作台布局
│   │   ├── page.tsx                         # 用户首页 / 项目列表
│   │   ├── projects/new/page.tsx            # 创建小说项目
│   │   ├── projects/[projectId]/page.tsx    # 项目总览
│   │   ├── projects/[projectId]/bible/page.tsx
│   │   ├── projects/[projectId]/characters/page.tsx
│   │   ├── projects/[projectId]/world/page.tsx
│   │   ├── projects/[projectId]/outline/page.tsx
│   │   ├── projects/[projectId]/write/page.tsx
│   │   ├── projects/[projectId]/memory/page.tsx
│   │   ├── projects/[projectId]/issues/page.tsx
│   │   ├── projects/[projectId]/jobs/page.tsx
│   │   ├── projects/[projectId]/exports/page.tsx
│   │   └── settings/
│   │       ├── organization/page.tsx
│   │       ├── members/page.tsx
│   │       ├── billing/page.tsx
│   │       ├── usage/page.tsx
│   │       └── api-keys/page.tsx
│   │
│   ├── admin/
│   │   ├── layout.tsx                       # 管理后台布局
│   │   ├── page.tsx                         # 管理后台总览
│   │   ├── users/page.tsx
│   │   ├── users/[userId]/page.tsx
│   │   ├── organizations/page.tsx
│   │   ├── organizations/[organizationId]/page.tsx
│   │   ├── plans/page.tsx
│   │   ├── subscriptions/page.tsx
│   │   ├── quotas/page.tsx
│   │   ├── jobs/page.tsx
│   │   ├── model-calls/page.tsx
│   │   ├── content-review/page.tsx
│   │   ├── audit-logs/page.tsx
│   │   └── system/page.tsx
│   │
│   └── api-health/page.tsx                  # 可选：开发期健康检查
│
├── components/
├── features/
├── lib/
├── hooks/
├── stores/
└── types/
```

---

## 3. 角色与导航规则

UI 必须根据 `role + entitlement + organization status` 动态展示。

### 3.1 用户身份

```text
anonymous：未登录用户
user：普通登录用户
organization_owner：组织所有者
organization_member：组织成员
platform_admin：平台管理员
super_admin：超级管理员
```

### 3.2 用户端导航

Web Studio 左侧导航：

```text
工作台首页
小说项目
用量与额度
账单与套餐
组织设置
成员管理
API Keys（Pro/Team/Enterprise 可见）
```

项目内导航：

```text
项目总览
故事圣经
人物设定
世界观
大纲
写作工作台
长期记忆
审稿问题
生成任务
导出
项目设置
```

### 3.3 管理后台导航

Admin Console 左侧导航：

```text
总览
用户管理
组织管理
套餐管理
订阅管理
额度管理
生成任务
模型调用日志
内容审核
审计日志
系统设置
```

### 3.4 权限展示原则

前端只负责体验层面的隐藏、禁用和提示；后端仍必须强制校验。

```text
1. 没有角色权限：隐藏入口或显示“无权限”。
2. 套餐不支持：显示升级 CTA。
3. 额度不足：显示额度不足提示和升级/充值入口。
4. 组织被冻结：所有生成按钮禁用。
5. 任务运行中且达到并发上限：生成按钮禁用，提示等待。
```

---

## 4. 视觉与交互基调

### 4.1 设计定位

产品应该有“专业写作工作台 + SaaS 控制台”的感觉，不要做成聊天软件。

关键词：

```text
专业
稳定
可控
长任务可视化
创作沉浸感
管理后台清晰
```

### 4.2 主题

推荐默认浅色主题，写作工作台支持深色沉浸模式。

```text
Default Theme：浅色 SaaS 控制台
Writing Focus Mode：深色/极简写作模式
Admin Theme：高信息密度后台控制台
```

### 4.3 设计 Token

```text
主色：indigo / violet 系列
成功：green
警告：amber
错误：red
中性：slate
字体：系统默认中文字体 + Inter
圆角：8px / 12px
布局宽度：全屏控制台式布局
```

### 4.4 状态色语义

```text
planned：灰色
running / drafting：蓝色
waiting：琥珀色
completed：绿色
failed：红色
cancelled：灰色
needs_rewrite：橙色
finalized：绿色
```

---

## 5. Public Site 页面

### 5.1 官网首页 `/`

目标：介绍平台价值，引导注册。

模块：

```text
Hero：AI 自动写小说平台
核心 CTA：开始创作 / 查看价格
功能展示：自动大纲、自动写作、自动审稿、自动重写、长期记忆、导出成书
工作流展示：题材 → 故事圣经 → 大纲 → 场景 → 正文 → 审稿 → 导出
套餐入口
FAQ
页脚
```

Hero 文案建议：

```text
输入一个故事创意，生成可持续迭代的完整小说。
从故事圣经、大纲、章节、场景到正文、审稿和重写，全部由 AI 工作流自动完成。
```

### 5.2 价格页 `/pricing`

展示 Free / Pro / Team / Enterprise。

卡片字段：

```text
套餐名
价格
适用人群
每月生成字数
项目数
并发任务数
自动审稿
自动重写
导出格式
团队成员数
CTA
```

交互：

```text
未登录点击购买 → 跳转注册
已登录点击购买 → checkout / billing page
套餐当前已拥有 → 显示 Current Plan
```

---

## 6. Auth 与 Onboarding

### 6.1 登录页 `/login`

字段：

```text
邮箱
密码
记住登录
忘记密码
登录按钮
注册链接
```

登录成功后：

```text
如果用户没有 organization → /onboarding
否则 → /studio
```

### 6.2 注册页 `/register`

字段：

```text
邮箱
密码
确认密码
昵称
同意条款
注册按钮
```

注册成功后：

```text
创建 user
创建 personal organization
创建 organization_member owner
默认 Free 套餐
初始化 quota_balances
跳转 onboarding
```

### 6.3 Onboarding `/onboarding`

目标：快速建立第一个小说项目。

步骤：

```text
Step 1：选择使用目的
- 个人创作
- 工作室生产
- 内容团队
- 测试体验

Step 2：选择常用题材
- 玄幻
- 都市
- 悬疑
- 科幻
- 言情
- 历史
- 自定义

Step 3：创建第一个项目
- 项目标题
- 一句话创意
- 目标章节数
- 文风
```

完成后跳转：

```text
/studio/projects/[projectId]
```

---

## 7. Web Studio 总览

### 7.1 工作台首页 `/studio`

页面目标：展示当前组织的创作概况。

模块：

```text
顶部：组织切换器、当前套餐、额度进度、用户菜单
主区域：项目列表、创建项目按钮
数据卡片：项目数、生成字数、运行中任务、剩余额度
最近任务：generation_jobs 列表
最近编辑：最近打开项目/章节
升级提示：Free 用户可见
```

项目卡片字段：

```text
小说标题
类型
状态
章节进度
总字数
最近生成时间
当前任务状态
操作：打开 / 继续生成 / 导出
```

状态示例：

```text
未生成故事圣经
故事圣经已完成
大纲已完成
正在写第 3 章
等待审稿
已完成
```

---

## 8. 创建小说项目

### 8.1 路由

```text
/studio/projects/new
```

### 8.2 创建向导

推荐 4 步：

```text
Step 1：基础信息
Step 2：故事创意
Step 3：写作目标
Step 4：生成设置
```

### 8.3 表单字段

基础信息：

```text
title：小说标题
language：语言，默认 zh-CN
genre：题材
sub_genre：子类型
```

故事创意：

```text
premise：一句话创意
core_conflict：核心冲突，可选
main_character_seed：主角设定，可选
world_seed：世界观设定，可选
```

写作目标：

```text
target_word_count：目标字数
target_chapter_count：目标章节数
reader_profile：目标读者
narrative_pov：叙事视角
style：文风
```

生成设置：

```text
auto_generate_bible：创建后自动生成故事圣经
auto_generate_outline：故事圣经后自动生成大纲
content_constraints：禁忌内容 / 不希望出现的元素
```

### 8.4 创建后行为

```text
创建 project
检查项目数额度
保存 novel_specs 初始信息
可选启动 GenerateBibleWorkflow
跳转项目总览
```

---

## 9. 项目总览页

### 9.1 路由

```text
/studio/projects/[projectId]
```

### 9.2 页面模块

```text
项目状态 Header
生成进度 Timeline
关键数据卡片
下一步推荐动作
最近章节
最近任务
问题提醒
导出入口
```

### 9.3 推荐动作逻辑

```text
如果没有故事圣经 → 显示“生成故事圣经”
如果有故事圣经但无大纲 → 显示“生成全书大纲”
如果有大纲但无场景 → 显示“拆分章节场景”
如果有场景但无正文 → 显示“开始写第 1 章”
如果有审稿问题 → 显示“处理审稿问题”
如果已完成 → 显示“导出小说”
```

---

## 10. 故事圣经页面

### 10.1 路由

```text
/studio/projects/[projectId]/bible
```

### 10.2 页面目标

展示和编辑故事圣经，是自动生成的核心上下文。

### 10.3 模块

```text
故事前提 Premise
主题 Theme
核心卖点 Hook
世界观摘要 World Overview
主线冲突 Main Conflict
叙事规则 Narrative Rules
文风规则 Style Guide
禁忌内容 Constraints
生成/重生成按钮
版本历史
```

### 10.4 交互

```text
点击“生成故事圣经” → 启动 GenerateBibleWorkflow
点击“重生成” → 弹出确认，创建新版本
点击“保存编辑” → 保存用户修改，标记为 user_modified
```

### 10.5 特殊提示

故事圣经一旦用户手动修改，后续生成必须优先使用用户版本。

---

## 11. 人物设定页面

### 11.1 路由

```text
/studio/projects/[projectId]/characters
```

### 11.2 页面结构

```text
左侧：人物列表
右侧：人物详情表单
顶部：生成主要人物 / 新增人物 / 批量导入
```

### 11.3 人物字段

```text
name
role
age / gender 可选
description
personality
motivation
secret
arc
relationships
current_state
first_appearance_chapter
status
```

### 11.4 角色状态展示

人物卡必须显示当前状态：

```text
身体状态
情绪状态
已知信息
关系变化
最近出场章节
```

这是 Memory Engine 的可视化入口。

---

## 12. 世界观页面

### 12.1 路由

```text
/studio/projects/[projectId]/world
```

### 12.2 世界观条目类型

```text
location
organization
item
law
magic_system
technology
event
history
custom
```

### 12.3 页面结构

```text
左侧：类型筛选
中间：世界观条目表格/卡片
右侧：详情抽屉
顶部：生成世界观 / 新增条目
```

### 12.4 条目字段

```text
type
name
description
rules
related_characters
related_plot_threads
importance
```

---

## 13. 大纲页面

### 13.1 路由

```text
/studio/projects/[projectId]/outline
```

### 13.2 页面目标

管理全书结构、分卷、章节、冲突、转折、伏笔。

### 13.3 页面布局

```text
左侧：卷/章树
中间：章节大纲详情
右侧：伏笔、人物成长、冲突升级
```

### 13.4 章节字段

```text
chapter_index
title
summary
goal
conflict
ending_hook
characters
location
plot_threads
status
```

### 13.5 交互

```text
生成全书大纲
重新生成某一章大纲
插入章节
删除章节
调整顺序
锁定章节大纲
拆分章节为场景
```

### 13.6 锁定机制

用户可以锁定章节，锁定后自动重生成大纲时不得覆盖。

```text
locked_by_user = true
```

---

## 14. 写作工作台

### 14.1 路由

```text
/studio/projects/[projectId]/write
```

这是用户端最核心页面。

### 14.2 总体布局

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Top Bar: 项目名 / 状态 / 当前套餐 / 额度 / 生成按钮 / 导出 / 设置          │
├───────────────┬───────────────────────────────────────┬──────────────────┤
│ Chapter Tree  │ Editor                                │ Inspector        │
│ 章节/场景树     │ 正文编辑器                              │ 设定/记忆/审稿问题 │
│               │                                       │                  │
├───────────────┴───────────────────────────────────────┴──────────────────┤
│ Bottom Panel: 生成任务日志 / 模型调用日志 / 版本历史 / 审稿结果              │
└──────────────────────────────────────────────────────────────────────────┘
```

### 14.3 左侧 ChapterSceneTree

显示：

```text
卷
章节
场景
状态图标
字数
审稿问题数量
```

交互：

```text
点击章节 → 打开章节合并稿
点击场景 → 打开场景正文
右键章节 → 生成场景 / 写本章 / 审稿 / 重写 / 导出章节
右键场景 → 写场景 / 审稿 / 重写 / 查看版本
```

状态图标：

```text
planned：空心圆
writing：旋转图标
drafted：蓝色圆点
needs_rewrite：橙色警告
finalized：绿色对勾
failed：红色错误
```

### 14.4 中间 Editor

推荐使用 Tiptap 或 Markdown 编辑器。

编辑器功能：

```text
正文编辑
自动保存
字数统计
版本保存
只读/可编辑切换
Focus Mode
章节/场景标题展示
```

顶部工具条：

```text
保存
生成当前场景
审稿当前场景
重写当前场景
合并章节
查看版本
锁定正文
```

### 14.5 右侧 Inspector

Tabs：

```text
当前场景
人物
世界观
记忆
伏笔
审稿问题
生成设置
```

#### 当前场景 Tab

字段：

```text
时间
地点
出场人物
目标
冲突
情绪起点
情绪终点
信息揭示
结尾钩子
```

#### 人物 Tab

显示当前场景相关人物：

```text
人物卡摘要
当前状态
关系变化
最近出场记录
```

#### 世界观 Tab

显示召回的世界观条目：

```text
条目名称
类型
规则
相关性
```

#### 记忆 Tab

显示 Context Builder 召回内容：

```text
前文摘要
相关章节摘要
相关场景摘要
相关伏笔
相关时间线事件
```

#### 审稿问题 Tab

显示 continuity_issues：

```text
问题类型
严重程度
描述
建议修复
一键重写
标记已解决
```

### 14.6 底部 BottomPanel

Tabs：

```text
任务日志
模型调用
版本历史
审稿结果
用量记录
```

任务日志展示：

```text
generation_job 状态
timeline events
当前步骤
失败原因
重试按钮
取消按钮
```

模型调用展示：

```text
task_type
model
input_tokens
output_tokens
latency
status
查看 prompt
查看 response
```

版本历史展示：

```text
版本号
类型
创建时间
字数
来源：AI / 用户 / 重写
操作：查看 / 恢复 / 对比
```

---

## 15. 生成任务体验

### 15.1 生成按钮分级

不同页面提供不同按钮：

```text
生成故事圣经
生成全书大纲
拆分当前章节场景
写当前场景
写当前章节
生成前 3 章
一键生成整本小说
审稿当前章节
重写当前章节
全书审稿
导出小说
```

### 15.2 生成前确认弹窗

所有长任务启动前必须弹窗确认：

```text
任务名称
预计消耗额度
预计耗时提示
当前套餐
剩余额度
并发任务占用
确认启动
```

对于 Free 用户：

```text
如果超出权益 → 显示升级 CTA
```

### 15.3 任务进度组件 JobProgress

字段：

```text
job_id
job_type
status
current_step
total_steps
progress_percent
started_at
estimated_remaining_text
```

步骤显示示例：

```text
1. 检查权限
2. 预留额度
3. 生成故事圣经
4. 生成人物卡
5. 生成世界观
6. 生成章节大纲
7. 拆分场景
8. 写场景 1/4
9. 写场景 2/4
10. 合并章节
11. 更新记忆
12. 结算额度
```

### 15.4 任务失败处理

失败状态必须提供：

```text
失败原因
最后成功步骤
消耗额度
是否已释放预留额度
重试按钮
查看日志
联系客服/反馈
```

---

## 16. 长期记忆页面

### 16.1 路由

```text
/studio/projects/[projectId]/memory
```

### 16.2 页面目标

可视化 Memory Engine。

### 16.3 记忆类型

```text
chapter_summary
scene_summary
character_state
world_rule
foreshadowing
timeline_event
style_rule
```

### 16.4 页面结构

```text
顶部：记忆搜索框
左侧：类型筛选
中间：记忆列表
右侧：记忆详情
```

### 16.5 操作

```text
搜索记忆
按章节筛选
按人物筛选
手动新增记忆
编辑记忆
标记重要
删除/归档
重新生成章节摘要
```

---

## 17. 审稿问题页面

### 17.1 路由

```text
/studio/projects/[projectId]/issues
```

### 17.2 问题类型

```text
character_inconsistency
timeline_conflict
world_rule_conflict
plot_hole
foreshadowing_missing
style_drift
repetition
pacing_issue
```

### 17.3 页面结构

```text
筛选栏：严重程度 / 状态 / 章节 / 类型
问题列表
问题详情抽屉
一键重写入口
标记已解决
```

### 17.4 状态

```text
open
rewriting
resolved
ignored
```

---

## 18. 导出页面

### 18.1 路由

```text
/studio/projects/[projectId]/exports
```

### 18.2 导出格式

第一版：

```text
Markdown
TXT
```

后续：

```text
DOCX
EPUB
PDF
```

### 18.3 页面模块

```text
导出格式选择
导出范围：全书 / 指定章节
版本选择：最新稿 / final 稿
导出任务状态
历史导出文件
下载链接
```

---

## 19. Billing / Usage 页面

### 19.1 Billing 路由

```text
/studio/settings/billing
```

模块：

```text
当前套餐
套餐权益
升级/降级
订阅状态
账单历史
支付方式
取消订阅入口
```

### 19.2 Usage 路由

```text
/studio/settings/usage
```

模块：

```text
本月生成字数
本月审稿次数
本月重写次数
并发任务使用情况
用量趋势图
最近 usage_events
```

### 19.3 QuotaMeter 组件

显示：

```text
quota_key
limit_value
used_value
reserved_value
remaining_value
reset_at
```

QuotaMeter 必须在这些地方显示：

```text
Top Bar
Studio 首页
生成确认弹窗
Billing / Usage 页面
```

---

## 20. 组织设置与成员

### 20.1 Organization Settings

```text
/studio/settings/organization
```

字段：

```text
组织名称
组织头像
组织状态
默认语言
默认写作风格
删除组织入口
```

### 20.2 Members

```text
/studio/settings/members
```

表格字段：

```text
用户
邮箱
角色
状态
加入时间
操作
```

角色：

```text
owner
admin
editor
viewer
billing_manager
```

第一版可只实现：

```text
owner
member
```

---

## 21. Admin Console 总览

### 21.1 路由

```text
/admin
```

### 21.2 总览指标

```text
总用户数
活跃组织数
付费组织数
本月生成字数
运行中任务数
失败任务数
模型调用次数
平均任务耗时
高消耗组织
```

### 21.3 图表

```text
日新增用户
日生成字数
任务成功率
模型调用成本趋势
套餐分布
```

---

## 22. Admin 用户管理

### 22.1 路由

```text
/admin/users
/admin/users/[userId]
```

### 22.2 列表字段

```text
用户 ID
邮箱
昵称
状态
是否平台员工
所属组织数
注册时间
最近登录
操作
```

### 22.3 用户详情

Tabs：

```text
基本信息
所属组织
项目
用量
生成任务
审计日志
```

操作：

```text
封禁用户
恢复用户
重置密码
设为平台管理员
移除平台管理员
```

---

## 23. Admin 组织管理

### 23.1 路由

```text
/admin/organizations
/admin/organizations/[organizationId]
```

### 23.2 列表字段

```text
组织 ID
组织名称
Owner
套餐
状态
成员数
项目数
本月用量
创建时间
操作
```

### 23.3 组织详情 Tabs

```text
概览
成员
订阅
额度
项目
生成任务
模型调用
审计日志
```

### 23.4 管理操作

```text
切换套餐
手动赠送额度
冻结组织
恢复组织
取消运行中任务
查看项目内容
```

---

## 24. Admin 套餐管理

### 24.1 路由

```text
/admin/plans
```

### 24.2 列表字段

```text
套餐 Code
名称
价格
状态
权益数量
创建时间
```

### 24.3 套餐配置

可配置：

```text
max_projects
max_monthly_words
max_concurrent_jobs
full_novel_generation
advanced_audit
advanced_rewrite
epub_export
docx_export
team_members
api_access
priority_queue
```

### 24.4 注意

Plan 管理必须是配置化，不要把套餐限制写死在前端。

---

## 25. Admin 额度管理

### 25.1 路由

```text
/admin/quotas
```

### 25.2 功能

```text
按组织查询额度
查看 quota_balances
查看 quota_reservations
查看 usage_events
手动调整额度
释放异常预留额度
```

---

## 26. Admin 生成任务管理

### 26.1 路由

```text
/admin/jobs
```

### 26.2 列表字段

```text
job_id
organization
user
project
job_type
status
priority
plan_code
progress
reserved_quota
consumed_quota
started_at
finished_at
```

### 26.3 操作

```text
查看详情
取消任务
重试任务
查看 workflow 日志
查看 model_calls
查看 usage_events
```

---

## 27. Admin 模型调用日志

### 27.1 路由

```text
/admin/model-calls
```

### 27.2 列表字段

```text
id
organization
project
job_id
task_type
model
input_tokens
output_tokens
latency_ms
status
created_at
```

### 27.3 详情抽屉

显示：

```text
system_prompt
user_prompt
response_text
response_json
error_message
metadata
```

注意：生产环境需要根据权限控制 prompt/response 可见性。

---

## 28. Admin 内容审核

### 28.1 路由

```text
/admin/content-review
```

### 28.2 功能

```text
待审核项目
被举报内容
敏感内容标记
违规处理
人工审核记录
```

第一版可只做占位页，但路由要保留。

---

## 29. Admin 审计日志

### 29.1 路由

```text
/admin/audit-logs
```

### 29.2 字段

```text
actor_user_id
action
resource_type
resource_id
organization_id
ip_address
user_agent
metadata
created_at
```

### 29.3 需要记录的操作

```text
登录
套餐切换
额度调整
组织冻结/恢复
用户封禁/恢复
任务取消/重试
项目删除
权限变更
```

---

## 30. 核心组件清单

### 30.1 Layout 组件

```text
PublicLayout
AuthLayout
StudioLayout
ProjectLayout
AdminLayout
```

### 30.2 通用组件

```text
AppSidebar
TopBar
UserMenu
OrganizationSwitcher
PlanBadge
QuotaMeter
StatusBadge
PermissionGate
EntitlementGate
DataTable
SearchFilterBar
ConfirmDialog
EmptyState
ErrorState
LoadingState
```

### 30.3 小说业务组件

```text
ProjectCard
ProjectStatusTimeline
BibleEditor
CharacterList
CharacterDetailPanel
WorldItemList
OutlineTree
ChapterDetailForm
ChapterSceneTree
ScenePlanPanel
NovelEditor
ContextInspector
MemoryList
AuditIssueList
DraftVersionPanel
ExportPanel
```

### 30.4 生成任务组件

```text
GenerateActionButton
GenerationConfirmDialog
JobProgress
JobTimeline
JobLogPanel
ModelCallTable
ModelCallDrawer
UsageEventList
```

### 30.5 Admin 组件

```text
AdminMetricCard
UserTable
OrganizationTable
PlanFeatureEditor
QuotaAdjustmentDialog
JobAdminTable
AuditLogTable
ContentReviewQueue
```

---

## 31. 前端数据类型

建议建立：

```text
types/auth.ts
types/organization.ts
types/billing.ts
types/quota.ts
types/project.ts
types/novel.ts
types/generation.ts
types/admin.ts
```

核心 TypeScript 类型示例：

```ts
export type ProjectStatus =
  | 'created'
  | 'bible_generating'
  | 'bible_ready'
  | 'outline_generating'
  | 'outline_ready'
  | 'drafting'
  | 'auditing'
  | 'rewriting'
  | 'completed'
  | 'exported';

export type GenerationJobStatus =
  | 'queued'
  | 'running'
  | 'waiting'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface Project {
  id: string;
  organization_id: string;
  title: string;
  genre: string;
  target_word_count: number;
  target_chapter_count: number;
  status: ProjectStatus;
  total_word_count: number;
  created_at: string;
  updated_at: string;
}

export interface Chapter {
  id: string;
  project_id: string;
  chapter_index: number;
  title: string;
  summary?: string;
  goal?: string;
  conflict?: string;
  ending_hook?: string;
  status: string;
  word_count: number;
}

export interface Scene {
  id: string;
  project_id: string;
  chapter_id: string;
  scene_index: number;
  title?: string;
  time_marker?: string;
  location?: string;
  characters: string[];
  goal?: string;
  conflict?: string;
  status: string;
  word_count: number;
}

export interface QuotaBalance {
  quota_key: string;
  limit_value: number;
  used_value: number;
  reserved_value: number;
  reset_at: string;
}

export interface GenerationJob {
  id: string;
  organization_id: string;
  project_id?: string;
  job_type: string;
  status: GenerationJobStatus;
  priority: string;
  progress_percent: number;
  current_step?: string;
  error_message?: string;
  started_at?: string;
  finished_at?: string;
  created_at: string;
}
```

---

## 32. API 对接映射

前端 API Client 建议按 feature 拆分：

```text
lib/api/auth.ts
lib/api/organizations.ts
lib/api/billing.ts
lib/api/quotas.ts
lib/api/projects.ts
lib/api/novel.ts
lib/api/generation-jobs.ts
lib/api/admin.ts
```

核心接口：

```text
POST /auth/register
POST /auth/login
GET  /auth/me

GET  /organizations
GET  /organizations/{organization_id}
GET  /organizations/{organization_id}/members

GET  /billing/plans
GET  /billing/current-subscription
POST /billing/checkout-session
GET  /quotas
GET  /usage

POST /projects
GET  /projects
GET  /projects/{project_id}
PATCH /projects/{project_id}

POST /projects/{project_id}/bible/generate
GET  /projects/{project_id}/bible
POST /projects/{project_id}/outline/generate
GET  /projects/{project_id}/chapters
GET  /chapters/{chapter_id}/scenes
POST /chapters/{chapter_id}/scenes/generate
POST /scenes/{scene_id}/write
POST /scenes/{scene_id}/audit
POST /scenes/{scene_id}/rewrite

POST /projects/{project_id}/generate-first-chapter
POST /projects/{project_id}/generate-full-novel
GET  /generation-jobs/{job_id}
GET  /generation-jobs/{job_id}/events
POST /generation-jobs/{job_id}/cancel

POST /projects/{project_id}/export
GET  /exports/{export_id}
```

Admin 接口：

```text
GET /admin/users
GET /admin/users/{user_id}
PATCH /admin/users/{user_id}/status

GET /admin/organizations
GET /admin/organizations/{organization_id}
PATCH /admin/organizations/{organization_id}/plan
PATCH /admin/organizations/{organization_id}/quota

GET /admin/plans
POST /admin/plans
PATCH /admin/plans/{plan_id}

GET /admin/generation-jobs
POST /admin/generation-jobs/{job_id}/cancel
POST /admin/generation-jobs/{job_id}/retry

GET /admin/model-calls
GET /admin/audit-logs
```

---

## 33. 状态管理方案

### 33.1 Server State

使用 TanStack Query 管理：

```text
current user
organizations
projects
project detail
chapters
scenes
generation jobs
quotas
admin tables
```

### 33.2 Client State

使用 Zustand 管理：

```text
currentOrganizationId
studioSidebarCollapsed
selectedProjectId
selectedChapterId
selectedSceneId
editorFocusMode
rightInspectorTab
bottomPanelTab
adminSidebarCollapsed
```

### 33.3 实时状态

任务进度使用：

```text
优先 SSE：GET /generation-jobs/{job_id}/events
可选 WebSocket
降级轮询：每 3-5 秒刷新 job status
```

---

## 34. 权限与权益组件

### 34.1 PermissionGate

```tsx
<PermissionGate permission="novel:generate_full">
  <Button>一键生成整本小说</Button>
</PermissionGate>
```

### 34.2 EntitlementGate

```tsx
<EntitlementGate
  feature="full_novel_generation"
  fallback={<UpgradeCard feature="一键生成整本小说" />}
>
  <GenerateFullNovelButton />
</EntitlementGate>
```

### 34.3 QuotaGuard

```tsx
<QuotaGuard quotaKey="monthly_generated_words" estimatedAmount={8000}>
  <GenerateChapterButton />
</QuotaGuard>
```

注意：这些组件只控制 UI。后端必须再次校验。

---

## 35. Empty / Error / Loading 状态

### 35.1 项目为空

```text
你还没有创建小说项目。
创建第一个项目，让 AI 从故事圣经开始帮你自动写作。
CTA：创建小说项目
```

### 35.2 故事圣经为空

```text
这个项目还没有故事圣经。
故事圣经会作为后续大纲、章节、场景和正文生成的核心依据。
CTA：生成故事圣经
```

### 35.3 额度不足

```text
当前组织的生成额度不足。
你可以升级套餐、等待下个计费周期重置，或联系管理员调整额度。
CTA：查看套餐
```

### 35.4 权限不足

```text
你没有权限执行此操作。
请联系组织所有者或平台管理员。
```

### 35.5 任务失败

```text
生成任务失败。
最后成功步骤：{last_successful_step}
失败原因：{error_message}
操作：重试 / 查看日志 / 取消任务
```

---

## 36. Codex 前端实现任务拆分

建议让 Codex 按阶段实现，不要一次要求生成全部。

### 阶段 1：前端基础脚手架

目标：建立 Next.js + TypeScript + Tailwind + shadcn/ui 项目。

任务：

```text
1. 创建 frontend 项目结构。
2. 配置 Tailwind、shadcn/ui、lucide-react。
3. 建立 PublicLayout / AuthLayout / StudioLayout / AdminLayout。
4. 建立路由结构。
5. 建立 API Client 基础封装。
6. 建立类型文件。
7. 建立 mock 数据，便于页面先跑起来。
```

验收：

```text
npm run dev 可以启动。
Public / Login / Studio / Admin 路由可访问。
Sidebar 和 TopBar 正常显示。
```

### 阶段 2：Auth + Organization UI

任务：

```text
1. 登录页。
2. 注册页。
3. Onboarding 页。
4. current user provider。
5. organization switcher。
6. 权限/权益基础组件。
```

验收：

```text
可以通过 mock auth 登录。
登录后进入 /studio。
可以切换 organization。
```

### 阶段 3：Studio 首页 + 项目创建

任务：

```text
1. Studio dashboard。
2. 项目列表。
3. 项目创建向导。
4. ProjectCard。
5. QuotaMeter。
```

验收：

```text
可以创建 mock project。
项目卡片显示状态、字数、任务。
```

### 阶段 4：项目内页面

任务：

```text
1. 项目总览。
2. 故事圣经页面。
3. 人物设定页面。
4. 世界观页面。
5. 大纲页面。
```

验收：

```text
项目内导航完整。
各页面能展示 mock 数据。
```

### 阶段 5：写作工作台

任务：

```text
1. ChapterSceneTree。
2. NovelEditor。
3. ContextInspector。
4. BottomPanel。
5. GenerationConfirmDialog。
6. JobProgress。
7. DraftVersionPanel。
```

验收：

```text
写作工作台三栏布局完成。
点击章节/场景可切换内容。
可以打开生成确认弹窗。
可以显示任务进度。
```

### 阶段 6：Admin Console

任务：

```text
1. Admin dashboard。
2. 用户管理。
3. 组织管理。
4. 套餐管理。
5. 额度管理。
6. 任务管理。
7. 模型调用日志。
8. 审计日志。
```

验收：

```text
Admin 页面完整。
表格、筛选、详情抽屉、操作按钮可用。
```

### 阶段 7：接真实后端 API

任务：

```text
1. 替换 mock API。
2. 接 JWT。
3. 接 TanStack Query。
4. 接 SSE 任务进度。
5. 接权限/权益/额度。
6. 接真实生成任务 API。
```

验收：

```text
真实登录。
真实项目创建。
真实生成任务启动。
真实任务进度更新。
真实额度展示。
```

---

## 37. 第一版 UI MVP 范围

第一版必须实现：

```text
Public 首页
价格页
登录
注册
Onboarding
Studio 首页
项目创建
项目总览
故事圣经
大纲
写作工作台
生成任务进度
用量与额度
导出页
Admin 总览
Admin 用户管理
Admin 组织管理
Admin 套餐/额度管理
Admin 任务管理
Admin 模型调用日志
```

第一版可以先不做：

```text
复杂团队协作
复杂发票页面
模板市场
内容社区
移动端专项适配
高级封面生成
复杂 API Key 管理
```

---

## 38. UI 验收标准

### 38.1 用户端验收

```text
1. 用户能注册登录。
2. 用户能看到当前组织、套餐和额度。
3. 用户能创建小说项目。
4. 用户能进入项目总览。
5. 用户能生成故事圣经。
6. 用户能生成大纲。
7. 用户能在写作工作台查看章节/场景/正文。
8. 用户能启动生成任务并看到进度。
9. 用户能看到模型调用和任务日志。
10. 用户能导出 Markdown/TXT。
```

### 38.2 管理端验收

```text
1. 管理员能进入 Admin Console。
2. 管理员能查看用户列表。
3. 管理员能查看组织列表。
4. 管理员能给组织切换套餐。
5. 管理员能调整组织额度。
6. 管理员能查看生成任务。
7. 管理员能取消/重试任务。
8. 管理员能查看模型调用日志。
9. 管理员能查看审计日志。
```

### 38.3 权限与套餐验收

```text
1. Free 用户不能一键生成整本小说。
2. 额度不足时生成按钮禁用。
3. 组织被冻结时不能启动生成。
4. 普通用户不能进入 /admin。
5. 没有 billing 权限的成员不能修改套餐。
```

---

## 39. 给 Codex 的实现约束

Codex 实现时必须遵守：

```text
1. 不要把 UI 做成聊天软件。
2. 不要绕过 organization_id 租户边界。
3. 不要把套餐权益写死在组件里，必须通过 entitlements/plan_features 驱动。
4. 不要把生成任务当普通同步请求，UI 必须展示 job 状态。
5. 不要在前端硬编码管理员账号。
6. 不要把 prompt/response 长文本直接全部塞进列表页，使用详情抽屉。
7. 所有长任务操作必须有确认弹窗。
8. 所有破坏性操作必须有二次确认。
9. 写作工作台必须支持章节/场景/版本三层结构。
10. 管理后台必须和用户端分 layout。
```

---

## 40. 推荐首个 Codex 指令

把架构文档和本文档放入仓库后，给 Codex 的第一条指令建议如下：

```text
请阅读 docs/ai_novel_saas_final_architecture.md 和 docs/ai_novel_saas_ui_spec.md。

任务：先实现前端基础脚手架和 UI 路由，不接真实后端。

要求：
1. 使用 Next.js App Router、TypeScript、Tailwind CSS、shadcn/ui。
2. 建立 PublicLayout、AuthLayout、StudioLayout、ProjectLayout、AdminLayout。
3. 建立本文档中定义的路由结构。
4. 使用 mock 数据实现 Studio 首页、项目创建页、项目总览页、写作工作台、Admin 总览页。
5. 建立核心组件：TopBar、Sidebar、OrganizationSwitcher、PlanBadge、QuotaMeter、ProjectCard、ChapterSceneTree、NovelEditor、ContextInspector、JobProgress、DataTable。
6. 代码需要有清晰的 features/ 分层。
7. 不要实现真实支付，不要接真实 GPT，不要绕过权限/权益/额度的 UI 逻辑。
8. 完成后确保 npm run dev、npm run lint、npm run typecheck 通过。
```

---

## 41. 总结

最终 UI 的核心不是“一个生成按钮”，而是：

```text
SaaS 控制台
+ 小说项目管理
+ 故事资产管理
+ 写作流水线可视化
+ 长任务进度管理
+ 额度/套餐控制
+ 管理后台
```

用户端重点是：

```text
创建项目 → 生成故事圣经 → 生成大纲 → 拆场景 → 写正文 → 审稿 → 重写 → 导出
```

管理端重点是：

```text
用户 → 组织 → 套餐 → 额度 → 任务 → 日志 → 审核 → 风控
```

这份 UI 文档应与最终架构文档一起交给 Codex，作为前端实现的主要依据。
