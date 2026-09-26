import { AppSidebar } from "@/components/layout/app-sidebar";
import { Topbar } from "@/components/layout/topbar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-muted/30">
      <AppSidebar />
      <div className="md:pl-64">
        <Topbar />
        <main className="p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
