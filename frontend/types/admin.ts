export type AuditLog = {
  id: string;
  actor: string;
  action: string;
  resource: string;
  target: string;
  ip: string;
  createdAt: string;
};

export type PlatformMetric = {
  label: string;
  value: string;
  delta: string;
  tone: "blue" | "green" | "orange" | "rose" | "violet";
};
