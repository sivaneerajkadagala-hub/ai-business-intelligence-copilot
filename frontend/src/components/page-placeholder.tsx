import type { LucideIcon } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function PagePlaceholder({
  title,
  description,
  icon: Icon,
}: {
  title: string;
  description: string;
  icon: LucideIcon;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <Card className="flex min-h-[320px] items-center justify-center border-dashed">
        <CardHeader className="items-center text-center">
          <div className="mb-2 flex size-12 items-center justify-center rounded-full bg-muted">
            <Icon className="size-6 text-muted-foreground" />
          </div>
          <CardTitle className="text-base">Coming in a later phase</CardTitle>
          <CardDescription className="max-w-sm">
            This section is scaffolded and will be implemented as the build
            progresses through the project phases.
          </CardDescription>
        </CardHeader>
        <CardContent />
      </Card>
    </div>
  );
}
