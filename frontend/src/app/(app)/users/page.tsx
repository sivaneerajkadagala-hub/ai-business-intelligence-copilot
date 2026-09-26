"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert, UserPlus } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth";
import { apiErrorMessage } from "@/lib/api";
import type { User } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const ROLES = ["admin", "analyst", "viewer"] as const;

type UsersPage = { items: User[]; total: number; page: number; pages: number };

function RoleBadge({ role }: { role: User["role"] }) {
  const variant =
    role === "admin" ? "default" : role === "analyst" ? "secondary" : "outline";
  return <Badge variant={variant}>{role}</Badge>;
}

export default function UsersPage() {
  const { user: me, api, loading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({
    email: "",
    password: "",
    fullName: "",
    role: "viewer" as string,
  });

  const { data, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => api<UsersPage>("/users"),
    enabled: !!me && me.role === "admin",
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["users"] });

  const createUser = useMutation({
    mutationFn: () =>
      api("/users", { method: "POST", body: JSON.stringify(form) }),
    onSuccess: () => {
      toast.success("User created");
      setDialogOpen(false);
      setForm({ email: "", password: "", fullName: "", role: "viewer" });
      invalidate();
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const changeRole = useMutation({
    mutationFn: ({ id, role }: { id: string; role: string }) =>
      api(`/users/${id}/role`, { method: "PATCH", body: JSON.stringify({ role }) }),
    onSuccess: () => {
      toast.success("Role updated");
      invalidate();
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const deactivate = useMutation({
    mutationFn: (id: string) => api(`/users/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("User deactivated");
      invalidate();
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  if (!authLoading && me?.role !== "admin") {
    return (
      <Card className="mx-auto mt-10 max-w-md">
        <CardHeader className="items-center text-center">
          <ShieldAlert className="mb-2 size-8 text-muted-foreground" />
          <CardTitle>Admin access required</CardTitle>
          <CardDescription>
            User management is only available to administrators.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
          <p className="text-sm text-muted-foreground">
            Manage workspace members and their roles
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger render={<Button />}>
            <UserPlus className="mr-2 size-4" />
            Add user
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create user</DialogTitle>
              <DialogDescription>
                New users sign in with the password you set here.
              </DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cu-name">Full name</Label>
                <Input
                  id="cu-name"
                  value={form.fullName}
                  onChange={(e) => setForm({ ...form, fullName: e.target.value })}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cu-email">Email</Label>
                <Input
                  id="cu-email"
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cu-pass">Temporary password</Label>
                <Input
                  id="cu-pass"
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Role</Label>
                <Select
                  value={form.role}
                  onValueChange={(v) => setForm({ ...form, role: v as string })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select role" />
                  </SelectTrigger>
                  <SelectContent>
                    {ROLES.map((r) => (
                      <SelectItem key={r} value={r}>
                        {r}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button
                onClick={() => createUser.mutate()}
                disabled={
                  createUser.isPending ||
                  !form.email ||
                  form.password.length < 8 ||
                  !form.fullName
                }
              >
                {createUser.isPending ? "Creating..." : "Create user"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Joined</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 6 }).map((__, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-20" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              {data?.items.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="font-medium">{u.fullName}</TableCell>
                  <TableCell>{u.email}</TableCell>
                  <TableCell>
                    <RoleBadge role={u.role} />
                  </TableCell>
                  <TableCell>
                    {u.isActive ? (
                      <span className="text-sm">Active</span>
                    ) : (
                      <span className="text-sm text-muted-foreground">
                        Deactivated
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {new Date(u.createdAt).toLocaleDateString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Select
                        value={u.role}
                        onValueChange={(v) =>
                          changeRole.mutate({ id: u.id, role: v as string })
                        }
                      >
                        <SelectTrigger size="sm" className="w-28">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {ROLES.map((r) => (
                            <SelectItem key={r} value={r}>
                              {r}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={!u.isActive || u.id === me?.id}
                        onClick={() => deactivate.mutate(u.id)}
                      >
                        Deactivate
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      {data && (
        <p className="text-xs text-muted-foreground">
          {data.total} user{data.total === 1 ? "" : "s"}
        </p>
      )}
    </div>
  );
}
