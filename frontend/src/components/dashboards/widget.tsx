"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useAuth } from "@/lib/auth";
import { fmtMetric, type KpiResult } from "@/lib/analytics";
import type { Widget } from "@/lib/workspace";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const COLORS = ["#2563eb", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444", "#06b6d4"];
const AXIS = { fontSize: 10, fill: "var(--muted-foreground)" } as const;

function fmtAxis(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return String(v);
}

type SeriesPoint = { t: string; value: number };
type BreakdownItem = { label: string; value: number };
type Row = Record<string, unknown>;

export function WidgetBody({ widget }: { widget: Widget }) {
  const { api } = useAuth();
  const c = widget.config;

  const { data, isLoading, error } = useQuery({
    queryKey: ["widget", widget.id, widget.type, c],
    queryFn: async (): Promise<SeriesPoint[] | BreakdownItem[] | KpiResult | Row[]> => {
      if (widget.type === "kpi" && c.kpiId) {
        return api<KpiResult>(`/analytics/kpis/${c.kpiId}/value`);
      }
      if (widget.type === "line") {
        const params = new URLSearchParams({
          dataset_id: c.datasetId!,
          date_column: c.dateColumn!,
          metric_column: c.metricColumn!,
          agg: c.agg ?? "sum",
          bucket: c.bucket ?? "month",
        });
        return api<SeriesPoint[]>(`/analytics/series?${params}`);
      }
      if (widget.type === "bar" || widget.type === "pie") {
        const params = new URLSearchParams({
          dataset_id: c.datasetId!,
          dimension: c.dimension!,
          metric_column: c.metricColumn!,
          agg: c.agg ?? "sum",
          limit: "8",
        });
        return api<BreakdownItem[]>(`/analytics/breakdown?${params}`);
      }
      const res = await api<{ rows: Row[] }>(
        `/datasets/${c.datasetId}/preview?page_size=8`,
      );
      return res.rows;
    },
    enabled: !!c.datasetId || !!c.kpiId,
  });

  if (isLoading) return <Skeleton className="h-full min-h-24" />;
  if (error)
    return (
      <p className="flex h-full items-center justify-center text-xs text-muted-foreground">
        Could not load widget data
      </p>
    );

  if (widget.type === "kpi") {
    const k = data as KpiResult;
    return (
      <div className="flex h-full flex-col justify-center">
        <p className="text-3xl font-semibold tracking-tight">
          {fmtMetric(k?.value, k?.unit ?? "")}
        </p>
        {k?.deltaPct != null && (
          <p
            className={`mt-1 text-xs font-medium ${
              k.deltaPct >= 0 ? "text-emerald-600" : "text-red-600"
            }`}
          >
            {k.deltaPct >= 0 ? "+" : ""}
            {k.deltaPct.toFixed(1)}% vs prior period
          </p>
        )}
      </div>
    );
  }

  if (widget.type === "line") {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data as SeriesPoint[]}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="t" tick={AXIS} tickLine={false} axisLine={false} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmtAxis} width={40} />
          <Tooltip formatter={(v) => [fmtMetric(Number(v)), "value"]} />
          <Area type="monotone" dataKey="value" stroke={COLORS[0]} fill={COLORS[0]} fillOpacity={0.15} strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    );
  }

  if (widget.type === "pie") {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data as BreakdownItem[]}
            dataKey="value"
            nameKey="label"
            innerRadius="45%"
            outerRadius="75%"
            paddingAngle={2}
          >
            {(data as BreakdownItem[]).map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip formatter={(v, n) => [fmtMetric(Number(v)), n]} />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  if (widget.type === "bar") {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data as BreakdownItem[]}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmtAxis} width={40} />
          <Tooltip formatter={(v) => [fmtMetric(Number(v)), "value"]} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {(data as BreakdownItem[]).map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  // table
  const rows = data as Row[];
  const cols = rows?.length ? Object.keys(rows[0]).slice(0, 5) : [];
  return (
    <div className="h-full overflow-auto">
      <Table>
        <TableHeader>
          <TableRow>
            {cols.map((k) => (
              <TableHead key={k} className="text-xs">{k}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows?.map((r, i) => (
            <TableRow key={i}>
              {cols.map((k) => (
                <TableCell key={k} className="text-xs">
                  {r[k] == null ? "—" : String(r[k])}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
