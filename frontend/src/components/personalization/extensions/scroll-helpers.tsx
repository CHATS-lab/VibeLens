import { ArrowDown, ArrowUp } from "lucide-react";
import { useCallback, useMemo, useRef } from "react";

/** Sticky wrapper for a search/filter row so it stays visible while scrolling. */
export function StickyHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="sticky top-0 z-20 -mx-6 px-6 py-2 bg-panel/95 backdrop-blur supports-[backdrop-filter]:bg-panel/80 border-b border-card mb-3">
      {children}
    </div>
  );
}

/**
 * Provides refs for top/bottom sentinel markers and a pair of floating
 * scroll-to-top/bottom buttons. Place the sentinels at the start and end of
 * the scrollable content, and render `scrollButtons` anywhere inside the tab.
 */
export function useScrollAnchors() {
  const topRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const scrollToTop = useCallback(() => {
    topRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);
  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, []);

  const scrollButtons = useMemo(
    () => (
      <div className="fixed bottom-6 right-6 z-30 flex flex-col gap-2">
        <button
          type="button"
          onClick={scrollToTop}
          aria-label="Scroll to top"
          className="p-2.5 bg-panel hover:bg-control-hover border border-card rounded-full shadow-md text-muted hover:text-primary transition"
        >
          <ArrowUp className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={scrollToBottom}
          aria-label="Scroll to bottom"
          className="p-2.5 bg-panel hover:bg-control-hover border border-card rounded-full shadow-md text-muted hover:text-primary transition"
        >
          <ArrowDown className="w-4 h-4" />
        </button>
      </div>
    ),
    [scrollToTop, scrollToBottom],
  );

  return { topRef, bottomRef, scrollButtons };
}
