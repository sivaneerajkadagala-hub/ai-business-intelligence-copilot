import {
  Bot,
  ChartLine,
  Database,
  FileCode2,
  FileText,
  LayoutDashboard,
  LayoutGrid,
  Lightbulb,
  ScrollText,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  title: string;
  href: string;
  icon: LucideIcon;
  roles?: string[];
};

export type NavGroup = {
  label: string;
  items: NavItem[];
};

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [{ title: "Dashboard", href: "/dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Data",
    items: [
      { title: "Datasets", href: "/datasets", icon: Database },
      { title: "Saved Queries", href: "/queries", icon: FileCode2 },
    ],
  },
  {
    label: "Analysis",
    items: [
      { title: "BI Copilot", href: "/copilot", icon: Bot },
      { title: "Analytics", href: "/analytics", icon: ChartLine },
      { title: "Insights", href: "/insights", icon: Lightbulb },
    ],
  },
  {
    label: "Build",
    items: [
      { title: "Dashboards", href: "/dashboards", icon: LayoutGrid },
      { title: "Reports", href: "/reports", icon: FileText },
    ],
  },
  {
    label: "Administration",
    items: [
      { title: "Users", href: "/users", icon: Users, roles: ["admin"] },
      {
        title: "Audit Logs",
        href: "/audit-logs",
        icon: ScrollText,
        roles: ["admin"],
      },
    ],
  },
  {
    label: "Account",
    items: [{ title: "Settings", href: "/settings", icon: Settings }],
  },
];
