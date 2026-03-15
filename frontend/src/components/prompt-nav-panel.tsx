import { MessageSquare } from "lucide-react";
import { extractUserText, truncate } from "../utils";
import type { Message } from "../types";

const PREVIEW_MAX_CHARS = 80;

interface PromptEntry {
  turnNumber: number;
  uuid: string;
  preview: string;
  followingCount: number;
}

interface PromptNavPanelProps {
  messages: Message[];
  activePromptUuid: string | null;
  onNavigate: (uuid: string) => void;
}

function buildPromptEntries(messages: Message[]): PromptEntry[] {
  const entries: PromptEntry[] = [];
  let turnNumber = 0;

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    if (msg.role !== "user") continue;

    const text = extractUserText(msg);
    if (!text) continue;

    turnNumber++;

    // Count following non-user messages until the next user message
    let followingCount = 0;
    for (let j = i + 1; j < messages.length; j++) {
      if (messages[j].role === "user") break;
      followingCount++;
    }

    entries.push({
      turnNumber,
      uuid: msg.uuid,
      preview: truncate(text.replace(/\n/g, " "), PREVIEW_MAX_CHARS),
      followingCount,
    });
  }

  return entries;
}

const MIN_PROMPTS_FOR_NAV = 2;

export function PromptNavPanel({
  messages,
  activePromptUuid,
  onNavigate,
}: PromptNavPanelProps) {
  const entries = buildPromptEntries(messages);

  if (entries.length < MIN_PROMPTS_FOR_NAV) return null;

  return (
    <div className="hidden xl:block w-56 shrink-0 h-full overflow-y-auto border-l border-zinc-800 bg-zinc-900/50">
      <div className="px-3 py-3">
        <div className="flex items-center gap-1.5 text-xs text-zinc-400 mb-3">
          <MessageSquare className="w-3.5 h-3.5" />
          <span className="font-medium">Prompts</span>
          <span className="text-zinc-600">({entries.length})</span>
        </div>
        <div className="space-y-1">
          {entries.map((entry) => {
            const isActive = entry.uuid === activePromptUuid;
            return (
              <button
                key={entry.uuid}
                onClick={() => onNavigate(entry.uuid)}
                className={`w-full text-left px-2 py-1.5 rounded-md transition-colors text-xs group ${
                  isActive
                    ? "bg-cyan-500/15 border border-cyan-500/30"
                    : "hover:bg-zinc-800/60 border border-transparent"
                }`}
              >
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span
                    className={`font-mono font-semibold ${
                      isActive ? "text-cyan-400" : "text-zinc-500 group-hover:text-zinc-400"
                    }`}
                  >
                    #{entry.turnNumber}
                  </span>
                  {entry.followingCount > 0 && (
                    <span className="text-[10px] text-zinc-600">
                      +{entry.followingCount}
                    </span>
                  )}
                </div>
                <p
                  className={`line-clamp-2 leading-snug ${
                    isActive ? "text-cyan-200/80" : "text-zinc-500 group-hover:text-zinc-400"
                  }`}
                >
                  {entry.preview}
                </p>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
