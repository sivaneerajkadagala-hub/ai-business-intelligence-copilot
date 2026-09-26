"use client";

import { useState } from "react";
import { ChevronDown, Code2 } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChatMessage } from "@/lib/copilot";
import { fmtMetric } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const COLORS = ["#2563eb", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444", "#06b6d4"];
const AXIS = { fontSize: 11, fill: "var(--muted-foreground)" } as const;

function fmtAxis(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return String(v);
}

function AnswerChart({ msg }: { msg: ChatMessage }) {
  const spec = msg.chartSpec;
  const snap = msg.resultSnapshot;
  if (!spec || !snap?.rows.length || spec.type === "number") return null;

  const data = snap.rows.map((r) => ({
    label: String(r[spec.x ?? "label"] ?? ""),
    value: Number(r[spec.y ?? "value"] ?? 0),
    t: String(r[spec.x ?? "t"] ?? ""),
  }));

  if (spec.type === "line") {
    return (
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data.map((d) => ({ t: d.t, value: d.value }))}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="t" tick={AXIS} tickLine={false} axisLine={false} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmtAxis} />
          <Tooltip formatter={(v) => [fmtMetric(Number(v)), "value"]} />
          <Area type="monotone" dataKey="value" stroke={COLORS[0]} fill={COLORS[0]} fillOpacity={0.15} strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmtAxis} />
        <Tooltip formatter={(v) => [fmtMetric(Number(v)), "value"]} />
        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
          {data.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function AssistantMessage({ msg }: { msg: ChatMessage }) {
  const [showSql, setShowSql] = useState(false);
  const snap = msg.resultSnapshot;
  const isNumber = msg.chartSpec?.type === "number" && snap?.rows.length === 1;

  return (
    <div className="mr-auto w-full max-w-3xl rounded-lg border bg-card p-4">
      <p className="font-medium">{msg.content}</p>
      {msg.explanation && (
        <p className="mt-1.5 text-sm text-muted-foreground">{msg.explanation}</p>
      )}

      {isNumber && (
        <div className="mt-3 text-3xl font-semibold tracking-tight">
          {fmtMetric(
            Number(snap.rows[0][snap.columns[0]]),
          )}
        </div>
      )}

      <div className="mt-3">
        <AnswerChart msg={msg} />
      </div>

      {snap && !isNumber && (
        <div className="mt-3 overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                {snap.columns.map((c) => (
                  <TableHead key={c} className="whitespace-nowrap text-xs">
                    {c}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {snap.rows.slice(0, 10).map((row, i) => (
                <TableRow key={i}>
                  {snap.columns.map((c) => (
                    <TableCell key={c} className="whitespace-nowrap text-sm">
                      {row[c] == null ? "—" : String(row[c])}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {snap.rowCount > 10 && (
            <p className="border-t px-3 py-1.5 text-xs text-muted-foreground">
              Showing 10 of {snap.rowCount.toLocaleString()} rows
            </p>
          )}
        </div>
      )}

      {msg.sql && (
        <div className="mt-3">
          <Button
            variant="ghost"
            size="sm"
            className="-ml-2 text-xs text-muted-foreground"
            onClick={() => setShowSql(!showSql)}
          >
            <Code2 className="mr-1.5 size-3.5" />
            {showSql ? "Hide" : "Show"} generated SQL
            <ChevronDown
              className={`ml-1 size-3.5 transition-transform ${showSql ? "rotate-180" : ""}`}
            />
          </Button>
          {showSql && (
            <pre className="mt-1 overflow-x-auto rounded-md bg-muted p-3 text-xs">
              {msg.sql}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
