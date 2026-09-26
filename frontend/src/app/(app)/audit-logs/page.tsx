"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ScrollText } from "lucide-react";

import { useAuth } from "@/lib/auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type AuditEntry = {
  id: string;
  userId: string | null;
  actor: string | null;
  action: string;
  resourceType: string | null;
  resourceId: string | null;
  meta: Record<string, unknown> | null;
  ip: string | null;
  createdAt: string | null;
};
type AuditPage = { items: AuditEntry[]; total: number; page: number; pages: number };

const ACTION_COLORS: Record<string, "destructive" | "secondary" | "default" | "outline"> = {
  "auth.login_failed": "destructive",
  "security.refresh_reuse": "destructive",
  "users.deactivate": "default",
};

export default function AuditLogsPage() {
  const { api } = useAuth();
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["audit-logs", page, actionFilter],
    queryFn: () =>
      api<AuditPage>(
        `/audit-logs?page=${page}&page_size=50${
          actionFilter ? `&action=${encodeURIComponent(actionFilter)}` : ""
        }`,
      ),
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Audit Logs</h1>
          <p className="text-sm text-muted-foreground">
            Security-relevant actions across the workspace
          </p>
        </div>
        <Input
          value={actionFilter}
          onChange={(e) => {
            setActionFilter(e.target.value);
            setPage(1);
          }}
          placeholder="Filter by action (e.g. copilot, auth, datasets)"
          className="w-72"
        />
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Resource</TableHead>
                <TableHead>Details</TableHead>
                <TableHead>IP</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 8 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={6}><Skeleton className="h-5" /></TableCell>
                  </TableRow>
                ))}
              {!isLoading && !data?.items.length && (
                <TableRow>
                  <TableCell colSpan={6} className="py-10 text-center text-muted-foreground">
                    <ScrollText className="mx-auto mb-2 size-6 opacity-40" />
                    No audit events match.
                  </TableCell>
                </TableRow>
              )}
              {data?.items.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {e.createdAt ? new Date(e.createdAt).toLocaleString() : "—"}
                  </TableCell>
                  <TableCell className="text-sm">{e.actor ?? "system"}</TableCell>
                  <TableCell>
                    <Badge variant={ACTION_COLORS[e.action] ?? "secondary"}>
                      {e.action}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs">
                    {e.resourceType}
                    {e.resourceId && (
                      <span className="block max-w-36 truncate font-mono text-muted-foreground">
                        {e.resourceId}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="max-w-64">
                    <code className="block truncate text-xs text-muted-foreground">
                      {e.meta ? JSON.stringify(e.meta) : "—"}
                    </code>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {e.ip ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {data && data.pages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Page {data.page} of {data.pages} · {data.total} events
          </span>
          <div className="flex gap-1">
            <Button size="icon" variant="outline" disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}>
              <ChevronLeft className="size-4" />
            </Button>
            <Button size="icon" variant="outline" disabled={page >= data.pages}
                    onClick={() => setPage((p) => p + 1)}>
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
