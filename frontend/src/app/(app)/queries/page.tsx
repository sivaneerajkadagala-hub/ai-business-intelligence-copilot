import type { Metadata } from "next";
import { FileCode2 } from "lucide-react";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Saved Queries" };

export default function QueriesPage() {
  return (
    <PagePlaceholder
      title="Saved Queries"
      description="Your library of saved analytics queries"
      icon={FileCode2}
    />
  );
}
