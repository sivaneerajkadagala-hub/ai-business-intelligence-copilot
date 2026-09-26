import type { Metadata } from "next";
import { Database } from "lucide-react";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Datasets" };

export default function DatasetsPage() {
  return (
    <PagePlaceholder
      title="Datasets"
      description="Upload, profile, and manage your business data"
      icon={Database}
    />
  );
}
