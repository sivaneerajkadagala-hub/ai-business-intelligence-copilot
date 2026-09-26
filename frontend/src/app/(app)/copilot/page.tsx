"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Database,
  Loader2,
  MessageSquare,
  Plus,
  Send,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth";
import { apiErrorMessage } from "@/lib/api";
import {
  type ChatMessage,
  type ChatResponse,
  type Conversation,
} from "@/lib/copilot";
import {
  type Dataset,
  type DatasetColumn,
  type Page,
} from "@/lib/datasets";
import { AssistantMessage } from "@/components/copilot/answer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";

type Profile = { columns: DatasetColumn[] };

export default function CopilotPage() {
  const { api, user } = useAuth();
  const queryClient = useQueryClient();
  const [activeConv, setActiveConv] = useState<string | null>(null);
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [saveTarget, setSaveTarget] = useState<ChatMessage | null>(null);
  const [saveName, setSaveName] = useState("");
  const [pinTarget, setPinTarget] = useState<ChatMessage | null>(null);
  const [pinDashboard, setPinDashboard] = useState<string | null>(null);
  // Optimistic messages for the current thread until the server copy
  // catches up (deduped against fetched messages by id / role+content).
  const [pending, setPending] = useState<ChatMessage[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: conversations } = useQuery({
    queryKey: ["conversations"],
    queryFn: () => api<Conversation[]>("/copilot/conversations"),
  });

  const { data: datasets } = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api<Page<Dataset>>("/datasets?page_size=100"),
  });
  const readyDatasets = datasets?.items.filter((d) => d.status === "ready") ?? [];
  const dataset =
    readyDatasets.find((d) => d.id === datasetId) ??
    readyDatasets.find((d) => d.name === "Sales") ??
    readyDatasets[0];

  const { data: profile } = useQuery({
    queryKey: ["profile", dataset?.id],
    queryFn: () => api<Profile>(`/datasets/${dataset!.id}/profile`),
    enabled: !!dataset,
  });

  const { data: convDetail, isLoading: convLoading } = useQuery({
    queryKey: ["conversation", activeConv],
    queryFn: () =>
      api<Conversation & { messages: ChatMessage[] }>(
        `/copilot/conversations/${activeConv}`,
      ),
    enabled: !!activeConv,
  });

  const fetchedMessages = convDetail?.messages ?? [];
  const pendingVisible = pending.filter(
    (m) =>
      !fetchedMessages.some(
        (f) => f.id === m.id || (f.role === "user" && f.content === m.content),
      ),
  );
  const messages = activeConv
    ? [...fetchedMessages, ...pendingVisible]
    : pending;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const sendMutation = useMutation({
    mutationFn: (q: string) =>
      api<ChatResponse>("/copilot/chat", {
        method: "POST",
        body: JSON.stringify({
          question: q,
          datasetId: dataset?.id,
          conversationId: activeConv ?? undefined,
        }),
      }),
    onMutate: (q) => {
      setPending((m) => [
        ...m,
        {
          id: `temp-${Date.now()}`,
          role: "user",
          content: q,
          sql: null,
          resultSnapshot: null,
          chartSpec: null,
          explanation: null,
          createdAt: new Date().toISOString(),
        },
      ]);
      setQuestion("");
    },
    onSuccess: (res) => {
      setPending((m) => [...m, res.message]);
      setActiveConv(res.conversationId);
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["conversation", res.conversationId] });
    },
    onError: (e) => {
      setPending([]);
      toast.error(apiErrorMessage(e));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      api(`/copilot/conversations/${id}`, { method: "DELETE" }),
    onSuccess: (_d, id) => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      if (activeConv === id) {
        setActiveConv(null);
        setPending([]);
      }
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const saveQueryMutation = useMutation({
    mutationFn: () =>
      api("/queries", {
        method: "POST",
        body: JSON.stringify({
          name: saveName.trim() || "Copilot query",
          sql: saveTarget?.sql,
          question: saveTarget?.content?.slice(0, 200) ?? null,
          datasetId: dataset?.id,
          isShared: true,
        }),
      }),
    onSuccess: () => {
      toast.success("Query saved to library");
      setSaveTarget(null);
      setSaveName("");
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const { data: dashboards } = useQuery({
    queryKey: ["dashboards"],
    queryFn: () =>
      api<{ id: string; name: string; ownerId: string; isShared: boolean }[]>(
        "/dashboards",
      ),
    enabled: !!pinTarget,
  });
  const editableDashboards = (dashboards ?? []).filter(
    (d) => d.ownerId === user?.id || user?.role === "admin",
  );
  const pinMutation = useMutation({
    mutationFn: () =>
      api<{ dashboardId: string; dashboardName: string }>(
        `/copilot/messages/${pinTarget?.id}/pin`,
        {
          method: "POST",
          body: JSON.stringify({ dashboardId: pinDashboard }),
        },
      ),
    onSuccess: (r) => {
      toast.success(`Pinned to "${r.dashboardName}"`);
      setPinTarget(null);
      setPinDashboard(null);
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const firstMetric = profile?.columns.find((c) =>
    ["integer", "float"].includes(c.inferredType),
  )?.normalizedName;
  const firstDim = profile?.columns.find(
    (c) => c.inferredType === "string",
  )?.normalizedName;
  const suggestions = dataset
    ? [
        firstMetric ? `Total ${firstMetric}` : null,
        firstDim && firstMetric ? `Top 5 ${firstDim} by ${firstMetric}` : null,
        firstMetric ? `Monthly ${firstMetric} trend` : null,
        "How many rows are there?",
      ].filter(Boolean) as string[]
    : [];

  function send(q?: string) {
    const text = (q ?? question).trim();
    if (!text || !dataset || sendMutation.isPending) return;
    sendMutation.mutate(text);
  }

  function newChat() {
    setActiveConv(null);
    setPending([]);
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* Conversation list */}
      <div className="flex w-60 shrink-0 flex-col rounded-lg border bg-card">
        <div className="flex items-center justify-between border-b p-3">
          <span className="text-sm font-medium">Chats</span>
          <Button size="icon" variant="ghost" onClick={newChat} title="New chat">
            <Plus className="size-4" />
          </Button>
        </div>
        <ScrollArea className="flex-1">
          <ul className="flex flex-col gap-0.5 p-2">
            {conversations?.map((c) => (
              <li key={c.id} className="group flex items-center gap-1">
                <button
                  onClick={() => {
                    setActiveConv(c.id);
                    setPending([]);
                  }}
                  className={`flex flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm ${
                    activeConv === c.id
                      ? "bg-accent font-medium"
                      : "text-muted-foreground hover:bg-accent/60"
                  }`}
                >
                  <MessageSquare className="size-3.5 shrink-0" />
                  <span className="truncate">{c.title}</span>
                </button>
                <button
                  onClick={() => deleteMutation.mutate(c.id)}
                  className="invisible rounded p-1 text-muted-foreground hover:text-destructive group-hover:visible"
                  title="Delete"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </li>
            ))}
            {!conversations?.length && (
              <li className="p-3 text-xs text-muted-foreground">
                No conversations yet.
              </li>
            )}
          </ul>
        </ScrollArea>
      </div>

      {/* Chat area */}
      <div className="flex min-w-0 flex-1 flex-col rounded-lg border bg-card">
        <div className="flex items-center justify-between gap-3 border-b px-4 py-2.5">
          <div className="flex items-center gap-2">
            <Bot className="size-4 text-primary" />
            <span className="text-sm font-medium">BI Copilot</span>
            <Badge variant="outline" className="text-xs">
              demo engine
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            <Database className="size-4 text-muted-foreground" />
            <Select
              value={dataset?.id}
              onValueChange={(v) => setDatasetId(v as string)}
            >
              <SelectTrigger size="sm" className="w-44">
                <SelectValue placeholder="Dataset" />
              </SelectTrigger>
              <SelectContent>
                {readyDatasets.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {convLoading ? (
            <div className="flex flex-col gap-3">
              <Skeleton className="h-16 w-2/3" />
              <Skeleton className="h-24 w-3/4" />
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <Bot className="size-10 text-muted-foreground/40" />
              <div>
                <p className="font-medium">Ask anything about your data</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {dataset
                    ? `Querying "${dataset.name}" — ${dataset.rowCount.toLocaleString()} rows`
                    : "Select a dataset to begin"}
                </p>
              </div>
              <div className="flex max-w-md flex-wrap justify-center gap-2">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="rounded-full border px-3 py-1.5 text-xs hover:bg-accent"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {messages.map((m) =>
                m.role === "user" ? (
                  <div
                    key={m.id}
                    className="ml-auto max-w-md rounded-lg bg-primary px-3.5 py-2 text-sm text-primary-foreground"
                  >
                    {m.content}
                  </div>
                ) : (
                  <AssistantMessage
                    key={m.id}
                    msg={m}
                    onPin={
                      user?.role === "viewer"
                        ? undefined
                        : (msg) => {
                            setPinTarget(msg);
                            setPinDashboard(null);
                          }
                    }
                    onSaveQuery={
                      user?.role === "viewer"
                        ? undefined
                        : (msg) => {
                            setSaveTarget(msg);
                            setSaveName(msg.content.slice(0, 60));
                          }
                    }
                  />
                ),
              )}
              {sendMutation.isPending && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  Generating, validating &amp; executing…
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <form
          className="flex items-center gap-2 border-t p-3"
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          <Input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={
              dataset
                ? `Ask about ${dataset.name}…`
                : "Upload a dataset first"
            }
            disabled={!dataset || sendMutation.isPending}
          />
          <Button type="submit" disabled={!question.trim() || sendMutation.isPending}>
            <Send className="size-4" />
          </Button>
        </form>
      </div>

      <Dialog open={!!saveTarget} onOpenChange={(o) => !o && setSaveTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save query</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <Input
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="Query name"
            />
            <pre className="max-h-40 overflow-x-auto rounded-md bg-muted p-3 text-xs">
              {saveTarget?.sql}
            </pre>
            <Button
              onClick={() => saveQueryMutation.mutate()}
              disabled={saveQueryMutation.isPending}
            >
              Save to library
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!pinTarget} onOpenChange={(o) => !o && setPinTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Pin to dashboard</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <Select value={pinDashboard ?? ""} onValueChange={(v) => setPinDashboard(v as string)}>
              <SelectTrigger>
                <SelectValue placeholder="Choose a dashboard" />
              </SelectTrigger>
              <SelectContent>
                {editableDashboards.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!editableDashboards.length && (
              <p className="text-sm text-muted-foreground">
                No dashboards you can edit — create one on the Dashboards page.
              </p>
            )}
            <Button
              onClick={() => pinMutation.mutate()}
              disabled={!pinDashboard || pinMutation.isPending}
            >
              Pin chart
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
