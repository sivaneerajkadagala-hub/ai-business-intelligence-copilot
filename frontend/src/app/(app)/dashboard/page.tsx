"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  Database,
  LayoutDashboard,
  Search,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { useAuth } from "@/lib/auth";
import {
  fmtMetric,
  rangeDates,
  RANGES,
  type Summary,
} from "@/lib/analytics";
import {
  type Dataset,
  type DatasetColumn,
  type Page,
} from "@/lib/datasets";
import {
  BreakdownBarChart,
  BreakdownPieChart,
  SeriesAreaChart,
} from "@/components/charts/data-charts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";

type Profile = { columns: DatasetColumn[] };

function pick(columns: DatasetColumn[] | undefined, type: string[], preferred: string[]) {
  if (!columns) return undefined;
  const typed = columns.filter((c) => type.includes(c.inferredType));
  for (const p of preferred) {
    const hit = typed.find((c) => c.normalizedName === p);
    if (hit) return hit.normalizedName;
  }
  return typed[0]?.normalizedName;
}

function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardDescription>{label}</CardDescription>
        <Icon className="size-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold tracking-tight">{value}</div>
      </CardContent>
    </Card>
  );
}

function DeltaBadge({ pct }: { pct: number | null }) {
  if (pct == null) return null;
  const up = pct >= 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 text-xs font-medium ${
        up ? "text-emerald-600" : "text-destructive"
      }`}
    >
      {up ? <TrendingUp className="size-3" /> : <TrendingDown className="size-3" />}
      {Math.abs(pct).toFixed(1)}% vs prev period
    </span>
  );
}

export default function DashboardPage() {
  const { api } = useAuth();
  const [range, setRange] = useState<string>("12m");
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [metric, setMetric] = useState<string | null>(null);

  const { from, to } = rangeDates(range);

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["summary", from, to],
    queryFn: () =>
      api<Summary>(
        `/analytics/summary${from ? `?from=${from}&to=${to}` : ""}`,
      ),
  });

  const { data: datasets } = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api<Page<Dataset>>("/datasets?page_size=100"),
  });

  const readyDatasets = datasets?.items.filter((d) => d.status === "ready") ?? [];
  const dataset =
    readyDatasets.find((d) => d.id === datasetId) ??
    readyDatasets.find((d) => d.name === "Sales") ??
    readyDatasets[0];

  const { data: profile } = useQuery({
    queryKey: ["profile", dataset?.id],
    queryFn: () => api<Profile>(`/datasets/${dataset!.id}/profile`),
    enabled: !!dataset,
  });

  const dateCol = pick(profile?.columns, ["date", "datetime"], [
    "date",
    "order_date",
    "signup_date",
    "created_at",
  ]);
  const metricCol =
    metric ??
    pick(profile?.columns, ["integer", "float"], [
      "revenue",
      "amount",
      "profit",
      "quantity",
    ]);
  const dimCol = pick(profile?.columns, ["string"], [
    "region",
    "category",
    "customer_type",
    "product",
  ]);

  const seriesParams = `dataset_id=${dataset?.id}&date_column=${dateCol}&metric_column=${metricCol}&agg=sum&bucket=month${from ? `&from=${from}&to=${to}` : ""}`;
  const { data: series, isLoading: seriesLoading } = useQuery({
    queryKey: ["series", seriesParams],
    queryFn: () => api<{ points: { t: string; value: number }[] }>(`/analytics/series?${seriesParams}`),
    enabled: !!dataset && !!dateCol && !!metricCol,
  });

  const breakdownParams = `dataset_id=${dataset?.id}&dimension=${dimCol}&metric_column=${metricCol}&agg=sum&limit=6${dateCol ? `&date_column=${dateCol}` : ""}${from ? `&from=${from}&to=${to}` : ""}`;
  const { data: breakdown, isLoading: breakdownLoading } = useQuery({
    queryKey: ["breakdown", breakdownParams],
    queryFn: () => api<{ items: { label: string; value: number }[] }>(`/analytics/breakdown?${breakdownParams}`),
    enabled: !!dataset && !!dimCol && !!metricCol,
  });

  const numericCols = profile?.columns.filter((c) =>
    ["integer", "float"].includes(c.inferredType),
  );

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Live metrics across your workspace
          </p>
        </div>
        <div className="flex items-center gap-2">
          {RANGES.map((r) => (
            <Button
              key={r.key}
              size="sm"
              variant={range === r.key ? "default" : "outline"}
              onClick={() => setRange(r.key)}
            >
              {r.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {summaryLoading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)
        ) : (
          <>
            <StatCard label="Datasets" value={String(summary?.datasetsCount ?? 0)} icon={Database} />
            <StatCard
              label="Total records"
              value={fmtMetric(summary?.totalRecords ?? 0)}
              icon={BarChart3}
            />
            <StatCard
              label="Dashboards"
              value={String(summary?.dashboardsCount ?? 0)}
              icon={LayoutDashboard}
            />
            <StatCard
              label="Queries executed"
              value={String(summary?.queriesExecuted ?? 0)}
              icon={Search}
            />
          </>
        )}
      </div>

      {summary && summary.kpis.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {summary.kpis.map((k) => (
            <Card key={k.id}>
              <CardHeader className="pb-2">
                <CardDescription className="truncate">{k.name}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-1">
                <div className="text-2xl font-semibold tracking-tight">
                  {k.result ? fmtMetric(k.result.value, k.result.unit) : "—"}
                </div>
                <div className="flex items-center gap-2">
                  <DeltaBadge pct={k.result?.deltaPct ?? null} />
                  {k.result?.target != null && (
                    <span className="text-xs text-muted-foreground">
                      {k.result.progressPct}% of target
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Select
          value={dataset?.id ?? null}
          onValueChange={(v) => {
            setDatasetId(v as string);
            setMetric(null);
          }}
        >
          <SelectTrigger size="sm" className="w-52">
            <SelectValue placeholder="Select dataset" />
          </SelectTrigger>
          <SelectContent>
            {readyDatasets.map((d) => (
              <SelectItem key={d.id} value={d.id}>
                {d.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={metricCol ?? null} onValueChange={(v) => setMetric(v as string)}>
          <SelectTrigger size="sm" className="w-40">
            <SelectValue placeholder="Metric" />
          </SelectTrigger>
          <SelectContent>
            {numericCols?.map((c) => (
              <SelectItem key={c.normalizedName} value={c.normalizedName}>
                {c.normalizedName}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {dataset && (
          <Badge variant="outline">
            {dataset.name} · {dataset.rowCount.toLocaleString()} rows
          </Badge>
        )}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <SeriesAreaChart
            title={metricCol ? `${metricCol} over time` : "Trend"}
            subtitle={dataset ? `${dataset.name} · monthly` : undefined}
            data={series?.points}
            loading={seriesLoading}
          />
        </div>
        <BreakdownPieChart
          title={dimCol ? `By ${dimCol}` : "Breakdown"}
          data={breakdown?.items}
          loading={breakdownLoading}
        />
      </div>

      <BreakdownBarChart
        title={dimCol ? `Top ${dimCol}` : "Top categories"}
        data={breakdown?.items}
        loading={breakdownLoading}
        height={220}
      />

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-base">Recent activity</CardTitle>
            <CardDescription>Latest actions across the workspace</CardDescription>
          </div>
          <Activity className="size-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          {!summary?.recentActivity.length ? (
            <p className="text-sm text-muted-foreground">No activity yet.</p>
          ) : (
            <ScrollArea className="h-48">
              <ul className="flex flex-col gap-2">
                {summary.recentActivity.map((a, i) => (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2">
                      <Badge variant="outline" className="font-mono text-xs">
                        {a.action}
                      </Badge>
                      <span className="text-muted-foreground">{a.actor}</span>
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {a.at ? new Date(a.at).toLocaleString() : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </ScrollArea>
          )}
          <div className="mt-3 text-xs">
            <Link href="/datasets" className="text-primary hover:underline">
              Upload more data
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
