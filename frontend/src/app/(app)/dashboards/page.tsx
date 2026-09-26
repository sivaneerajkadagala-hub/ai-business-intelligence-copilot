import type { Metadata } from "next";
import { LayoutGrid } from "lucide-react";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Dashboards" };

export default function DashboardsPage() {
  return (
    <PagePlaceholder
      title="Dashboards"
      description="Build and manage custom dashboards"
      icon={LayoutGrid}
    />
  );
}
