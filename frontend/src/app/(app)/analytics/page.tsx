"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Target, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth";
import { apiErrorMessage } from "@/lib/api";
import { fmtMetric, type KPI } from "@/lib/analytics";
import {
  type Dataset,
  type DatasetColumn,
  type Page,
} from "@/lib/datasets";
import {
  BreakdownBarChart,
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const AGGS = ["sum", "avg", "count", "count_distinct", "min", "max"];
type Profile = { columns: DatasetColumn[] };

export default function AnalyticsPage() {
  const { api, user } = useAuth();
  const queryClient = useQueryClient();
  const canWrite = user?.role === "admin" || user?.role === "analyst";

  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({
    name: "",
    datasetId: "",
    aggregation: "sum",
    column: "",
    dateColumn: "",
    target: "",
    unit: "",
  });
  const [explorerDatasetId, setExplorerDatasetId] = useState<string | null>(null);
  const [explorerMetric, setExplorerMetric] = useState<string | null>(null);
  const [explorerDim, setExplorerDim] = useState<string | null>(null);

  const { data: kpis, isLoading } = useQuery({
    queryKey: ["kpis"],
    queryFn: () => api<KPI[]>("/analytics/kpis"),
  });

  const { data: datasets } = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api<Page<Dataset>>("/datasets?page_size=100"),
  });
  const readyDatasets = datasets?.items.filter((d) => d.status === "ready") ?? [];

  // Profile for the KPI-form dataset
  const { data: formProfile } = useQuery({
    queryKey: ["profile", form.datasetId],
    queryFn: () => api<Profile>(`/datasets/${form.datasetId}/profile`),
    enabled: !!form.datasetId,
  });

  // Profile for explorer dataset
  const explorerDataset =
    readyDatasets.find((d) => d.id === explorerDatasetId) ??
    readyDatasets.find((d) => d.name === "Sales") ??
    readyDatasets[0];
  const { data: explorerProfile } = useQuery({
    queryKey: ["profile", explorerDataset?.id],
    queryFn: () => api<Profile>(`/datasets/${explorerDataset!.id}/profile`),
    enabled: !!explorerDataset,
  });

  const eDate = explorerProfile?.columns.find((c) =>
    ["date", "datetime"].includes(c.inferredType),
  )?.normalizedName;
  const eMetric =
    explorerMetric ??
    explorerProfile?.columns.find((c) => ["integer", "float"].includes(c.inferredType))
      ?.normalizedName;
  const eDim =
    explorerDim ??
    explorerProfile?.columns.find((c) => c.inferredType === "string")?.normalizedName;

  const { data: series } = useQuery({
    queryKey: ["exp-series", explorerDataset?.id, eDate, eMetric],
    queryFn: () =>
      api<{ points: { t: string; value: number }[] }>(
        `/analytics/series?dataset_id=${explorerDataset!.id}&date_column=${eDate}&metric_column=${eMetric}&agg=sum&bucket=month`,
      ),
    enabled: !!explorerDataset && !!eDate && !!eMetric,
  });
  const { data: breakdown } = useQuery({
    queryKey: ["exp-breakdown", explorerDataset?.id, eDim, eMetric],
    queryFn: () =>
      api<{ items: { label: string; value: number }[] }>(
        `/analytics/breakdown?dataset_id=${explorerDataset!.id}&dimension=${eDim}&metric_column=${eMetric}&agg=sum&limit=8`,
      ),
    enabled: !!explorerDataset && !!eDim && !!eMetric,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api<KPI>("/analytics/kpis", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          datasetId: form.datasetId,
          formula: {
            aggregation: form.aggregation,
            column: form.column || undefined,
            dateColumn: form.dateColumn || undefined,
          },
          target: form.target ? Number(form.target) : undefined,
          unit: form.unit || undefined,
        }),
      }),
    onSuccess: () => {
      toast.success("KPI created");
      setCreateOpen(false);
      setForm({ ...form, name: "", target: "", unit: "" });
      queryClient.invalidateQueries({ queryKey: ["kpis"] });
      queryClient.invalidateQueries({ queryKey: ["summary"] });
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api(`/analytics/kpis/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kpis"] });
      queryClient.invalidateQueries({ queryKey: ["summary"] });
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const numericCols = formProfile?.columns.filter((c) =>
    ["integer", "float"].includes(c.inferredType),
  );
  const dateCols = formProfile?.columns.filter((c) =>
    ["date", "datetime"].includes(c.inferredType),
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
          <p className="text-sm text-muted-foreground">
            Define KPIs and explore metrics across datasets
          </p>
        </div>
        {canWrite && (
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger render={<Button />}>
              <Plus className="mr-2 size-4" />
              New KPI
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create KPI</DialogTitle>
                <DialogDescription>
                  A live metric computed from a dataset column.
                </DialogDescription>
              </DialogHeader>
              <div className="flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label>Name</Label>
                  <Input
                    placeholder="e.g. Monthly Revenue"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Dataset</Label>
                  <Select
                    value={form.datasetId || null}
                    onValueChange={(v) => setForm({ ...form, datasetId: v as string, column: "", dateColumn: "" })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Choose dataset" />
                    </SelectTrigger>
                    <SelectContent>
                      {readyDatasets.map((d) => (
                        <SelectItem key={d.id} value={d.id}>
                          {d.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>Aggregation</Label>
                    <Select
                      value={form.aggregation}
                      onValueChange={(v) => setForm({ ...form, aggregation: v as string })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {AGGS.map((a) => (
                          <SelectItem key={a} value={a}>
                            {a}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>Metric column</Label>
                    <Select
                      value={form.column || null}
                      onValueChange={(v) => setForm({ ...form, column: v as string })}
                      disabled={form.aggregation === "count"}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="column" />
                      </SelectTrigger>
                      <SelectContent>
                        {numericCols?.map((c) => (
                          <SelectItem key={c.normalizedName} value={c.normalizedName}>
                            {c.normalizedName}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Date column (for period filters)</Label>
                  <Select
                    value={form.dateColumn || null}
                    onValueChange={(v) => setForm({ ...form, dateColumn: v as string })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="optional" />
                    </SelectTrigger>
                    <SelectContent>
                      {dateCols?.map((c) => (
                        <SelectItem key={c.normalizedName} value={c.normalizedName}>
                          {c.normalizedName}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>Target (optional)</Label>
                    <Input
                      type="number"
                      placeholder="e.g. 100000"
                      value={form.target}
                      onChange={(e) => setForm({ ...form, target: e.target.value })}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>Unit (optional)</Label>
                    <Input
                      placeholder="e.g. $"
                      value={form.unit}
                      onChange={(e) => setForm({ ...form, unit: e.target.value })}
                    />
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button
                  disabled={!form.name || !form.datasetId || createMutation.isPending}
                  onClick={() => createMutation.mutate()}
                >
                  {createMutation.isPending ? "Creating..." : "Create KPI"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">KPIs</CardTitle>
          <CardDescription>Live values computed from current data</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Formula</TableHead>
                <TableHead className="text-right">Current value</TableHead>
                <TableHead>Target progress</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 5 }).map((__, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-20" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              {!isLoading && !kpis?.length && (
                <TableRow>
                  <TableCell colSpan={5}>
                    <div className="flex flex-col items-center gap-2 py-12 text-center">
                      <Target className="size-8 text-muted-foreground/50" />
                      <p className="text-sm text-muted-foreground">
                        No KPIs yet — create one to track a metric over time.
                      </p>
                    </div>
                  </TableCell>
                </TableRow>
              )}
              {kpis?.map((k) => (
                <KpiRow key={k.id} kpi={k} onDelete={() => deleteMutation.mutate(k.id)} canWrite={canWrite} />
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">Data explorer</h2>
        <div className="flex items-center gap-2">
          <Select
            value={explorerDataset?.id ?? null}
            onValueChange={(v) => {
              setExplorerDatasetId(v as string);
              setExplorerMetric(null);
              setExplorerDim(null);
            }}
          >
            <SelectTrigger size="sm" className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {readyDatasets.map((d) => (
                <SelectItem key={d.id} value={d.id}>
                  {d.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={eMetric ?? null} onValueChange={(v) => setExplorerMetric(v as string)}>
            <SelectTrigger size="sm" className="w-36">
              <SelectValue placeholder="metric" />
            </SelectTrigger>
            <SelectContent>
              {explorerProfile?.columns
                .filter((c) => ["integer", "float"].includes(c.inferredType))
                .map((c) => (
                  <SelectItem key={c.normalizedName} value={c.normalizedName}>
                    {c.normalizedName}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
          <Select value={eDim ?? null} onValueChange={(v) => setExplorerDim(v as string)}>
            <SelectTrigger size="sm" className="w-36">
              <SelectValue placeholder="dimension" />
            </SelectTrigger>
            <SelectContent>
              {explorerProfile?.columns
                .filter((c) => c.inferredType === "string")
                .map((c) => (
                  <SelectItem key={c.normalizedName} value={c.normalizedName}>
                    {c.normalizedName}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <SeriesAreaChart
          title={eMetric ? `${eMetric} over time` : "Trend"}
          subtitle={explorerDataset ? `${explorerDataset.name} · monthly` : undefined}
          data={series?.points}
        />
        <BreakdownBarChart
          title={eDim ? `${eMetric} by ${eDim}` : "Breakdown"}
          data={breakdown?.items}
        />
      </div>
    </div>
  );
}

function KpiRow({
  kpi,
  onDelete,
  canWrite,
}: {
  kpi: KPI;
  onDelete: () => void;
  canWrite: boolean;
}) {
  const { api } = useAuth();
  const { data: result } = useQuery({
    queryKey: ["kpi-value", kpi.id],
    queryFn: () =>
      api<{ value: number; deltaPct: number | null; progressPct: number | null }>(
        `/analytics/kpis/${kpi.id}/value`,
      ),
  });

  const f = kpi.formula;
  return (
    <TableRow>
      <TableCell className="font-medium">{kpi.name}</TableCell>
      <TableCell>
        <Badge variant="outline" className="font-mono text-xs">
          {f.aggregation}({f.column ?? "*"})
        </Badge>
      </TableCell>
      <TableCell className="text-right tabular-nums font-medium">
        {result ? fmtMetric(result.value, kpi.unit) : <Skeleton className="ml-auto h-4 w-16" />}
      </TableCell>
      <TableCell>
        {kpi.target ? (
          <div className="flex items-center gap-2">
            <Progress value={Math.min(result?.progressPct ?? 0, 100)} className="w-24" />
            <span className="text-xs text-muted-foreground">
              {result?.progressPct ?? "—"}% of {fmtMetric(kpi.target, kpi.unit)}
            </span>
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">no target</span>
        )}
      </TableCell>
      <TableCell>
        {canWrite && (
          <Button variant="ghost" size="icon" onClick={onDelete}>
            <Trash2 className="size-4 text-muted-foreground" />
          </Button>
        )}
      </TableCell>
    </TableRow>
  );
}
