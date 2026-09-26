"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

export default function SettingsPage() {
  const router = useRouter();
  const { user, api, setUser, loading } = useAuth();
  const [fullName, setFullName] = useState<string | null>(null);
  const [pw, setPw] = useState({ current: "", next: "", confirm: "" });
  const [saving, setSaving] = useState(false);
  const [changingPw, setChangingPw] = useState(false);

  async function saveProfile() {
    if (!fullName?.trim()) return;
    setSaving(true);
    try {
      const updated = await api<User>("/auth/me", {
        method: "PATCH",
        body: JSON.stringify({ fullName: fullName.trim() }),
      });
      setUser(updated);
      toast.success("Profile updated");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  async function changePassword() {
    setChangingPw(true);
    try {
      await api("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          currentPassword: pw.current,
          newPassword: pw.next,
        }),
      });
      toast.success("Password changed — sign in again");
      router.push("/login");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    } finally {
      setChangingPw(false);
    }
  }

  if (loading) {
    return (
      <div className="flex max-w-2xl flex-col gap-4">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Manage your profile and security
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Profile</CardTitle>
          <CardDescription>Your account details</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" value={user?.email ?? ""} disabled />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Full name</Label>
            <Input
              id="name"
              value={fullName ?? user?.fullName ?? ""}
              onChange={(e) => setFullName(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2">
            <Label className="text-muted-foreground">Role</Label>
            <Badge variant="secondary">{user?.role}</Badge>
          </div>
          <div>
            <Button onClick={saveProfile} disabled={saving}>
              {saving ? "Saving..." : "Save profile"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Change password</CardTitle>
          <CardDescription>
            You&apos;ll be signed out of all sessions
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cur-pw">Current password</Label>
            <Input
              id="cur-pw"
              type="password"
              autoComplete="current-password"
              value={pw.current}
              onChange={(e) => setPw({ ...pw, current: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-pw">New password</Label>
            <Input
              id="new-pw"
              type="password"
              autoComplete="new-password"
              value={pw.next}
              onChange={(e) => setPw({ ...pw, next: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="conf-pw">Confirm new password</Label>
            <Input
              id="conf-pw"
              type="password"
              autoComplete="new-password"
              value={pw.confirm}
              onChange={(e) => setPw({ ...pw, confirm: e.target.value })}
            />
            {pw.confirm && pw.next !== pw.confirm && (
              <p className="text-xs text-destructive">Passwords do not match</p>
            )}
          </div>
          <div>
            <Button
              onClick={changePassword}
              disabled={
                changingPw || !pw.current || pw.next.length < 8 || pw.next !== pw.confirm
              }
            >
              {changingPw ? "Updating..." : "Change password"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
