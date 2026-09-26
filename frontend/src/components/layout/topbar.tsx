"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { SidebarContent } from "@/components/layout/app-sidebar";

function titleCase(segment: string) {
  return segment
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function Topbar() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b bg-background px-4">
      <Sheet>
        <SheetTrigger
          render={
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              aria-label="Open navigation"
            />
          }
        >
          <Menu className="size-5" />
        </SheetTrigger>
        <SheetContent side="left" className="w-64 p-0">
          <SidebarContent />
        </SheetContent>
      </Sheet>

      <nav className="hidden items-center gap-1 text-sm text-muted-foreground md:flex">
        <Link href="/dashboard" className="hover:text-foreground">
          Home
        </Link>
        {segments.map((seg, i) => (
          <span key={i} className="flex items-center gap-1">
            <span>/</span>
            <span
              className={
                i === segments.length - 1 ? "text-foreground" : undefined
              }
            >
              {titleCase(seg)}
            </span>
          </span>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-2">
        <div className="relative hidden sm:block">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input
            placeholder="Search..."
            className="w-48 pl-8 lg:w-64"
            aria-label="Global search"
          />
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                variant="ghost"
                size="icon"
                className="rounded-full"
                aria-label="Account menu"
              />
            }
          >
            <Avatar className="size-8">
              <AvatarFallback>--</AvatarFallback>
            </Avatar>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>Account</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem render={<Link href="/settings" />}>
              Settings
            </DropdownMenuItem>
            <DropdownMenuItem render={<Link href="/login" />}>
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
