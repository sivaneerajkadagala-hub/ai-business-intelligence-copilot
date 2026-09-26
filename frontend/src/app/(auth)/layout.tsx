import Link from "next/link";
import { BarChart3 } from "lucide-react";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-muted/40 p-4">
      <Link
        href="/"
        className="mb-6 flex items-center gap-2 text-foreground"
      >
        <div className="flex size-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <BarChart3 className="size-5" />
        </div>
        <span className="text-lg font-semibold">BI Copilot</span>
      </Link>
      {children}
      <p className="mt-8 text-center text-xs text-muted-foreground">
        AI Business Intelligence Copilot
      </p>
    </div>
  );
}
