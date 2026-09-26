import type { Metadata } from "next";
import Link from "next/link";
import {
  ChartLine,
  Database,
  FileCode2,
  LayoutGrid,
  Upload,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Dashboard" };

const KPI_CARDS = [
  { label: "Total Datasets", icon: Database },
  { label: "Total Records", icon: ChartLine },
  { label: "Active Dashboards", icon: LayoutGrid },
  { label: "Queries Executed", icon: FileCode2 },
];

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Business intelligence overview
          </p>
        </div>
        <Button render={<Link href="/datasets" />}>
          <Upload className="mr-2 size-4" />
          Upload dataset
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {KPI_CARDS.map((kpi) => (
          <Card key={kpi.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardDescription className="text-sm font-medium">
                {kpi.label}
              </CardDescription>
              <kpi.icon className="size-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-semibold">—</div>
              <p className="text-xs text-muted-foreground">
                Populates once data is connected
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {["Revenue trend", "Sales by region"].map((title) => (
          <Card key={title} className="min-h-[280px]">
            <CardHeader>
              <CardTitle className="text-base">{title}</CardTitle>
            </CardHeader>
            <CardContent className="flex h-48 flex-col items-center justify-center gap-2 text-center">
              <ChartLine className="size-8 text-muted-foreground/50" />
              <p className="text-sm text-muted-foreground">
                Charts render here once the analytics API is live (Phase 4)
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
