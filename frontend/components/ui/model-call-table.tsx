import type { ModelCall } from "@/types";

import { formatDateTime, msToTime } from "@/lib/format";
import { StatusBadge } from "./badge";
import { DataTable } from "./data-table";

/**
 * 模型调用日志表格。
 *
 * 调用方传 rows，由 useQuery + adminApi.modelCalls 提供。
 * 默认空数组，避免 undefined 时崩溃。
 */
export function ModelCallTable({ rows = [] }: { rows?: ModelCall[] }) {
  return (
    <DataTable
      rows={rows}
      columns={[
        {
          key: "task",
          header: "task_type",
          render: (row) => (
            <span className="font-semibold text-slate-950">{row.taskType}</span>
          ),
        },
        { key: "model", header: "model", render: (row) => row.model },
        {
          key: "tokens",
          header: "input / output",
          render: (row) =>
            `${row.inputTokens.toLocaleString()} / ${row.outputTokens.toLocaleString()}`,
        },
        { key: "latency", header: "latency", render: (row) => msToTime(row.latencyMs) },
        {
          key: "status",
          header: "status",
          render: (row) => (
            <StatusBadge status={row.status === "success" ? "succeeded" : "failed"} />
          ),
        },
        { key: "created", header: "created", render: (row) => formatDateTime(row.createdAt) },
      ]}
    />
  );
}
