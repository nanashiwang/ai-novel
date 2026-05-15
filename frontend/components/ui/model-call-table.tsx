import { modelCalls } from "@/lib/mock-data";
import { formatDateTime, msToTime } from "@/lib/format";
import { DataTable } from "./data-table";
import { StatusBadge } from "./badge";
import type { ModelCall } from "@/types";

export function ModelCallTable({ rows = modelCalls }: { rows?: ModelCall[] }) {
  return (
    <DataTable
      rows={rows}
      columns={[
        { key: "task", header: "task_type", render: (row) => <span className="font-semibold text-slate-950">{row.taskType}</span> },
        { key: "model", header: "model", render: (row) => row.model },
        { key: "tokens", header: "input / output", render: (row) => `${row.inputTokens.toLocaleString()} / ${row.outputTokens.toLocaleString()}` },
        { key: "latency", header: "latency", render: (row) => msToTime(row.latencyMs) },
        { key: "status", header: "status", render: (row) => <StatusBadge status={row.status === "success" ? "succeeded" : "failed"} /> },
        { key: "created", header: "created", render: (row) => formatDateTime(row.createdAt) },
      ]}
    />
  );
}
