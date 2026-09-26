"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  GitCompareArrows,
  Lightbulb,
  RefreshCw,
  TrendingUp,
  TriangleAlert,
  Waves,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth";
import { apiErrorMessage } from "@/lib/api";
import { fmtMetric } from "@/lib/analytics";
import {
  type Dataset,
  type DatasetColumn,
  type Page,
} from "@/lib/datasets";
import { AnswerChart } from "@/components/copilot/answer";
import type { ChatMessage } from "@/lib/copilot";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type Insight = {
  id: string;
  type: "trend" | "anomaly" | "comparison" | "ranking" | "forecast";
  title: string;
  body: string;
  severity: "info" | "warning" | "critical";
  generatedBy: string;
  createdAt: string;
};

type AnomalyResult = {
  series: { t: string; value: number }[];
  anomalies: {
    t: string; value: number; expected: number;
    score: number; direction: string; severity: string; method: string;
  }[];
  method: string;
  points: number;
};

type ForecastResult = {
  id: string;
  method: string;
  history: { t: string; value: number }[];
  forecast: { t: string; forecast: number; lower: number; upper: number }[];
};

type Profile = { columns: DatasetColumn[] };

const TYPE_ICON = {
  trend: TrendingUp,
  anomaly: TriangleAlert,
  comparison: GitCompareArrows,
  ranking: Activity,
  forecast: Waves,
};

const SEVERITY_BADGE: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  info: "secondary",
  warning: "default",
  critical: "destructive",
};

export default function InsightsPage() {
  const { api, user } = useAuth();
  const queryClient = useQueryClient();
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [horizon, setHorizon] = useState("6");
  const canWrite = user?.role === "admin" || user?.role === "analyst";

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
  const dateCol = profile?.columns.find((c) =>
    ["date", "datetime"].includes(c.inferredType),
  )?.normalizedName;
  const metricCol = profile?.columns.find((c) =>
    ["revenue", "amount", "profit", "quantity"].includes(c.normalizedName),
  )?.normalizedName
    ?? profile?.columns.find((c) => ["integer", "float"].includes(c.inferredType))?.normalizedName;

  const { data: insightList, isLoading } = useQuery({
    queryKey: ["insights", dataset?.id],
    queryFn: () => api<Insight[]>(`/insights?dataset_id=${dataset!.id}`),
    enabled: !!dataset,
  });

  const { data: anomalyRes, isLoading: anomalyLoading } = useQuery({
    queryKey: ["anomalies", dataset?.id, dateCol, metricCol],
    queryFn: () =>
      api<AnomalyResult>(
        `/insights/anomalies?dataset_id=${dataset!.id}&date_column=${dateCol}&metric_column=${metricCol}&bucket=day`,
      ),
    enabled: !!dataset && !!dateCol && !!metricCol,
    retry: false,
  });

  const generateMutation = useMutation({
    mutationFn: () =>
      api<Insight[]>(`/insights/generate?dataset_id=${dataset!.id}`, { method: "POST" }),
    onSuccess: (list) => {
      toast.success(`${list.length} insights generated`);
      queryClient.invalidateQueries({ queryKey: ["insights", dataset?.id] });
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const forecastMutation = useMutation({
    mutationFn: () =>
      api<ForecastResult>("/insights/forecast", {
        method: "POST",
        body: JSON.stringify({
          datasetId: dataset!.id,
          dateColumn: dateCol,
          metricColumn: metricCol,
          bucket: "month",
          horizon: Number(horizon),
        }),
      }),
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const anomalyChartMsg: ChatMessage | null = anomalyRes
    ? {
        id: "a", role: "assistant", content: "", sql: null,
        resultSnapshot: {
          columns: [], rows: anomalyRes.anomalies as unknown as Record<string, unknown>[],
          rowCount: anomalyRes.anomalies.length, series: anomalyRes.series,
        },
        chartSpec: { type: "anomaly" }, explanation: null, createdAt: "",
      }
    : null;

  const forecastChartMsg: ChatMessage | null = forecastMutation.data
    ? {
        id: "f", role: "assistant", content: "", sql: null,
        resultSnapshot: {
          columns: [],
          rows: forecastMutation.data.forecast as unknown as Record<string, unknown>[],
          rowCount: forecastMutation.data.forecast.length,
          series: forecastMutation.data.history,
        },
        chartSpec: { type: "forecast" }, explanation: null, createdAt: "",
      }
    : null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Insights</h1>
          <p className="text-sm text-muted-foreground">
            AI-generated findings, anomaly detection &amp; forecasts
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={dataset?.id} onValueChange={(v) => setDatasetId(v as string)}>
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
          {canWrite && (
            <Button
              size="sm"
              disabled={!dataset || generateMutation.isPending}
              onClick={() => generateMutation.mutate()}
            >
              <RefreshCw className={`mr-2 size-4 ${generateMutation.isPending ? "animate-spin" : ""}`} />
              Generate insights
            </Button>
          )}
        </div>
      </div>

      {/* Insights cards */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {isLoading &&
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-32" />)}
        {!isLoading && !insightList?.length && (
          <Card className="col-span-full">
            <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
              <Lightbulb className="size-8 text-muted-foreground/50" />
              <p className="text-sm text-muted-foreground">
                No insights yet — click &quot;Generate insights&quot; to analyze{" "}
                {dataset?.name ?? "the dataset"}.
              </p>
            </CardContent>
          </Card>
        )}
        {insightList?.map((ins) => {
          const Icon = TYPE_ICON[ins.type] ?? Lightbulb;
          return (
            <Card key={ins.id}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <div className="flex items-center gap-2">
                  <Icon className="size-4 text-muted-foreground" />
                  <CardTitle className="text-sm">{ins.title}</CardTitle>
                </div>
                <Badge variant={SEVERITY_BADGE[ins.severity] ?? "secondary"}>
                  {ins.severity}
                </Badge>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{ins.body}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {/* Anomaly detection */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Anomaly detection</CardTitle>
            <CardDescription>
              {metricCol && dateCol
                ? `${metricCol} by ${dateCol} (daily, ${anomalyRes?.method ?? "z-score/IQR"})`
                : "No date+metric columns found"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {anomalyLoading ? (
              <Skeleton className="h-56" />
            ) : anomalyChartMsg ? (
              <>
                <AnswerChart msg={anomalyChartMsg} />
                {anomalyRes!.anomalies.length > 0 ? (
                  <div className="mt-3 overflow-x-auto rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Date</TableHead>
                          <TableHead>Direction</TableHead>
                          <TableHead className="text-right">Value</TableHead>
                          <TableHead className="text-right">Expected</TableHead>
                          <TableHead className="text-right">Score</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {anomalyRes!.anomalies.slice(0, 8).map((a) => (
                          <TableRow key={a.t}>
                            <TableCell className="font-mono text-xs">{a.t}</TableCell>
                            <TableCell>
                              <Badge variant={a.direction === "spike" ? "destructive" : "default"}>
                                {a.direction}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {fmtMetric(a.value)}
                            </TableCell>
                            <TableCell className="text-right tabular-nums text-muted-foreground">
                              {fmtMetric(a.expected)}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {a.score.toFixed(1)}σ
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-muted-foreground">
                    No anomalies — all {anomalyRes!.points} points within normal range.
                  </p>
                )}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                Not enough data points for detection (need ≥8).
              </p>
            )}
          </CardContent>
        </Card>

        {/* Forecasting */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">Forecast</CardTitle>
                <CardDescription>
                  {forecastMutation.data
                    ? `Method: ${forecastMutation.data.method} · ~80% CI`
                    : "Project forward from the monthly series"}
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Select value={horizon} onValueChange={(v) => setHorizon(v as string)}>
                  <SelectTrigger size="sm" className="w-24">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {["3", "6", "12"].map((h) => (
                      <SelectItem key={h} value={h}>
                        {h} mo
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!dataset || !dateCol || !metricCol || forecastMutation.isPending}
                  onClick={() => forecastMutation.mutate()}
                >
                  Run
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {forecastMutation.isPending ? (
              <Skeleton className="h-56" />
            ) : forecastChartMsg ? (
              <AnswerChart msg={forecastChartMsg} />
            ) : (
              <p className="text-sm text-muted-foreground">
                Choose a horizon and run a forecast.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
