/**
 * Renders text that may contain bullet points and inline **bold** markdown.
 *
 * Handles various LLM output formats:
 *   "Conclusion.\n- Point 1\n- Point 2"
 *   "Conclusion.\n\n- **Bold key**: explanation\n\n- **Another**: detail"
 *
 * Lead text renders as a paragraph; lines starting with "- " render as
 * a styled <ul>. **bold** spans are rendered as <strong>. Empty lines
 * between bullets are silently dropped.
 */

import React from "react";

const BOLD_REGEX = /\*\*(.+?)\*\*/g;

/** Render inline **bold** spans within a text string. */
function renderInlineMarkdown(raw: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  // Reset regex state for each call
  BOLD_REGEX.lastIndex = 0;
  while ((match = BOLD_REGEX.exec(raw)) !== null) {
    if (match.index > lastIndex) {
      parts.push(raw.slice(lastIndex, match.index));
    }
    parts.push(<strong key={match.index} className="font-semibold text-primary">{match[1]}</strong>);
    lastIndex = BOLD_REGEX.lastIndex;
  }
  if (lastIndex < raw.length) {
    parts.push(raw.slice(lastIndex));
  }
  return parts.length === 1 ? parts[0] : <>{parts}</>;
}

export function BulletText({ text, className = "" }: { text: string; className?: string }) {
  const lines = text.split("\n");
  const lead: string[] = [];
  const bullets: string[] = [];
  let seenBullet = false;

  for (const raw of lines) {
    const line = raw.trim();
    if (line === "") continue;
    if (line.startsWith("- ")) {
      seenBullet = true;
      bullets.push(line.slice(2).trim());
    } else if (!seenBullet) {
      lead.push(line);
    }
    // Non-bullet lines after the first bullet are ignored (noise from LLM)
  }

  if (!seenBullet) {
    return <p className={className}>{renderInlineMarkdown(text)}</p>;
  }

  const leadText = lead.join(" ").trim();

  return (
    <div className={className}>
      {leadText && <p>{renderInlineMarkdown(leadText)}</p>}
      <ul className="mt-1.5 space-y-1 list-disc pl-4 marker:text-dimmed">
        {bullets.map((b, i) => (
          <li key={i}>{renderInlineMarkdown(b)}</li>
        ))}
      </ul>
    </div>
  );
}
