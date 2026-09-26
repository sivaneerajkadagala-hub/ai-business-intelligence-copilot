import type { Metadata } from "next";
import Link from "next/link";

import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const metadata: Metadata = { title: "Reset password" };

export default function ForgotPasswordPage() {
  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-xl">Reset password</CardTitle>
        <CardDescription>
          We&apos;ll send a reset link to your email
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="you@company.com"
              autoComplete="email"
              required
            />
          </div>
          <Button type="submit" className="w-full">
            Send reset link
          </Button>
        </form>
      </CardContent>
      <CardFooter className="justify-center">
        <Link
          href="/login"
          className="text-sm text-muted-foreground underline-offset-4 hover:underline"
        >
          Back to sign in
        </Link>
      </CardFooter>
    </Card>
  );
}
