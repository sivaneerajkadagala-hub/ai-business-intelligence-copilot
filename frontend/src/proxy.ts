import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PROTECTED_PREFIXES = [
  "/dashboard",
  "/datasets",
  "/analytics",
  "/copilot",
  "/dashboards",
  "/queries",
  "/reports",
  "/settings",
  "/users",
  "/audit-logs",
];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const needsAuth = PROTECTED_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(p + "/"),
  );
  if (!needsAuth) return NextResponse.next();

  // The httpOnly refresh cookie is the session signal — the access token
  // lives in memory only. Absent cookie → send the user to sign in.
  if (request.cookies.has("bi_refresh")) return NextResponse.next();

  const url = new URL("/login", request.url);
  url.searchParams.set("next", pathname);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/datasets/:path*",
    "/analytics/:path*",
    "/copilot/:path*",
    "/dashboards/:path*",
    "/queries/:path*",
    "/reports/:path*",
    "/settings/:path*",
    "/users/:path*",
    "/audit-logs/:path*",
  ],
};
