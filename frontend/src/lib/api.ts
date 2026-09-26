const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ApiError = {
  message: string;
  errorCode: string | null;
};

export function apiErrorMessage(e: unknown): string {
  return (e as ApiError | undefined)?.message ?? "Something went wrong";
}

export type ApiOptions = RequestInit & {
  token?: string | null;
};

export type User = {
  id: string;
  email: string;
  fullName: string;
  role: "admin" | "analyst" | "viewer";
  isActive: boolean;
  lastLoginAt: string | null;
  createdAt: string;
};

export type AuthResponse = { accessToken: string; user: User };

// The AuthProvider registers a refresher that rotates the refresh-cookie
// session and updates context state. apiFetch uses it to retry one 401.
let sessionRefresher: (() => Promise<string | null>) | null = null;
let inflightRefresh: Promise<string | null> | null = null;

export function setSessionRefresher(fn: () => Promise<string | null>) {
  sessionRefresher = fn;
}

function refreshSession(): Promise<string | null> {
  if (!sessionRefresher) return Promise.resolve(null);
  inflightRefresh ??= sessionRefresher().finally(() => {
    inflightRefresh = null;
  });
  return inflightRefresh;
}

async function doFetch<T>(path: string, options: ApiOptions): Promise<T> {
  const { token, headers, ...init } = options;
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    credentials: "include",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });

  const body = (await res.json().catch(() => null)) as {
    success?: boolean;
    data?: T;
    message?: string;
    errorCode?: string;
  } | null;

  if (!res.ok || body?.success === false) {
    throw {
      message: body?.message ?? `Request failed (${res.status})`,
      errorCode: body?.errorCode ?? null,
    } satisfies ApiError;
  }
  return body?.data as T;
}

export async function apiFetch<T>(
  path: string,
  options: ApiOptions = {},
): Promise<T> {
  try {
    return await doFetch<T>(path, options);
  } catch (err) {
    const apiErr = err as ApiError;
    const is401 = apiErr.errorCode === "UNAUTHORIZED";
    if (is401 && options.token !== undefined) {
      const fresh = await refreshSession();
      if (fresh) return doFetch<T>(path, { ...options, token: fresh });
    }
    throw err;
  }
}
