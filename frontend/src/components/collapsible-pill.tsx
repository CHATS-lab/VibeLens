import { ChevronDown, ChevronRight } from "lucide-react";

interface CollapsiblePillProps {
  open: boolean;
  onToggle: () => void;
  icon: React.ReactNode;
  label: string;
  preview?: string;
  className: string;
  children: React.ReactNode;
}

export function CollapsiblePill({
  open,
  onToggle,
  icon,
  label,
  preview,
  className,
  children,
}: CollapsiblePillProps) {
  return (
    <div className={`rounded-lg border ${className} overflow-hidden`}>
      <button
        onClick={onToggle}
        className="flex items-center gap-2 w-full px-3 py-2 text-xs hover:bg-white/5 transition-colors"
      >
        {open ? (
          <ChevronDown className="w-3 h-3 shrink-0" />
        ) : (
          <ChevronRight className="w-3 h-3 shrink-0" />
        )}
        {icon}
        <span className="font-medium">{label}</span>
        {!open && preview && (
          <span className="text-zinc-500 truncate ml-1">{preview}</span>
        )}
      </button>
      {open && <div className="border-t border-inherit">{children}</div>}
    </div>
  );
}
