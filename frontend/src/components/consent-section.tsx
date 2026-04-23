import { Coins, HardDrive, Send } from "lucide-react";
import { CLI_BACKENDS } from "./llm/llm-config-constants";

const SEND_ITEM = {
  icon: <Send className="w-4 h-4 text-violet-600 dark:text-violet-400 shrink-0 mt-0.5" />,
  text: "Session data will be sent to your selected AI provider.",
};

const COST_ITEM_LITELLM = {
  icon: <Coins className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />,
  text: "Costs will be charged to your configured API key.",
};

const COST_ITEM_CLI = {
  icon: <Coins className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />,
  text: "Usage will count against your agent subscription or quota.",
};

const LOCAL_ITEM = {
  icon: <HardDrive className="w-4 h-4 text-cyan-600 dark:text-cyan-400 shrink-0 mt-0.5" />,
  text: "Results are saved locally and can be deleted anytime.",
};

function getConsentItems(backendId: string | null | undefined) {
  const costItem = backendId && CLI_BACKENDS.has(backendId) ? COST_ITEM_CLI : COST_ITEM_LITELLM;
  return [SEND_ITEM, costItem, LOCAL_ITEM];
}

export function ConsentSection({
  agreed,
  onAgreeChange,
  backendId,
}: {
  agreed: boolean;
  onAgreeChange: (checked: boolean) => void;
  backendId?: string | null;
}) {
  const items = getConsentItems(backendId);
  return (
    <div className="space-y-3">
      <p className="text-sm font-semibold text-primary">
        By proceeding, you acknowledge that:
      </p>
      <div className="space-y-2">
        {items.map((item, i) => (
          <div
            key={i}
            className="flex items-start gap-3 rounded-md bg-control/40 border border-card px-3.5 py-2.5"
          >
            {item.icon}
            <span className="text-sm text-secondary leading-relaxed">{item.text}</span>
          </div>
        ))}
      </div>
      <label className="flex items-center gap-3 cursor-pointer rounded-lg border border-hover bg-control/60 px-4 py-3 hover:border-teal-600/40 hover:bg-control/80 transition">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => onAgreeChange(e.target.checked)}
          className="w-4 h-4 rounded border-hover bg-control text-teal-500 focus:ring-teal-500 focus:ring-offset-0 cursor-pointer"
        />
        <span className="text-sm font-medium text-primary select-none">
          I understand and agree to proceed
        </span>
      </label>
    </div>
  );
}
