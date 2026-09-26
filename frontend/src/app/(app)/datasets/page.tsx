"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, DatabaseZap, FileSpreadsheet, Upload } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth";
import { apiErrorMessage } from "@/lib/api";
import {
  formatBytes,
  formatNumber,
  type Dataset,
  type Page,
} from "@/lib/datasets";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
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
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function QualityBadge({ score }: { score: number | null }) {
  if (score == null) return <span className="text-muted-foreground">—</span>;
  const variant = score >= 80 ? "default" : score >= 50 ? "secondary" : "destructive";
  return <Badge variant={variant}>{score.toFixed(0)}</Badge>;
}

function StatusBadge({ status }: { status: Dataset["status"] }) {
  const map: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
    ready: "default",
    failed: "destructive",
  };
  return <Badge variant={map[status] ?? "secondary"}>{status}</Badge>;
}

export default function DatasetsPage() {
  const router = useRouter();
  const { api, user } = useAuth();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [srcOpen, setSrcOpen] = useState(false);
  const [srcUrl, setSrcUrl] = useState("");
  const [srcTables, setSrcTables] = useState<{ schema: string; table: string }[] | null>(null);
  const [srcTable, setSrcTable] = useState("");
  const [srcName, setSrcName] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api<Page<Dataset>>("/datasets"),
    // Poll while any import is still working through the background pool.
    refetchInterval: (q) =>
      q.state.data?.items.some((d) =>
        ["uploaded", "profiling", "importing"].includes(d.status),
      )
        ? 2000
        : false,
  });

  const canWrite = user?.role === "admin" || user?.role === "analyst";

  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      if (name.trim()) fd.append("name", name.trim());
      return api<Dataset>("/datasets/upload?async=true", { method: "POST", body: fd });
    },
    onSuccess: (ds) => {
      toast.success(`"${ds.name}" queued — importing in the background`);
      setDialogOpen(false);
      setName("");
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      router.push(`/datasets/${ds.id}`);
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const previewSrc = useMutation({
    mutationFn: () =>
      api<{ tables: { schema: string; table: string }[] }>(
        "/datasets/source/preview",
        { method: "POST", body: JSON.stringify({ url: srcUrl }) },
      ),
    onSuccess: (d) => {
      setSrcTables(d.tables);
      if (d.tables.length) setSrcTable(d.tables[0].table);
    },
    onError: (e) => {
      setSrcTables(null);
      toast.error(apiErrorMessage(e));
    },
  });

  const importSrc = useMutation({
    mutationFn: () =>
      api<Dataset>("/datasets/import-source", {
        method: "POST",
        body: JSON.stringify({
          url: srcUrl, table: srcTable,
          name: srcName.trim() || undefined,
        }),
      }),
    onSuccess: (ds) => {
      toast.success(`"${ds.name}" imported — ${ds.rowCount} rows`);
      setSrcOpen(false);
      setSrcUrl(""); setSrcTables(null); setSrcName("");
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      router.push(`/datasets/${ds.id}`);
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Datasets</h1>
          <p className="text-sm text-muted-foreground">
            Upload, profile, and manage your business data
          </p>
        </div>
        {canWrite && (
          <div className="flex gap-2">
            <Dialog open={srcOpen} onOpenChange={setSrcOpen}>
              <DialogTrigger render={<Button variant="outline" />}>
                <DatabaseZap className="mr-2 size-4" />
                Import from database
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Import from a data source</DialogTitle>
                  <DialogDescription>
                    PostgreSQL or SQLite connection URL — used once to read
                    the table, never stored.
                  </DialogDescription>
                </DialogHeader>
                <div className="flex flex-col gap-4">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="src-url">Connection URL</Label>
                    <Input
                      id="src-url"
                      placeholder="postgresql://user:pass@host:5432/db"
                      value={srcUrl}
                      onChange={(e) => { setSrcUrl(e.target.value); setSrcTables(null); }}
                    />
                  </div>
                  <Button
                    variant="outline"
                    disabled={!srcUrl || previewSrc.isPending}
                    onClick={() => previewSrc.mutate()}
                  >
                    {previewSrc.isPending ? "Connecting..." : "Test connection & list tables"}
                  </Button>
                  {srcTables && (
                    <>
                      <div className="flex flex-col gap-1.5">
                        <Label>Table</Label>
                        <select
                          className="h-9 rounded-md border bg-background px-3 text-sm"
                          value={srcTable}
                          onChange={(e) => setSrcTable(e.target.value)}
                        >
                          {srcTables.map((t) => (
                            <option key={t.table} value={t.table}>
                              {t.schema}.{t.table}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="src-name">Display name (optional)</Label>
                        <Input
                          id="src-name"
                          value={srcName}
                          onChange={(e) => setSrcName(e.target.value)}
                        />
                      </div>
                    </>
                  )}
                </div>
                <DialogFooter>
                  <Button
                    disabled={!srcTable || importSrc.isPending}
                    onClick={() => importSrc.mutate()}
                  >
                    {importSrc.isPending ? "Importing..." : "Import table"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger render={<Button />}>
              <Upload className="mr-2 size-4" />
              Upload dataset
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Upload dataset</DialogTitle>
                <DialogDescription>
                  CSV or XLSX, up to 50 MB. We&apos;ll profile it automatically.
                </DialogDescription>
              </DialogHeader>
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="ds-name">Display name (optional)</Label>
                  <Input
                    id="ds-name"
                    placeholder="e.g. Q4 Sales"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="ds-file">File</Label>
                  <Input
                    id="ds-file"
                    ref={fileRef}
                    type="file"
                    accept=".csv,.xlsx"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  disabled={upload.isPending}
                  onClick={() => {
                    const f = fileRef.current?.files?.[0];
                    if (!f) {
                      toast.error("Choose a file first");
                      return;
                    }
                    upload.mutate(f);
                  }}
                >
                  {upload.isPending ? "Importing..." : "Upload & profile"}
                </Button>
              </DialogFooter>
            </DialogContent>
            </Dialog>
          </div>
        )}
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Rows</TableHead>
                <TableHead className="text-right">Cols</TableHead>
                <TableHead className="text-right">Size</TableHead>
                <TableHead>Quality</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Uploaded</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 4 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 8 }).map((__, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-16" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              {!isLoading && data?.items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8}>
                    <div className="flex flex-col items-center gap-2 py-14 text-center">
                      <Database className="size-8 text-muted-foreground/50" />
                      <p className="text-sm text-muted-foreground">
                        No datasets yet — upload a CSV or XLSX to get started.
                      </p>
                    </div>
                  </TableCell>
                </TableRow>
              )}
              {data?.items.map((ds) => (
                <TableRow
                  key={ds.id}
                  className="cursor-pointer"
                  onClick={() => router.push(`/datasets/${ds.id}`)}
                >
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <FileSpreadsheet className="size-4 text-muted-foreground" />
                      <span className="font-medium">{ds.name}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{ds.fileType}</Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatNumber(ds.rowCount)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {ds.columnCount}
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    {formatBytes(ds.fileSizeBytes)}
                  </TableCell>
                  <TableCell>
                    <QualityBadge score={ds.qualityScore} />
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={ds.status} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {new Date(ds.createdAt).toLocaleDateString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      {data && data.total > 0 && (
        <p className="text-xs text-muted-foreground">{data.total} dataset(s)</p>
      )}
    </div>
  );
}
