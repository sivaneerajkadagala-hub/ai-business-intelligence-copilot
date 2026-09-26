export type Dataset = {
  id: string;
  name: string;
  description: string | null;
  ownerId: string;
  status: "uploaded" | "profiling" | "importing" | "ready" | "failed";
  originalFilename: string;
  fileType: "csv" | "xlsx";
  fileSizeBytes: number;
  rowCount: number;
  columnCount: number;
  qualityScore: number | null;
  isShared: boolean;
  currentVersionId: string | null;
  createdAt: string;
  updatedAt: string;
  versions?: DatasetVersion[];
};

export type DatasetVersion = {
  id: string;
  versionNo: number;
  kind: "original" | "cleaned";
  operations: Record<string, unknown>[] | null;
  tableName: string;
  rowCount: number;
  columnCount: number;
  createdAt: string;
};

export type DatasetColumn = {
  name: string;
  normalizedName: string;
  ordinal: number;
  inferredType: string;
  nullCount: number;
  distinctCount: number;
  minValue: string | null;
  maxValue: string | null;
  mean: number | null;
  median: number | null;
  stddev: number | null;
  outlierCount: number | null;
  topValues: { value: string | null; count: number }[] | null;
};

export type Page<T> = { items: T[]; total: number; page: number; pages: number };

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}
