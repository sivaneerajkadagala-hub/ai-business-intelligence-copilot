"use client";

import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth";
import { apiErrorMessage } from "@/lib/api";
import type { DatasetColumn } from "@/lib/datasets";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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

type Operation = Record<string, unknown>;

type PreviewResult = {
  rowsBefore: number;
  rowsAfter: number;
  report: { op: string; rowsBefore: number; rowsAfter: number; rowsAffected: number }[];
  afterSample: Record<string, unknown>[];
};

const TARGET_TYPES = ["string", "integer", "float", "boolean", "date", "datetime"];
const FILL_STRATEGIES = ["value", "mean", "median", "mode"];

function ColumnSelect({
  value,
  onChange,
  columns,
}: {
  value: string;
  onChange: (v: string) => void;
  columns: DatasetColumn[];
}) {
  return (
    <Select value={value || null} onValueChange={(v) => onChange(v as string)}>
      <SelectTrigger size="sm" className="w-44">
        <SelectValue placeholder="Select column" />
      </SelectTrigger>
      <SelectContent>
        {columns.map((c) => (
          <SelectItem key={c.normalizedName} value={c.normalizedName}>
            {c.normalizedName}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function OpRow({
  label,
  hint,
  checked,
  onCheck,
  children,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onCheck: (v: boolean) => void;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-md border p-3">
      <div className="flex items-center gap-2">
        <Checkbox checked={checked} onCheckedChange={(v) => onCheck(v === true)} />
        <Label className="cursor-pointer font-medium" onClick={() => onCheck(!checked)}>
          {label}
        </Label>
        <span className="text-xs text-muted-foreground">{hint}</span>
      </div>
      {checked && children && (
        <div className="flex flex-wrap items-center gap-2 pl-6">{children}</div>
      )}
    </div>
  );
}

export function CleanDialog({
  datasetId,
  versionId,
  columns,
  open,
  onOpenChange,
  onApplied,
}: {
  datasetId: string;
  versionId: string;
  columns: DatasetColumn[];
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onApplied: () => void;
}) {
  const { api } = useAuth();
  const [ops, setOps] = useState({
    dropNulls: false,
    dropDuplicates: false,
    fillNulls: false,
    cast: false,
    rename: false,
    normalizeDates: false,
    removeOutliers: false,
  });
  const [cfg, setCfg] = useState({
    fillColumn: "",
    fillStrategy: "value",
    fillValue: "",
    castColumn: "",
    castTo: "float",
    renameColumn: "",
    renameTo: "",
    dateColumn: "",
    outlierColumn: "",
    outlierMethod: "iqr",
  });
  const [preview, setPreview] = useState<PreviewResult | null>(null);

  const operations = useMemo<Operation[]>(() => {
    const list: Operation[] = [];
    if (ops.dropNulls) list.push({ op: "drop_nulls" });
    if (ops.dropDuplicates) list.push({ op: "drop_duplicates" });
    if (ops.fillNulls && cfg.fillColumn) {
      list.push({
        op: "fill_nulls",
        column: cfg.fillColumn,
        strategy: cfg.fillStrategy,
        ...(cfg.fillStrategy === "value" ? { value: cfg.fillValue } : {}),
      });
    }
    if (ops.cast && cfg.castColumn)
      list.push({ op: "cast", column: cfg.castColumn, to: cfg.castTo });
    if (ops.rename && cfg.renameColumn && cfg.renameTo)
      list.push({ op: "rename", column: cfg.renameColumn, newName: cfg.renameTo });
    if (ops.normalizeDates && cfg.dateColumn)
      list.push({ op: "normalize_dates", column: cfg.dateColumn });
    if (ops.removeOutliers && cfg.outlierColumn)
      list.push({
        op: "remove_outliers",
        column: cfg.outlierColumn,
        method: cfg.outlierMethod,
      });
    return list;
  }, [ops, cfg]);

  const previewMutation = useMutation({
    mutationFn: () =>
      api<PreviewResult>(`/datasets/${datasetId}/clean/preview`, {
        method: "POST",
        body: JSON.stringify({ versionId, operations }),
      }),
    onSuccess: setPreview,
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const applyMutation = useMutation({
    mutationFn: () =>
      api(`/datasets/${datasetId}/clean`, {
        method: "POST",
        body: JSON.stringify({ versionId, operations }),
      }),
    onSuccess: () => {
      toast.success("Cleaned version created");
      setPreview(null);
      onOpenChange(false);
      onApplied();
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create cleaned version</DialogTitle>
          <DialogDescription>
            Operations produce a new version — the original is never modified.
          </DialogDescription>
        </DialogHeader>

        <div className="flex max-h-[50vh] flex-col gap-2 overflow-y-auto pr-1">
          <OpRow
            label="Drop missing values"
            hint="Remove rows containing nulls"
            checked={ops.dropNulls}
            onCheck={(v) => setOps({ ...ops, dropNulls: v })}
          />
          <OpRow
            label="Drop duplicates"
            hint="Remove exact duplicate rows"
            checked={ops.dropDuplicates}
            onCheck={(v) => setOps({ ...ops, dropDuplicates: v })}
          />
          <OpRow
            label="Fill missing values"
            hint="Impute nulls in a column"
            checked={ops.fillNulls}
            onCheck={(v) => setOps({ ...ops, fillNulls: v })}
          >
            <ColumnSelect columns={columns}
              value={cfg.fillColumn}
              onChange={(v) => setCfg({ ...cfg, fillColumn: v })}
            />
            <Select
              value={cfg.fillStrategy}
              onValueChange={(v) => setCfg({ ...cfg, fillStrategy: v as string })}
            >
              <SelectTrigger size="sm" className="w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {FILL_STRATEGIES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {cfg.fillStrategy === "value" && (
              <Input
                className="w-32"
                placeholder="value"
                value={cfg.fillValue}
                onChange={(e) => setCfg({ ...cfg, fillValue: e.target.value })}
              />
            )}
          </OpRow>
          <OpRow
            label="Cast column type"
            hint="Convert data type"
            checked={ops.cast}
            onCheck={(v) => setOps({ ...ops, cast: v })}
          >
            <ColumnSelect columns={columns}
              value={cfg.castColumn}
              onChange={(v) => setCfg({ ...cfg, castColumn: v })}
            />
            <span className="text-xs text-muted-foreground">to</span>
            <Select
              value={cfg.castTo}
              onValueChange={(v) => setCfg({ ...cfg, castTo: v as string })}
            >
              <SelectTrigger size="sm" className="w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TARGET_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </OpRow>
          <OpRow
            label="Rename column"
            hint="Rename a column"
            checked={ops.rename}
            onCheck={(v) => setOps({ ...ops, rename: v })}
          >
            <ColumnSelect columns={columns}
              value={cfg.renameColumn}
              onChange={(v) => setCfg({ ...cfg, renameColumn: v })}
            />
            <Input
              className="w-40"
              placeholder="new name"
              value={cfg.renameTo}
              onChange={(e) => setCfg({ ...cfg, renameTo: e.target.value })}
            />
          </OpRow>
          <OpRow
            label="Normalize dates"
            hint="Parse & normalize a date column"
            checked={ops.normalizeDates}
            onCheck={(v) => setOps({ ...ops, normalizeDates: v })}
          >
            <ColumnSelect columns={columns}
              value={cfg.dateColumn}
              onChange={(v) => setCfg({ ...cfg, dateColumn: v })}
            />
          </OpRow>
          <OpRow
            label="Remove outliers"
            hint="Drop outlier rows in a numeric column"
            checked={ops.removeOutliers}
            onCheck={(v) => setOps({ ...ops, removeOutliers: v })}
          >
            <ColumnSelect columns={columns}
              value={cfg.outlierColumn}
              onChange={(v) => setCfg({ ...cfg, outlierColumn: v })}
            />
            <Select
              value={cfg.outlierMethod}
              onValueChange={(v) => setCfg({ ...cfg, outlierMethod: v as string })}
            >
              <SelectTrigger size="sm" className="w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="iqr">IQR</SelectItem>
                <SelectItem value="zscore">Z-score</SelectItem>
              </SelectContent>
            </Select>
          </OpRow>
        </div>

        {preview && (
          <div className="rounded-md border bg-muted/40 p-3 text-sm">
            <p className="font-medium">
              {preview.rowsBefore.toLocaleString()} → {preview.rowsAfter.toLocaleString()} rows
            </p>
            <ul className="mt-1 text-xs text-muted-foreground">
              {preview.report.map((r, i) => (
                <li key={i}>
                  {r.op}: −{r.rowsAffected.toLocaleString()} rows
                </li>
              ))}
            </ul>
          </div>
        )}

        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            disabled={operations.length === 0 || previewMutation.isPending}
            onClick={() => previewMutation.mutate()}
          >
            {previewMutation.isPending ? "Computing..." : "Preview changes"}
          </Button>
          <Button
            disabled={operations.length === 0 || applyMutation.isPending}
            onClick={() => applyMutation.mutate()}
          >
            {applyMutation.isPending ? "Applying..." : "Apply as new version"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
