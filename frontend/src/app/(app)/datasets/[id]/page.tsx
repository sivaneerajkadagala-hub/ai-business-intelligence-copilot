"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Brush,
  Download,
  GitBranch,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth";
import { apiErrorMessage, saveBlob } from "@/lib/api";
import {
  formatBytes,
  formatNumber,
  type Dataset,
  type DatasetColumn,
  type DatasetVersion,
} from "@/lib/datasets";
import { CleanDialog } from "@/components/datasets/clean-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

type Profile = { version: DatasetVersion; columns: DatasetColumn[] };
type Preview = {
  version: DatasetVersion;
  columns: string[];
  rows: Record<string, unknown>[];
  total: number;
  page: number;
  pages: number;
};

const TYPE_COLORS: Record<string, "default" | "secondary" | "outline"> = {
  integer: "default",
  float: "default",
  date: "secondary",
  datetime: "secondary",
};

export default function DatasetDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { api, user, download } = useAuth();
  const queryClient = useQueryClient();
  const [previewPage, setPreviewPage] = useState(1);
  const [versionId, setVersionId] = useState<string | null>(null);
  const [cleanOpen, setCleanOpen] = useState(false);

  const { data: ds, isLoading } = useQuery({
    queryKey: ["dataset", id],
    queryFn: () => api<Dataset>(`/datasets/${id}`),
  });

  const activeVersionId = versionId ?? ds?.currentVersionId ?? null;

  const { data: profile } = useQuery({
    queryKey: ["dataset-profile", id, activeVersionId],
    queryFn: () =>
      api<Profile>(`/datasets/${id}/profile?version_id=${activeVersionId}`),
    enabled: !!activeVersionId,
  });

  const { data: preview, isLoading: previewLoading } = useQuery({
    queryKey: ["dataset-preview", id, activeVersionId, previewPage],
    queryFn: () =>
      api<Preview>(
        `/datasets/${id}/preview?version_id=${activeVersionId}&page=${previewPage}&page_size=50`,
      ),
    enabled: !!activeVersionId,
  });

  const canWrite = user?.role === "admin" || user?.role === "analyst";
  const isOwner = ds?.ownerId === user?.id;

  async function onExport() {
    try {
      const blob = await download(`/datasets/${id}/export.csv`);
      saveBlob(blob, `${ds?.name.replace(/\s+/g, "_")}.csv`);
      toast.success("CSV downloaded");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  }

  async function onDelete() {
    try {
      await api(`/datasets/${id}`, { method: "DELETE" });
      toast.success("Dataset deleted");
      router.push("/datasets");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  }

  if (isLoading || !ds) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const activeVersion = ds.versions?.find((v) => v.id === activeVersionId);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.push("/datasets")}>
            <ArrowLeft className="size-4" />
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">{ds.name}</h1>
              <Badge variant="outline">{ds.fileType}</Badge>
              <Badge variant={ds.status === "ready" ? "default" : "destructive"}>
                {ds.status}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {ds.originalFilename} · {formatBytes(ds.fileSizeBytes)} · uploaded{" "}
              {new Date(ds.createdAt).toLocaleString()}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {canWrite && ds.status === "ready" && (
            <Button variant="outline" onClick={() => setCleanOpen(true)}>
              <Brush className="mr-2 size-4" />
              Clean data
            </Button>
          )}
          {canWrite && (
            <Button variant="outline" onClick={onExport}>
              <Download className="mr-2 size-4" />
              Export CSV
            </Button>
          )}
          {(isOwner || user?.role === "admin") && (
            <Button variant="outline" onClick={onDelete}>
              <Trash2 className="mr-2 size-4" />
              Delete
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Rows", value: formatNumber(ds.rowCount) },
          { label: "Columns", value: ds.columnCount.toString() },
          {
            label: "Quality score",
            value: ds.qualityScore != null ? ds.qualityScore.toFixed(0) : "—",
          },
          {
            label: "Version",
            value: activeVersion ? `v${activeVersion.versionNo} (${activeVersion.kind})` : "—",
          },
        ].map((s) => (
          <Card key={s.label}>
            <CardHeader className="pb-2">
              <CardDescription>{s.label}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-semibold">{s.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {ds.versions && ds.versions.length > 1 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <GitBranch className="size-4 text-muted-foreground" />
          <span className="text-muted-foreground">Viewing version:</span>
          {ds.versions.map((v) => (
            <Button
              key={v.id}
              size="sm"
              variant={v.id === activeVersionId ? "default" : "outline"}
              onClick={() => {
                setVersionId(v.id);
                setPreviewPage(1);
              }}
            >
              v{v.versionNo} · {v.kind}
            </Button>
          ))}
        </div>
      )}

      <Tabs defaultValue="preview">
        <TabsList>
          <TabsTrigger value="preview">Preview</TabsTrigger>
          <TabsTrigger value="columns">Column profile</TabsTrigger>
        </TabsList>

        <TabsContent value="preview">
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {preview?.columns.map((c) => (
                        <TableHead key={c} className="whitespace-nowrap">
                          {c}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {previewLoading &&
                      Array.from({ length: 8 }).map((_, i) => (
                        <TableRow key={i}>
                          {Array.from({ length: 5 }).map((__, j) => (
                            <TableCell key={j}>
                              <Skeleton className="h-4 w-20" />
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    {preview?.rows.map((row, i) => (
                      <TableRow key={i}>
                        {preview.columns.map((c) => (
                          <TableCell key={c} className="whitespace-nowrap">
                            {row[c] == null ? (
                              <span className="text-muted-foreground/60">null</span>
                            ) : (
                              String(row[c])
                            )}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
          {preview && preview.pages > 1 && (
            <div className="mt-3 flex items-center gap-3 text-sm">
              <Button
                size="sm"
                variant="outline"
                disabled={previewPage <= 1}
                onClick={() => setPreviewPage(previewPage - 1)}
              >
                Previous
              </Button>
              <span className="text-muted-foreground">
                Page {preview.page} of {preview.pages} ·{" "}
                {formatNumber(preview.total)} rows
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={previewPage >= preview.pages}
                onClick={() => setPreviewPage(previewPage + 1)}
              >
                Next
              </Button>
            </div>
          )}
        </TabsContent>

        <TabsContent value="columns">
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Column</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead className="text-right">Nulls</TableHead>
                      <TableHead className="text-right">Distinct</TableHead>
                      <TableHead className="text-right">Min</TableHead>
                      <TableHead className="text-right">Max</TableHead>
                      <TableHead className="text-right">Mean</TableHead>
                      <TableHead className="text-right">Median</TableHead>
                      <TableHead className="text-right">Std</TableHead>
                      <TableHead className="text-right">Outliers</TableHead>
                      <TableHead>Top values</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {profile?.columns.map((c) => (
                      <TableRow key={c.normalizedName}>
                        <TableCell className="font-medium">
                          {c.normalizedName}
                          <span className="ml-1 text-xs text-muted-foreground">
                            {c.name !== c.normalizedName ? `(${c.name})` : ""}
                          </span>
                        </TableCell>
                        <TableCell>
                          <Badge variant={TYPE_COLORS[c.inferredType] ?? "outline"}>
                            {c.inferredType}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {c.nullCount > 0 ? (
                            <span className="text-destructive">{c.nullCount}</span>
                          ) : (
                            "0"
                          )}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {c.distinctCount}
                        </TableCell>
                        <TableCell className="text-right">{c.minValue ?? "—"}</TableCell>
                        <TableCell className="text-right">{c.maxValue ?? "—"}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          {c.mean != null ? c.mean.toFixed(2) : "—"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {c.median != null ? c.median.toFixed(2) : "—"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {c.stddev != null ? c.stddev.toFixed(2) : "—"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {c.outlierCount != null ? c.outlierCount : "—"}
                        </TableCell>
                        <TableCell className="max-w-48 truncate text-xs text-muted-foreground">
                          {c.topValues
                            ?.slice(0, 3)
                            .map((t) => `${t.value ?? "null"} (${t.count})`)
                            .join(", ")}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {profile && (
        <CleanDialog
          datasetId={ds.id}
          versionId={activeVersionId!}
          columns={profile.columns}
          open={cleanOpen}
          onOpenChange={setCleanOpen}
          onApplied={() => {
            queryClient.invalidateQueries({ queryKey: ["dataset", id] });
            setVersionId(null);
            setPreviewPage(1);
          }}
        />
      )}
    </div>
  );
}
