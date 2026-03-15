import { Check, Copy } from "lucide-react";
import { useCallback, useState } from "react";

const FEEDBACK_TIMEOUT_MS = 1500;

interface CopyButtonProps {
  text: string;
  className?: string;
}

export function CopyButton({ text, className = "" }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), FEEDBACK_TIMEOUT_MS);
    });
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className={`p-1 rounded hover:bg-zinc-700/50 transition-colors ${className}`}
      title={copied ? "Copied!" : "Copy"}
    >
      {copied ? (
        <Check className="w-3.5 h-3.5 text-emerald-400" />
      ) : (
        <Copy className="w-3.5 h-3.5 text-zinc-400" />
      )}
    </button>
  );
}
