"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileCode2, Loader2, Play, Trash2, Users } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth";
import { apiErrorMessage } from "@/lib/api";
import type { Dataset, Page } from "@/lib/datasets";
import type { SavedQuery } from "@/lib/workspace";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
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

type RunResult = {
  columns: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
  durationMs: number;
};

export default function QueriesPage() {
  const { api, user } = useAuth();
  const queryClient = useQueryClient();
  const [result, setResult] = useState<{ queryId: string; res: RunResult } | null>(null);
  const canWrite = user?.role === "admin" || user?.role === "analyst";

  const { data: queries, isLoading } = useQuery({
    queryKey: ["saved-queries"],
    queryFn: () => api<SavedQuery[]>("/queries"),
  });
  const { data: datasets } = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api<Page<Dataset>>("/datasets?page_size=100"),
  });
  const dsName = (id: string) =>
    datasets?.items.find((d) => d.id === id)?.name ?? "—";

  const runMutation = useMutation({
    mutationFn: (id: string) => api<RunResult>(`/queries/${id}/run`, { method: "POST" }),
    onSuccess: (res, id) => {
      setResult({ queryId: id, res });
      queryClient.invalidateQueries({ queryKey: ["saved-queries"] });
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api(`/queries/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Query deleted");
      queryClient.invalidateQueries({ queryKey: ["saved-queries"] });
      setResult(null);
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Saved Queries</h1>
        <p className="text-sm text-muted-foreground">
          Queries saved from the copilot — validated &amp; re-executed against live data
        </p>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Dataset</TableHead>
                <TableHead>SQL</TableHead>
                <TableHead>Last run</TableHead>
                <TableHead className="w-28" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={5}><Skeleton className="h-5" /></TableCell>
                  </TableRow>
                ))}
              {!isLoading && !queries?.length && (
                <TableRow>
                  <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                    <FileCode2 className="mx-auto mb-2 size-6 opacity-40" />
                    No saved queries — save one from a copilot answer.
                  </TableCell>
                </TableRow>
              )}
              {queries?.map((q) => (
                <TableRow key={q.id}>
                  <TableCell className="font-medium">
                    {q.name}
                    {q.isShared && (
                      <Badge variant="secondary" className="ml-2">
                        <Users className="mr-1 size-3" /> shared
                      </Badge>
                    )}
                    {q.question && (
                      <p className="mt-0.5 text-xs font-normal text-muted-foreground">
                        {q.question}
                      </p>
                    )}
                  </TableCell>
                  <TableCell>{dsName(q.datasetId)}</TableCell>
                  <TableCell className="max-w-72">
                    <code className="block truncate text-xs text-muted-foreground">
                      {q.sql}
                    </code>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {q.lastRunAt
                      ? new Date(q.lastRunAt).toLocaleString()
                      : "never"}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        title="Run"
                        disabled={runMutation.isPending}
                        onClick={() => runMutation.mutate(q.id)}
                      >
                        {runMutation.isPending && runMutation.variables === q.id ? (
                          <Loader2 className="size-4 animate-spin" />
                        ) : (
                          <Play className="size-4" />
                        )}
                      </Button>
                      {canWrite && (
                        <Button
                          size="icon"
                          variant="ghost"
                          title="Delete"
                          onClick={() => deleteMutation.mutate(q.id)}
                        >
                          <Trash2 className="size-4 text-destructive" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              Results — {result.res.rowCount.toLocaleString()} rows ·{" "}
              {result.res.durationMs}ms
            </CardTitle>
          </CardHeader>
          <CardContent className="max-h-96 overflow-auto p-0 pb-2">
            <Table>
              <TableHeader>
                <TableRow>
                  {result.res.columns.map((c) => (
                    <TableHead key={c} className="text-xs">{c}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.res.rows.slice(0, 50).map((r, i) => (
                  <TableRow key={i}>
                    {result.res.columns.map((c) => (
                      <TableCell key={c} className="text-sm">
                        {r[c] == null ? "—" : String(r[c])}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
