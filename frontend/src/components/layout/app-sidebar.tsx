"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3 } from "lucide-react";

import { NAV_GROUPS } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export function SidebarContent() {
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center gap-2 border-b px-4">
        <div className="flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <BarChart3 className="size-4" />
        </div>
        <div className="flex flex-col leading-none">
          <span className="text-sm font-semibold">BI Copilot</span>
          <span className="text-xs text-muted-foreground">
            Intelligence Platform
          </span>
        </div>
      </div>
      <ScrollArea className="flex-1 px-3 py-4">
        <nav className="flex flex-col gap-4">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <p className="mb-1 px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {group.label}
              </p>
              <div className="flex flex-col gap-0.5">
                {group.items.map((item) => {
                  const active =
                    pathname === item.href ||
                    pathname.startsWith(item.href + "/");
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={cn(
                        "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                        active
                          ? "bg-accent font-medium text-accent-foreground"
                          : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                      )}
                    >
                      <item.icon className="size-4 shrink-0" />
                      {item.title}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </ScrollArea>
      <Separator />
      <div className="p-3 text-xs text-muted-foreground">
        v0.1.0 &middot; Phase 1 scaffold
      </div>
    </div>
  );
}

export function AppSidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r bg-background md:block">
      <SidebarContent />
    </aside>
  );
}
