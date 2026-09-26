"use client";

import { useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import GridLayout, { WidthProvider, type Layout } from "react-grid-layout";
import { GripVertical, Loader2, Pencil, Plus, Save, X } from "lucide-react";
import { toast } from "sonner";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

import { useAuth } from "@/lib/auth";
import { apiErrorMessage } from "@/lib/api";
import type { DashboardDetail, Widget, WidgetType } from "@/lib/workspace";
import type { Dataset, DatasetColumn, Page } from "@/lib/datasets";
import type { KPI } from "@/lib/analytics";
import { WidgetBody } from "@/components/dashboards/widget";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const RGL = WidthProvider(GridLayout);
type Profile = { columns: DatasetColumn[] };

const WIDGET_DEFAULTS: Record<WidgetType, { w: number; h: number }> = {
  kpi: { w: 3, h: 3 },
  line: { w: 6, h: 4 },
  bar: { w: 6, h: 4 },
  pie: { w: 4, h: 4 },
  table: { w: 6, h: 4 },
};

export default function DashboardBuilderPage() {
  const { api, user } = useAuth();
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const canEdit =
    user?.role === "admin" || user?.role === "analyst";

  const [editing, setEditing] = useState(false);
  const [drafts, setDrafts] = useState<Widget[] | null>(null);
  const nextId = useRef(0);
  const [addOpen, setAddOpen] = useState(false);
  const [wType, setWType] = useState<WidgetType>("line");
  const [wTitle, setWTitle] = useState("");
  const [wDataset, setWDataset] = useState<string | null>(null);
  const [wKpi, setWKpi] = useState<string | null>(null);
  const [wDate, setWDate] = useState<string | null>(null);
  const [wMetric, setWMetric] = useState<string | null>(null);
  const [wDim, setWDim] = useState<string | null>(null);

  const { data: dashboard, isLoading } = useQuery({
    queryKey: ["dashboard", id],
    queryFn: () => api<DashboardDetail>(`/dashboards/${id}`),
  });
  const widgets = useMemo(
    () => drafts ?? dashboard?.widgets ?? [],
    [drafts, dashboard],
  );

  const { data: datasets } = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api<Page<Dataset>>("/datasets?page_size=100"),
    enabled: addOpen,
  });
  const readyDatasets = datasets?.items.filter((d) => d.status === "ready") ?? [];
  const selDataset = readyDatasets.find((d) => d.id === wDataset) ?? readyDatasets[0];

  const { data: profile } = useQuery({
    queryKey: ["profile", selDataset?.id],
    queryFn: () => api<Profile>(`/datasets/${selDataset!.id}/profile`),
    enabled: !!selDataset && wType !== "kpi",
  });
  const { data: kpis } = useQuery({
    queryKey: ["kpis", selDataset?.id],
    queryFn: () => api<KPI[]>(`/analytics/kpis?dataset_id=${selDataset!.id}`),
    enabled: !!selDataset && wType === "kpi",
  });

  const dateCols = profile?.columns.filter((c) => ["date", "datetime"].includes(c.inferredType)) ?? [];
  const metricCols = profile?.columns.filter((c) => ["integer", "float"].includes(c.inferredType)) ?? [];
  const dimCols = profile?.columns.filter((c) => c.inferredType === "string") ?? [];

  const saveMutation = useMutation({
    mutationFn: (list: Widget[]) =>
      api<Widget[]>(`/dashboards/${id}/widgets`, {
        method: "PUT",
        body: JSON.stringify({
          widgets: list.map((w) => ({
            type: w.type, title: w.title, config: w.config, position: w.position,
          })),
        }),
      }),
    onSuccess: () => {
      toast.success("Layout saved");
      setEditing(false);
      setDrafts(null);
      queryClient.invalidateQueries({ queryKey: ["dashboard", id] });
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const layout: Layout[] = useMemo(
    () =>
      widgets.map((w) => ({
        i: w.id, x: w.position.x, y: w.position.y,
        w: w.position.w, h: w.position.h, minW: 2, minH: 2,
      })),
    [widgets],
  );

  function onLayoutChange(l: Layout[]) {
    if (!dashboard) return;
    const byId = Object.fromEntries(l.map((li) => [li.i, li]));
    setDrafts(
      widgets.map((w) => ({
        ...w,
        position: byId[w.id]
          ? { x: byId[w.id].x, y: byId[w.id].y, w: byId[w.id].w, h: byId[w.id].h }
          : w.position,
      })),
    );
  }

  function addWidget() {
    if (!selDataset) return;
    const config: Widget["config"] = { datasetId: selDataset.id };
    if (wType === "kpi") config.kpiId = wKpi ?? kpis?.[0]?.id;
    if (wType === "line") {
      config.dateColumn = wDate ?? dateCols[0]?.normalizedName;
      config.metricColumn = wMetric ?? metricCols[0]?.normalizedName;
      config.bucket = "month";
    }
    if (wType === "bar" || wType === "pie") {
      config.dimension = wDim ?? dimCols[0]?.normalizedName;
      config.metricColumn = wMetric ?? metricCols[0]?.normalizedName;
      config.agg = "sum";
    }
    const def = WIDGET_DEFAULTS[wType];
    const w: Widget = {
      id: `new-${++nextId.current}`,
      type: wType,
      title: wTitle.trim() || `${wType.toUpperCase()} — ${selDataset.name}`,
      config,
      position: { x: 0, y: Infinity, ...def },
      sortOrder: widgets.length,
    };
    setDrafts([...widgets, w]);
    setEditing(true);
    setAddOpen(false);
    setWTitle("");
  }

  function removeWidget(wid: string) {
    setDrafts(widgets.filter((w) => w.id !== wid));
  }

  if (isLoading) return <Skeleton className="h-96" />;
  if (!dashboard) {
    router.replace("/dashboards");
    return null;
  }
  const dirty = drafts !== null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            {dashboard.name}
            {!dashboard.isShared && <Badge variant="outline">private</Badge>}
          </h1>
          <p className="text-sm text-muted-foreground">{dashboard.description}</p>
        </div>
        <div className="flex items-center gap-2">
          {canEdit && (
            <>
              <Dialog open={addOpen} onOpenChange={setAddOpen}>
                <DialogTrigger render={<Button variant="outline" />}>
                  <Plus className="mr-2 size-4" /> Add widget
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Add widget</DialogTitle>
                  </DialogHeader>
                  <div className="flex flex-col gap-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="flex flex-col gap-1.5">
                        <Label>Type</Label>
                        <Select value={wType} onValueChange={(v) => setWType(v as WidgetType)}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {(["kpi", "line", "bar", "pie", "table"] as const).map((t) => (
                              <SelectItem key={t} value={t}>{t.toUpperCase()}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label>Dataset</Label>
                        <Select value={selDataset?.id} onValueChange={(v) => setWDataset(v as string)}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {readyDatasets.map((d) => (
                              <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label>Title</Label>
                      <Input value={wTitle} onChange={(e) => setWTitle(e.target.value)} placeholder="Widget title" />
                    </div>
                    {wType === "kpi" && (
                      <div className="flex flex-col gap-1.5">
                        <Label>KPI</Label>
                        <Select value={wKpi ?? kpis?.[0]?.id} onValueChange={(v) => setWKpi(v as string)}>
                          <SelectTrigger><SelectValue placeholder="Select KPI" /></SelectTrigger>
                          <SelectContent>
                            {(kpis ?? []).map((k) => (
                              <SelectItem key={k.id} value={k.id}>{k.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        {!kpis?.length && (
                          <p className="text-xs text-muted-foreground">No KPIs on this dataset yet.</p>
                        )}
                      </div>
                    )}
                    {wType === "line" && (
                      <div className="grid grid-cols-2 gap-3">
                        <div className="flex flex-col gap-1.5">
                          <Label>Date column</Label>
                          <Select value={wDate ?? dateCols[0]?.normalizedName} onValueChange={(v) => setWDate(v as string)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              {dateCols.map((c) => (
                                <SelectItem key={c.normalizedName} value={c.normalizedName}>{c.name}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="flex flex-col gap-1.5">
                          <Label>Metric</Label>
                          <Select value={wMetric ?? metricCols[0]?.normalizedName} onValueChange={(v) => setWMetric(v as string)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              {metricCols.map((c) => (
                                <SelectItem key={c.normalizedName} value={c.normalizedName}>{c.name}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    )}
                    {(wType === "bar" || wType === "pie") && (
                      <div className="grid grid-cols-2 gap-3">
                        <div className="flex flex-col gap-1.5">
                          <Label>Dimension</Label>
                          <Select value={wDim ?? dimCols[0]?.normalizedName} onValueChange={(v) => setWDim(v as string)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              {dimCols.map((c) => (
                                <SelectItem key={c.normalizedName} value={c.normalizedName}>{c.name}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="flex flex-col gap-1.5">
                          <Label>Metric</Label>
                          <Select value={wMetric ?? metricCols[0]?.normalizedName} onValueChange={(v) => setWMetric(v as string)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              {metricCols.map((c) => (
                                <SelectItem key={c.normalizedName} value={c.normalizedName}>{c.name}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    )}
                    <Button onClick={addWidget} disabled={wType === "kpi" && !kpis?.length}>
                      Add to dashboard
                    </Button>
                  </div>
                </DialogContent>
              </Dialog>
              {dirty ? (
                <Button onClick={() => saveMutation.mutate(widgets)} disabled={saveMutation.isPending}>
                  {saveMutation.isPending ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Save className="mr-2 size-4" />}
                  Save layout
                </Button>
              ) : (
                <Button variant="secondary" onClick={() => setEditing(!editing)}>
                  <Pencil className="mr-2 size-4" /> {editing ? "Done" : "Edit"}
                </Button>
              )}
            </>
          )}
        </div>
      </div>

      {!widgets.length ? (
        <div className="flex h-72 flex-col items-center justify-center gap-3 rounded-lg border border-dashed text-center">
          <Plus className="size-8 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">
            Empty dashboard — add a widget to get started.
          </p>
        </div>
      ) : (
        <RGL
          layout={layout}
          cols={12}
          rowHeight={64}
          isDraggable={editing}
          isResizable={editing}
          onLayoutChange={onLayoutChange}
          draggableHandle=".widget-drag-handle"
          compactType="vertical"
        >
          {widgets.map((w) => (
            <div
              key={w.id}
              className="flex flex-col overflow-hidden rounded-lg border bg-card"
            >
              <div className="flex items-center justify-between border-b px-3 py-1.5">
                <div className="flex items-center gap-1.5">
                  <GripVertical
                    className={`widget-drag-handle size-3.5 text-muted-foreground/50 ${
                      editing ? "cursor-grab" : "invisible"
                    }`}
                  />
                  <span className="truncate text-xs font-medium">{w.title}</span>
                </div>
                {editing && (
                  <button
                    onClick={() => removeWidget(w.id)}
                    className="text-muted-foreground hover:text-destructive"
                    title="Remove widget"
                  >
                    <X className="size-3.5" />
                  </button>
                )}
              </div>
              <div className="min-h-0 flex-1 p-2">
                <WidgetBody widget={w} />
              </div>
            </div>
          ))}
        </RGL>
      )}
    </div>
  );
}
