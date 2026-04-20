import { Check, Copy } from "lucide-react";
import { useCallback } from "react";
import { useCopyFeedback } from "../../hooks/use-copy-feedback";
import { Tooltip } from "./tooltip";

interface CopyButtonProps {
  text: string;
  className?: string;
}

export function CopyButton({ text, className = "" }: CopyButtonProps) {
  const { copied, copy } = useCopyFeedback();
  const handleCopy = useCallback(() => {
    copy(text);
  }, [copy, text]);

  return (
    <Tooltip text={copied ? "Copied!" : "Copy"}>
      <button
        onClick={handleCopy}
        className={`p-1 rounded hover:bg-control-hover/50 transition-colors ${className}`}
      >
        {copied ? (
          <Check className="w-3.5 h-3.5 text-accent-emerald" />
        ) : (
          <Copy className="w-3.5 h-3.5 text-muted" />
        )}
      </button>
    </Tooltip>
  );
}
