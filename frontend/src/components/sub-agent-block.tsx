import { Bot, MessageSquare, Wrench } from "lucide-react";
import { useState } from "react";
import type { SubAgentSession } from "../types";
import { CollapsiblePill } from "./collapsible-pill";
import { MessageBlock } from "./message-block";

interface SubAgentBlockProps {
  subSession: SubAgentSession;
}

export function SubAgentBlock({ subSession }: SubAgentBlockProps) {
  const [open, setOpen] = useState(false);

  const messageCount = subSession.messages.length;
  const toolCallCount = subSession.messages.reduce(
    (sum, m) => sum + (m.tool_calls?.length || 0),
    0,
  );

  const label = subSession.agent_id || "Sub-agent";
  const preview = `${messageCount} msgs • ${toolCallCount} tools`;

  return (
    <CollapsiblePill
      open={open}
      onToggle={() => setOpen(!open)}
      icon={<Bot className="w-3.5 h-3.5" />}
      label={label}
      preview={preview}
      className="bg-violet-500/10 border-violet-500/30 text-violet-300"
    >
      <div className="border-l-2 border-violet-500/30 ml-3 pl-3 py-2 space-y-2">
        <div className="flex items-center gap-3 text-[10px] text-violet-400 px-1 pb-1">
          <span className="flex items-center gap-1">
            <MessageSquare className="w-3 h-3" />
            {messageCount}
          </span>
          <span className="flex items-center gap-1">
            <Wrench className="w-3 h-3" />
            {toolCallCount}
          </span>
        </div>
        {subSession.messages
          .filter((m) => m.role === "user" || m.role === "assistant")
          .map((msg) => (
            <MessageBlock key={msg.uuid} message={msg} />
          ))}
        {subSession.sub_sessions.map((nested) => (
          <SubAgentBlock key={nested.agent_id} subSession={nested} />
        ))}
      </div>
    </CollapsiblePill>
  );
}
