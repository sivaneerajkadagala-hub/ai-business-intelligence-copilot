export type Conversation = {
  id: string;
  title: string;
  datasetId: string | null;
  createdAt: string;
  updatedAt: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sql: string | null;
  resultSnapshot: {
    columns: string[];
    rows: Record<string, unknown>[];
    rowCount: number;
    series?: { t: string; value: number }[];
    meta?: {
      intent?: string;
      metric?: string;
      dim?: string;
      dateCol?: string;
      bucket?: string;
      agg?: string;
    };
  } | null;
  chartSpec: { type: string; x?: string; y?: string } | null;
  explanation: string | null;
  createdAt: string;
};

export type ChatResponse = {
  conversationId: string;
  message: ChatMessage;
  engine: string | null;
};
