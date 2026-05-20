"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import type { Chapter, DraftVersion, Scene } from "@/lib/api";
import { versionsApi } from "@/lib/api";
import { ApiError } from "@/lib/http";
import { useScopedKey } from "@/lib/use-scoped-key";

export type UseSceneVersionsArgs = {
  projectId: string;
  activeChapter?: Chapter;
  activeScene?: Scene;
};

/**
 * 写作工作台：当前 scene 的 draft_versions 管理。
 *
 * 负责：
 * - versions query（按 created_at desc，[0] = latestDraft）
 * - 当前显示版本 / 对比版本的本�� state
 * - save / autosave / delete 三个 mutation
 *
 * 不负责：write/audit/rewrite 等会写入 versions 的外部 mutation，
 * 它们仍由调用方在自己的 onSuccess 里 invalidate versionsKey（已导出）。
 */
export function useSceneVersions({ projectId, activeChapter, activeScene }: UseSceneVersionsArgs) {
  const queryClient = useQueryClient();
  const versionsKey = useScopedKey("project", projectId, "versions", activeScene?.id);

  const { data: versions = [] } = useQuery({
    queryKey: versionsKey,
    queryFn: () => versionsApi.list(projectId, { scene_id: activeScene?.id }),
    enabled: !!activeScene,
  });
  const latestDraft: DraftVersion | undefined = versions[0];

  // 显示的版本：默认最新；如果切换到了某历史版本，记录其 id。当 scene 改变
  // 或 versions 列表变化导致该 id 失效时，displayedVersion 自动 fallback
  // 到 latestDraft，无需用 useEffect 重置 displayedVersionId。
  const [displayedVersionId, setDisplayedVersionId] = useState<string | null>(null);
  const displayedVersion =
    (displayedVersionId
      ? versions.find((v) => v.id === displayedVersionId)
      : undefined) ?? latestDraft;
  const isShowingLatest =
    !displayedVersion || displayedVersion.id === latestDraft?.id;

  // 对比模式：与当前 displayedVersion 对比的另一个版本 id。null = 普通编辑模式。
  const [compareWithId, setCompareWithId] = useState<string | null>(null);
  const compareWithVersion = compareWithId
    ? versions.find((v) => v.id === compareWithId)
    : undefined;
  const isComparing = !!compareWithVersion;

  const saveVersion = useMutation({
    mutationFn: (content: string) => {
      if (!activeScene || !activeChapter) {
        return Promise.reject(new Error("no_active_scene"));
      }
      return versionsApi.create(projectId, {
        chapter_id: activeChapter.id,
        scene_id: activeScene.id,
        version_type: "user",
        content,
        word_count: content.length,
        status: "draft",
        parent_version_id: displayedVersion?.id ?? null,
      });
    },
    onSuccess: () => {
      toast.success("已保存为新版本");
      queryClient.invalidateQueries({ queryKey: versionsKey });
      setDisplayedVersionId(null);
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "保存失败");
    },
  });

  const autoSave = useMutation({
    // autosave 默默成功；与手动保存的差别：不弹 toast、version_type=autosave。
    mutationFn: (content: string) => {
      if (!activeScene || !activeChapter) {
        return Promise.reject(new Error("no_active_scene"));
      }
      return versionsApi.create(projectId, {
        chapter_id: activeChapter.id,
        scene_id: activeScene.id,
        version_type: "autosave",
        content,
        word_count: content.length,
        status: "draft",
        parent_version_id: displayedVersion?.id ?? null,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: versionsKey });
      setDisplayedVersionId(null);
    },
    onError: (e: unknown) => {
      // autosave 失败不打断用户，仅 console.warn
      console.warn("autosave failed", e);
    },
  });

  const deleteVersion = useMutation({
    mutationFn: (versionId: string) => versionsApi.delete(projectId, versionId),
    onSuccess: (_, versionId) => {
      toast.success("已删除该版本");
      // 若当前预览的就是被删的版本，自动回到最新版
      if (displayedVersionId === versionId) {
        setDisplayedVersionId(null);
      }
      queryClient.invalidateQueries({ queryKey: versionsKey });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "删除失败");
    },
  });

  return {
    versionsKey,
    versions,
    latestDraft,
    displayedVersion,
    displayedVersionId,
    setDisplayedVersionId,
    isShowingLatest,
    compareWithVersion,
    compareWithId,
    setCompareWithId,
    isComparing,
    saveVersion,
    autoSave,
    deleteVersion,
  };
}
