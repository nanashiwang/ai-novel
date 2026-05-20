"use client";

import { EyeOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";

export type ProviderFieldsProps = {
  title: string;
  active: boolean;
  configured: boolean;
  baseUrl: string;
  apiKey: string;
  disabled: boolean;
  onBaseUrlChange: (value: string) => void;
  onApiKeyChange: (value: string) => void;
  baseUrlPlaceholder: string;
  keyPlaceholder: string;
};

export function ProviderFields({
  title,
  active,
  configured,
  baseUrl,
  apiKey,
  disabled,
  onBaseUrlChange,
  onApiKeyChange,
  baseUrlPlaceholder,
  keyPlaceholder,
}: ProviderFieldsProps) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        active ? "border-indigo-200 bg-indigo-50/40" : "border-slate-200 bg-white"
      }`}
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="font-bold text-slate-950">{title}</p>
        <Badge tone={configured ? "green" : "slate"}>
          {configured ? "Key 已保存" : "未保存 Key"}
        </Badge>
      </div>
      <div className="grid gap-4 md:grid-cols-[1.2fr_0.8fr]">
        <label className="block text-sm font-bold text-slate-700">
          Base URL
          <input
            disabled={disabled}
            value={baseUrl}
            onChange={(e) => onBaseUrlChange(e.target.value)}
            placeholder={baseUrlPlaceholder}
            className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-4 disabled:bg-slate-100"
          />
        </label>
        <label className="block text-sm font-bold text-slate-700">
          API Key
          <div className="relative mt-2">
            <input
              disabled={disabled}
              value={apiKey}
              onChange={(e) => onApiKeyChange(e.target.value)}
              placeholder={keyPlaceholder}
              type="password"
              className="h-11 w-full rounded-xl border border-slate-200 bg-white px-4 pr-10 disabled:bg-slate-100"
            />
            <EyeOff className="pointer-events-none absolute right-3 top-3 size-5 text-slate-400" />
          </div>
        </label>
      </div>
    </div>
  );
}
