import type { Metadata } from "next";
import { ScrollText } from "lucide-react";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Audit Logs" };

export default function AuditLogsPage() {
  return (
    <PagePlaceholder
      title="Audit Logs"
      description="System activity and security audit trail"
      icon={ScrollText}
    />
  );
}
