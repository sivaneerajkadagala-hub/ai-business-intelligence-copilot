export type KPI = {
  id: string;
  name: string;
  description: string | null;
  datasetId: string;
  formula: {
    aggregation: string;
    column?: string;
    dateColumn?: string;
    filters?: { column: string; op: string; value: unknown }[];
  };
  target: number | null;
  unit: string | null;
  createdAt: string;
  result?: KpiResult | null;
};

export type KpiResult = {
  value: number;
  deltaPct: number | null;
  target: number | null;
  progressPct: number | null;
  unit: string | null;
};

export type Summary = {
  datasetsCount: number;
  totalRecords: number;
  dashboardsCount: number;
  queriesExecuted: number;
  kpis: KPI[];
  recentActivity: { action: string; at: string | null; actor: string }[];
};

export type SeriesPoint = { t: string; value: number };
export type BreakdownItem = { label: string; value: number };

export const RANGES = [
  { key: "90d", label: "90 days", days: 90 },
  { key: "6m", label: "6 months", days: 183 },
  { key: "12m", label: "12 months", days: 365 },
  { key: "all", label: "All time", days: null },
] as const;

export function rangeDates(key: string): { from?: string; to?: string } {
  const r = RANGES.find((x) => x.key === key);
  if (!r || !r.days) return {};
  const to = new Date();
  const from = new Date(Date.now() - r.days * 86400_000);
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

export function fmtMetric(v: number | null | undefined, unit?: string | null): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  let s: string;
  if (abs >= 1_000_000) s = `${(v / 1_000_000).toFixed(1)}M`;
  else if (abs >= 1_000) s = `${(v / 1_000).toFixed(1)}K`;
  else s = v.toLocaleString("en-US", { maximumFractionDigits: 2 });
  return unit ? `${unit}${s}` : s;
}
