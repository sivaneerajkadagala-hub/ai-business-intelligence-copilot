export type Dashboard = {
  id: string;
  ownerId: string;
  name: string;
  description: string | null;
  isShared: boolean;
  createdAt: string;
  updatedAt: string;
};

export type WidgetType = "kpi" | "line" | "bar" | "pie" | "table";

export type Widget = {
  id: string;
  type: WidgetType;
  title: string;
  config: {
    datasetId?: string;
    kpiId?: string;
    dateColumn?: string;
    metricColumn?: string;
    dimension?: string;
    agg?: string;
    bucket?: string;
  };
  position: { x: number; y: number; w: number; h: number };
  sortOrder: number;
};

export type DashboardDetail = Dashboard & { widgets: Widget[] };

export type SavedQuery = {
  id: string;
  name: string;
  question: string | null;
  sql: string;
  datasetId: string;
  createdBy: string | null;
  isShared: boolean;
  lastRunAt: string | null;
  createdAt: string;
};

export type Report = {
  id: string;
  name: string;
  format: "pdf" | "csv";
  status: "generating" | "ready" | "failed";
  createdAt: string;
};
