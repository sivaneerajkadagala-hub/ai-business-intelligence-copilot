import type { Metadata } from "next";
import { ChartLine } from "lucide-react";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Analytics" };

export default function AnalyticsPage() {
  return (
    <PagePlaceholder
      title="Analytics"
      description="KPIs, trends, anomaly detection, and forecasting"
      icon={ChartLine}
    />
  );
}
