"use client";

export type TextFieldProps = {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  placeholder?: string;
};

export function TextField({ label, value, onChange, rows, placeholder }: TextFieldProps) {
  return (
    <label className="block text-sm font-semibold text-slate-700">
      {label}
      {rows ? (
        <textarea
          rows={rows}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
        />
      )}
    </label>
  );
}

export type ListFieldProps = {
  label: string;
  values: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
};

export function ListField({ label, values, onChange, placeholder }: ListFieldProps) {
  return (
    <TextField
      label={`${label}（一行一条）`}
      rows={3}
      value={values.join("\n")}
      onChange={(v) => onChange(v.split("\n").map((s) => s.trim()).filter(Boolean))}
      placeholder={placeholder}
    />
  );
}
