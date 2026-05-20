/**
 * Markdown ↔ Tiptap / 纯文本互转。
 *
 * draft_versions.content 后端存的字符串可能是两种格式（由 content_format 标识）：
 * - "text"     —— 历史纯文本数据，按段落（`\n\n`）切分
 * - "markdown" —— Markdown 字符串（AI 输出 / 编辑器保存）
 *
 * 本模块提供：
 * - markdownToHtml(md)       —— 喂给 Tiptap 的 editor.commands.setContent(html)
 * - editorToMarkdown(editor) —— 从当前 Tiptap doc 反向序列化为 markdown
 * - textToHtml(text)         —— 旧 plain text 渲染（不解析任何 markdown 语法）
 * - toPlainText(content, fmt)—— diff / 列表预览前的统一 plain 化
 */
import type { Editor } from "@tiptap/react";
import { marked } from "marked";

import type { ContentFormat } from "@/lib/api";

// marked：把 markdown 转 HTML。Tiptap 的 StarterKit 能消化 marked 默认输出
// （heading/p/strong/em/blockquote/ul/ol/hr 等），保留行内 br 转换避免连续换行被吞。
marked.setOptions({ gfm: true, breaks: true });

const HTML_ESCAPE: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
};

function escapeHtml(s: string): string {
  return s.replace(/[&<>]/g, (c) => HTML_ESCAPE[c] ?? c);
}

/** 旧 'text' content 转 HTML：按双换行分段，单换行转 `<br/>`，全文 escape。 */
export function textToHtml(text: string): string {
  if (!text) return "";
  return text
    .split(/\n{2,}/)
    .map((para) => `<p>${escapeHtml(para).replace(/\n/g, "<br/>")}</p>`)
    .join("");
}

/** Markdown 字符串转 HTML，喂给 Tiptap 的 setContent。 */
export function markdownToHtml(md: string): string {
  if (!md) return "";
  // marked.parse 同步模式（async=false）返回 string
  const html = marked.parse(md, { async: false }) as string;
  return html.trim();
}

/**
 * 从 Tiptap editor 当前 doc 反向序列化为 markdown 字符串。
 *
 * 覆盖 StarterKit 提供的节点：paragraph / heading / bulletList / orderedList /
 * blockquote / horizontalRule / hardBreak / codeBlock；marks: bold / italic /
 * strike / code。其他未识别节点降级为 textContent，避免内容丢失。
 *
 * 不依赖 DOM（在 SSR 上调用也安全）。
 */
export function editorToMarkdown(editor: Editor | null): string {
  if (!editor) return "";
  const json = editor.getJSON();
  return docToMarkdown(json);
}

// ---------------------------------------------------------------------------
// 内部：ProseMirror JSON -> Markdown serializer
// ---------------------------------------------------------------------------

type PMNode = {
  type: string;
  attrs?: Record<string, unknown>;
  content?: PMNode[];
  marks?: { type: string; attrs?: Record<string, unknown> }[];
  text?: string;
};

function docToMarkdown(doc: PMNode): string {
  const blocks = (doc.content ?? []).map((node) => blockToMarkdown(node, "")).filter(Boolean);
  return blocks.join("\n\n").trim() + (blocks.length > 0 ? "\n" : "");
}

function blockToMarkdown(node: PMNode, listPrefix: string): string {
  switch (node.type) {
    case "paragraph":
      return listPrefix + inlineToMarkdown(node.content ?? []);
    case "heading": {
      const level = Math.min(Math.max(Number(node.attrs?.level ?? 1), 1), 6);
      return `${"#".repeat(level)} ${inlineToMarkdown(node.content ?? [])}`;
    }
    case "blockquote": {
      const inner = (node.content ?? [])
        .map((child) => blockToMarkdown(child, ""))
        .join("\n\n");
      return inner
        .split("\n")
        .map((line) => `> ${line}`)
        .join("\n");
    }
    case "bulletList":
      return listItemsToMarkdown(node, "- ", listPrefix);
    case "orderedList":
      return listItemsToMarkdown(node, "1. ", listPrefix);
    case "codeBlock": {
      const lang = (node.attrs?.language as string) || "";
      const code = (node.content ?? []).map((c) => c.text ?? "").join("");
      return "```" + lang + "\n" + code + "\n```";
    }
    case "horizontalRule":
      return "---";
    case "hardBreak":
      return "";
    default:
      // 未识别块：递归收集纯文本，避免静默丢失
      if (node.content) {
        return (node.content ?? [])
          .map((child) => blockToMarkdown(child, listPrefix))
          .filter(Boolean)
          .join("\n\n");
      }
      return node.text ?? "";
  }
}

function listItemsToMarkdown(listNode: PMNode, marker: string, parentPrefix: string): string {
  const items = listNode.content ?? [];
  return items
    .map((item) => {
      const inner = (item.content ?? [])
        .map((child, idx) => {
          const prefix = idx === 0 ? parentPrefix + marker : parentPrefix + "  ";
          return blockToMarkdown(child, prefix);
        })
        .join("\n");
      return inner;
    })
    .join("\n");
}

function inlineToMarkdown(nodes: PMNode[]): string {
  return nodes
    .map((node) => {
      if (node.type === "hardBreak") return "  \n";
      if (node.type !== "text") return inlineToMarkdown(node.content ?? []);
      let text = node.text ?? "";
      const marks = node.marks ?? [];
      // 应用顺序：code → strike → italic → bold（外层 mark 包内层）
      const has = (name: string) => marks.some((m) => m.type === name);
      if (has("code")) text = "`" + text + "`";
      if (has("strike")) text = `~~${text}~~`;
      if (has("italic") || has("em")) text = `*${text}*`;
      if (has("bold") || has("strong")) text = `**${text}**`;
      return text;
    })
    .join("");
}

// ---------------------------------------------------------------------------
// plain 提取：给 DiffView / 列表预览用
// ---------------------------------------------------------------------------

/**
 * 把任意 content 转为纯文本，用于 diff 对比与列表预览。
 * markdown 模式下用 marked → HTML → 简单 strip tags；text 模式直接返回。
 */
export function toPlainText(content: string, format: ContentFormat): string {
  if (!content) return "";
  if (format === "text") return content;
  // markdown：渲染为 HTML 后用 regex 剥标签
  const html = markdownToHtml(content);
  return html
    .replace(/<br\s*\/?>/g, "\n")
    .replace(/<\/(p|h[1-6]|li|blockquote)>/g, "\n")
    .replace(/<li[^>]*>/g, "• ")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
