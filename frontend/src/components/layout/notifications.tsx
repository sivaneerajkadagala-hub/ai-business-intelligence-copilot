"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";

import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

type Notification = {
  id: string;
  type: string;
  title: string;
  body: string | null;
  link: string | null;
  readAt: string | null;
  createdAt: string | null;
};

const DOT: Record<string, string> = {
  "ingest.success": "bg-emerald-500",
  "ingest.failed": "bg-red-500",
  "report.ready": "bg-blue-500",
  "insights.warning": "bg-amber-500",
};

export function NotificationBell() {
  const { api } = useAuth();
  const queryClient = useQueryClient();

  const { data: unread } = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => api<{ count: number }>("/notifications/unread-count"),
    refetchInterval: 30_000,
  });
  const { data: notes } = useQuery({
    queryKey: ["notifications", "recent"],
    queryFn: () => api<Notification[]>("/notifications?limit=10"),
    refetchInterval: 30_000,
  });

  const markAll = useMutation({
    mutationFn: () => api("/notifications/read-all", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const markOne = useMutation({
    mutationFn: (id: string) =>
      api(`/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const count = unread?.count ?? 0;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            className="relative"
            aria-label="Notifications"
          />
        }
      >
        <Bell className="size-5" />
        {count > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-semibold text-white">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel className="flex items-center justify-between">
          Notifications
          {count > 0 && (
            <button
              className="flex items-center gap-1 text-xs font-normal text-muted-foreground hover:text-foreground"
              onClick={() => markAll.mutate()}
            >
              <CheckCheck className="size-3.5" /> Mark all read
            </button>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {!notes?.length && (
          <p className="px-2 py-6 text-center text-sm text-muted-foreground">
            No notifications
          </p>
        )}
        {notes?.map((n) => (
          <DropdownMenuItem
            key={n.id}
            className="items-start gap-2 py-2"
            onClick={() => !n.readAt && markOne.mutate(n.id)}
            render={n.link ? <Link href={n.link} /> : undefined}
          >
            <span
              className={`mt-1.5 size-2 shrink-0 rounded-full ${
                DOT[n.type] ?? "bg-muted-foreground"
              } ${n.readAt ? "opacity-30" : ""}`}
            />
            <span className="flex min-w-0 flex-col">
              <span
                className={`text-sm leading-snug ${n.readAt ? "text-muted-foreground" : "font-medium"}`}
              >
                {n.title}
              </span>
              {n.body && (
                <span className="truncate text-xs text-muted-foreground">{n.body}</span>
              )}
              {n.createdAt && (
                <span className="text-[10px] text-muted-foreground/70">
                  {new Date(n.createdAt).toLocaleString()}
                </span>
              )}
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
