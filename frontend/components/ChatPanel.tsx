"use client";

import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { askQuestion, ApiError } from "@/lib/api";
import { parseAnswer } from "@/lib/format";
import type { AskResponse, Chapter, ChatTurn } from "@/lib/types";
import { AgentTrace } from "./AgentTrace";
import { CitationChip } from "./CitationChip";

interface AssistantMessage {
  role: "assistant";
  content: string;
  answer: AskResponse;
}
interface UserMessage {
  role: "user";
  content: string;
}
type Message = UserMessage | AssistantMessage;

const CONFIDENCE_LABEL: Record<AskResponse["confidence"], string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

export function ChatPanel({
  videoId,
  chapters,
  onCite,
}: {
  videoId: string;
  chapters: Chapter[];
  onCite: (seconds: number) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");

  // Two example questions, pre-filled from the chapter titles (§16.3).
  const examples = useMemo(() => {
    const titles = chapters.map((c) => c.title).filter(Boolean);
    const out: string[] = [];
    if (titles[0]) out.push(`What does "${titles[0]}" cover?`);
    if (titles[1]) out.push(`Why does "${titles[1]}" matter?`);
    return out;
  }, [chapters]);

  const ask = useMutation({
    mutationFn: (question: string) => {
      const history: ChatTurn[] = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));
      return askQuestion(videoId, question, history);
    },
    onSuccess: (answer, question) => {
      setMessages((prev) => [
        ...prev,
        { role: "user", content: question },
        { role: "assistant", content: answer.answer, answer },
      ]);
      setDraft("");
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = draft.trim();
    if (q && !ask.isPending) ask.mutate(q);
  };

  const error =
    ask.error instanceof ApiError
      ? ask.error.message
      : ask.error
        ? "Something went wrong. Try again."
        : null;

  return (
    <div className="flex h-full flex-col">
      <h2 className="mb-3 font-condensed text-lg font-semibold tracking-wide">
        Ask about this video
      </h2>

      <div className="flex-1 space-y-4 overflow-y-auto pr-1 scroll-slim">
        {messages.length === 0 && (
          <div className="rounded-lg border border-hairline bg-surface p-4">
            <p className="text-sm text-muted">
              Ask anything about what was said — answers cite the exact moments
              they come from. Try one of these:
            </p>
            <div className="mt-3 flex flex-col gap-2">
              {examples.map((q) => (
                <button
                  key={q}
                  onClick={() => setDraft(q)}
                  className="rounded-md border border-hairline px-3 py-2 text-left text-sm text-paper hover:border-signal"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <p
              key={i}
              className="ml-auto max-w-[85%] rounded-lg rounded-br-sm bg-signal/10 px-3 py-2 text-sm text-paper"
            >
              {m.content}
            </p>
          ) : (
            <AssistantBubble key={i} message={m} onCite={onCite} />
          ),
        )}

        {ask.isPending && (
          <p className="text-sm text-muted">Searching the transcript…</p>
        )}
        {error && (
          <p role="alert" className="text-sm text-citation">
            {error}
          </p>
        )}
      </div>

      <form onSubmit={submit} className="mt-3 flex gap-2">
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <input
          id="question"
          value={draft}
          maxLength={1000}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask a question"
          className="flex-1 rounded-lg border border-hairline bg-surface px-3 py-2.5 text-sm text-paper placeholder:text-muted focus:border-signal"
        />
        <button
          type="submit"
          disabled={ask.isPending || !draft.trim()}
          className="rounded-lg bg-signal px-4 py-2.5 font-condensed font-semibold tracking-wide text-ground disabled:opacity-60"
        >
          Ask
        </button>
      </form>
    </div>
  );
}

function AssistantBubble({
  message,
  onCite,
}: {
  message: AssistantMessage;
  onCite: (seconds: number) => void;
}) {
  const { answer } = message;
  const segments = parseAnswer(answer.answer, answer.citations);

  return (
    <div className="max-w-[95%] rounded-lg rounded-bl-sm border border-hairline bg-surface px-3 py-2.5">
      <p className="text-sm leading-relaxed text-paper">
        {segments.map((seg, i) =>
          seg.kind === "text" ? (
            <span key={i}>{seg.text}</span>
          ) : (
            <CitationChip
              key={i}
              marker={seg.marker}
              citation={seg.citation}
              onSeek={onCite}
            />
          ),
        )}
      </p>
      <div className="mt-2 flex items-center justify-between">
        <span
          className={`text-xs ${
            answer.confidence === "low" ? "text-citation" : "text-muted"
          }`}
        >
          {CONFIDENCE_LABEL[answer.confidence]}
        </span>
      </div>
      <AgentTrace trace={answer.trace} />
    </div>
  );
}
