import type { Metadata } from "next";
import { Bot } from "lucide-react";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "BI Copilot" };

export default function CopilotPage() {
  return (
    <PagePlaceholder
      title="BI Copilot"
      description="Ask questions about your data in natural language"
      icon={Bot}
    />
  );
}
