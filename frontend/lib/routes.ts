import {
  BarChart3,
  BookOpen,
  BriefcaseBusiness,
  Building2,
  ClipboardCheck,
  Cog,
  CreditCard,
  DatabaseZap,
  FileClock,
  FileDown,
  Gauge,
  Home,
  KeyRound,
  Layers3,
  ListTree,
  Network,
  PenLine,
  Settings,
  ShieldCheck,
  Sparkles,
  Users,
  WalletCards,
} from "lucide-react";

export const studioNav = [
  { label: "工作台", href: "/studio", icon: Home },
  { label: "项目", href: "/studio/projects", icon: BriefcaseBusiness },
  { label: "写作", href: "/studio/projects/demo-project/write", icon: PenLine },
  { label: "任务", href: "/studio/projects/demo-project/jobs", icon: ListTree },
  { label: "用量 / 套餐", href: "/studio/usage", icon: WalletCards },
  { label: "账号", href: "/studio/account", icon: Users },
];

export const projectNav = [
  { label: "项目总览", href: "/studio/projects/demo-project", icon: Gauge },
  { label: "故事圣经", href: "/studio/projects/demo-project/bible", icon: BookOpen },
  { label: "人物设定", href: "/studio/projects/demo-project/characters", icon: Network },
  { label: "世界观", href: "/studio/projects/demo-project/world", icon: DatabaseZap },
  { label: "大纲", href: "/studio/projects/demo-project/outline", icon: Layers3 },
  { label: "写作工作台", href: "/studio/projects/demo-project/write", icon: PenLine },
  { label: "生成任务", href: "/studio/projects/demo-project/jobs", icon: Sparkles },
  { label: "版本 / 审稿", href: "/studio/projects/demo-project/versions", icon: FileClock },
  { label: "导出", href: "/studio/projects/demo-project/export", icon: FileDown },
];

export const adminNav = [
  { label: "总览", href: "/admin", icon: BarChart3 },
  { label: "用户管理", href: "/admin/users", icon: Users },
  { label: "组织管理", href: "/admin/organizations", icon: Building2 },
  { label: "套餐管理", href: "/admin/plans", icon: CreditCard },
  { label: "额度管理", href: "/admin/quotas", icon: Gauge },
  { label: "生成任务", href: "/admin/generation-jobs", icon: ListTree },
  { label: "模型调用", href: "/admin/model-calls", icon: DatabaseZap },
  { label: "内容审核", href: "/admin/content-review", icon: ClipboardCheck },
  { label: "系统设置", href: "/admin/settings", icon: Cog },
  { label: "审计日志", href: "/admin/audit-logs", icon: ShieldCheck },
];

export const topQuickLinks = [
  { label: "新建项目", href: "/studio/projects/new", icon: Sparkles },
  { label: "账单套餐", href: "/studio/billing", icon: CreditCard },
  { label: "组织设置", href: "/studio/account", icon: Settings },
  { label: "Admin", href: "/admin", icon: KeyRound },
];
