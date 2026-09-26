const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ApiError = {
  message: string;
  errorCode: string | null;
};

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  const body = (await res.json().catch(() => null)) as {
    success?: boolean;
    data?: T;
    message?: string;
    errorCode?: string;
  } | null;

  if (!res.ok || body?.success === false) {
    const err: ApiError = {
      message: body?.message ?? `Request failed (${res.status})`,
      errorCode: body?.errorCode ?? null,
    };
    throw err;
  }

  return body?.data as T;
}
