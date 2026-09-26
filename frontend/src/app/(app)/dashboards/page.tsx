"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Copy, LayoutGrid, Plus, Trash2, Users } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth";
import { apiErrorMessage } from "@/lib/api";
import type { Dashboard } from "@/lib/workspace";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

const schema = z.object({
  name: z.string().min(2, "Give it a name"),
  description: z.string().optional(),
});
type Form = z.infer<typeof schema>;

export default function DashboardsPage() {
  const { api, user } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const canWrite = user?.role === "admin" || user?.role === "analyst";

  const { data: dashboards, isLoading } = useQuery({
    queryKey: ["dashboards"],
    queryFn: () => api<Dashboard[]>("/dashboards"),
  });

  const form = useForm<Form>({ resolver: zodResolver(schema) });
  const createMutation = useMutation({
    mutationFn: (f: Form) =>
      api<Dashboard>("/dashboards", { method: "POST", body: JSON.stringify(f) }),
    onSuccess: (d) => {
      toast.success("Dashboard created");
      setOpen(false);
      form.reset();
      queryClient.invalidateQueries({ queryKey: ["dashboards"] });
      router.push(`/dashboards/${d.id}`);
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api(`/dashboards/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Dashboard deleted");
      queryClient.invalidateQueries({ queryKey: ["dashboards"] });
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const duplicateMutation = useMutation({
    mutationFn: (id: string) =>
      api(`/dashboards/${id}/duplicate`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Dashboard duplicated");
      queryClient.invalidateQueries({ queryKey: ["dashboards"] });
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboards</h1>
          <p className="text-sm text-muted-foreground">
            Composable widget boards over your datasets
          </p>
        </div>
        {canWrite && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger render={<Button />}>
              <Plus className="mr-2 size-4" /> New dashboard
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>New dashboard</DialogTitle>
              </DialogHeader>
              <form
                className="flex flex-col gap-4"
                onSubmit={form.handleSubmit((f) => createMutation.mutate(f))}
              >
                <div className="flex flex-col gap-2">
                  <Label htmlFor="name">Name</Label>
                  <Input id="name" placeholder="Executive overview" {...form.register("name")} />
                  {form.formState.errors.name && (
                    <p className="text-sm text-destructive">{form.formState.errors.name.message}</p>
                  )}
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="description">Description (optional)</Label>
                  <Input id="description" {...form.register("description")} />
                </div>
                <Button type="submit" disabled={createMutation.isPending}>
                  Create
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {isLoading &&
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-36" />)}
        {!isLoading && !dashboards?.length && (
          <Card className="col-span-full">
            <CardHeader className="items-center py-14 text-center">
              <LayoutGrid className="size-8 text-muted-foreground/50" />
              <CardTitle className="text-base">No dashboards yet</CardTitle>
              <CardDescription>
                Create one to assemble KPIs, charts and tables in a grid.
              </CardDescription>
            </CardHeader>
          </Card>
        )}
        {dashboards?.map((d) => (
          <Card key={d.id} className="transition-shadow hover:shadow-md">
            <CardHeader>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <CardTitle className="truncate text-base">
                    <Link href={`/dashboards/${d.id}`} className="hover:underline">
                      {d.name}
                    </Link>
                  </CardTitle>
                  <CardDescription className="mt-1 line-clamp-2">
                    {d.description || "No description"}
                  </CardDescription>
                </div>
                {d.isShared ? (
                  <Badge variant="secondary" className="shrink-0">
                    <Users className="mr-1 size-3" /> shared
                  </Badge>
                ) : (
                  <Badge variant="outline" className="shrink-0">private</Badge>
                )}
              </div>
            </CardHeader>
            <CardFooter className="justify-between text-xs text-muted-foreground">
              <span>Updated {new Date(d.updatedAt).toLocaleDateString()}</span>
              <div className="flex gap-1">
                <Button
                  size="icon"
                  variant="ghost"
                  title="Duplicate"
                  disabled={duplicateMutation.isPending}
                  onClick={() => duplicateMutation.mutate(d.id)}
                >
                  <Copy className="size-3.5" />
                </Button>
                {(d.ownerId === user?.id || user?.role === "admin") && (
                  <Button
                    size="icon"
                    variant="ghost"
                    title="Delete"
                    disabled={deleteMutation.isPending}
                    onClick={() => deleteMutation.mutate(d.id)}
                  >
                    <Trash2 className="size-3.5 text-destructive" />
                  </Button>
                )}
              </div>
            </CardFooter>
          </Card>
        ))}
      </div>
    </div>
  );
}
