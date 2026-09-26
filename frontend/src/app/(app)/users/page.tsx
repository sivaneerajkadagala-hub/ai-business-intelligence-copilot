import type { Metadata } from "next";
import { Users } from "lucide-react";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Users" };

export default function UsersPage() {
  return (
    <PagePlaceholder
      title="Users"
      description="Manage users and roles"
      icon={Users}
    />
  );
}
