"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Plus } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth";
import { apiErrorMessage, saveBlob } from "@/lib/api";
import type { Dataset, Page } from "@/lib/datasets";
import type { Report } from "@/lib/workspace";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const STATUS_BADGE: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  ready: "secondary",
  generating: "outline",
  failed: "destructive",
};

export default function ReportsPage() {
  const { api, download, user } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [format, setFormat] = useState<"pdf" | "csv">("pdf");
  const [name, setName] = useState("");
  const canWrite = user?.role === "admin" || user?.role === "analyst";

  const { data: reports, isLoading } = useQuery({
    queryKey: ["reports"],
    queryFn: () => api<Report[]>("/reports"),
    refetchInterval: (q) =>
      q.state.data?.some((r) => r.status === "generating") ? 2000 : false,
  });
  const { data: datasets } = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api<Page<Dataset>>("/datasets?page_size=100"),
    enabled: open,
  });
  const readyDatasets = datasets?.items.filter((d) => d.status === "ready") ?? [];
  const selDataset = readyDatasets.find((d) => d.id === datasetId) ?? readyDatasets[0];

  const generateMutation = useMutation({
    mutationFn: () =>
      api<Report>("/reports/generate", {
        method: "POST",
        body: JSON.stringify({
          datasetId: selDataset?.id,
          format,
          name: name.trim() || undefined,
        }),
      }),
    onSuccess: () => {
      toast.success("Report generated");
      setOpen(false);
      setName("");
      queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  async function downloadReport(r: Report) {
    try {
      const blob = await download(`/reports/${r.id}/download`);
      saveBlob(blob, `${r.name.replace(/\s+/g, "_")}.${r.format}`);
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Reports</h1>
          <p className="text-sm text-muted-foreground">
            PDF summaries &amp; CSV exports of your datasets
          </p>
        </div>
        {canWrite && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger render={<Button />}>
              <Plus className="mr-2 size-4" /> Generate report
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Generate report</DialogTitle>
              </DialogHeader>
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label>Name (optional)</Label>
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Monthly exec summary"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>Dataset</Label>
                    <Select value={selDataset?.id ?? null} onValueChange={(v) => setDatasetId(v as string)}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {readyDatasets.map((d) => (
                          <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>Format</Label>
                    <Select value={format} onValueChange={(v) => setFormat(v as "pdf" | "csv")}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="pdf">PDF summary</SelectItem>
                        <SelectItem value="csv">CSV export</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <Button
                  onClick={() => generateMutation.mutate()}
                  disabled={!selDataset || generateMutation.isPending}
                >
                  Generate
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Format</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={5}><Skeleton className="h-5" /></TableCell>
                  </TableRow>
                ))}
              {!isLoading && !reports?.length && (
                <TableRow>
                  <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                    <FileText className="mx-auto mb-2 size-6 opacity-40" />
                    No reports yet.
                  </TableCell>
                </TableRow>
              )}
              {reports?.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-medium">{r.name}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{r.format.toUpperCase()}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={STATUS_BADGE[r.status] ?? "outline"}>{r.status}</Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(r.createdAt).toLocaleString()}
                  </TableCell>
                  <TableCell>
                    {r.status === "ready" && (
                      <Button size="icon" variant="ghost" title="Download"
                              onClick={() => downloadReport(r)}>
                        <Download className="size-4" />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
