import type { Metadata } from "next";
import { FileText } from "lucide-react";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Reports" };

export default function ReportsPage() {
  return (
    <PagePlaceholder
      title="Reports"
      description="Generate and export business reports"
      icon={FileText}
    />
  );
}
