import { MAX_VISIBLE_PAGES } from "./extension-constants";

interface ExtensionPaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

/** Builds the list of page numbers (and "..." ellipsis strings) to display. */
function buildPageNumbers(page: number, totalPages: number): (number | "...")[] {
  if (totalPages <= MAX_VISIBLE_PAGES) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  // Window around current page (excluding first and last)
  const windowSize = MAX_VISIBLE_PAGES - 4; // slots for first, ..., ..., last
  const windowStart = Math.max(2, page - Math.floor(windowSize / 2));
  const windowEnd = Math.min(totalPages - 1, windowStart + windowSize - 1);

  const pages: (number | "...")[] = [1];

  if (windowStart > 2) pages.push("...");
  for (let i = windowStart; i <= windowEnd; i++) pages.push(i);
  if (windowEnd < totalPages - 1) pages.push("...");

  pages.push(totalPages);
  return pages;
}

export function ExtensionPagination({ page, totalPages, onPageChange }: ExtensionPaginationProps) {
  if (totalPages <= 1) return null;

  const pageNumbers = buildPageNumbers(page, totalPages);

  const navButtonClass =
    "px-3 py-1.5 text-xs bg-control text-muted border border-card rounded transition hover:text-secondary disabled:opacity-30";
  const activeClass = "bg-teal-600 text-white dark:bg-teal-500 border-transparent";
  const inactiveClass = "bg-control text-muted border border-card hover:text-secondary";

  return (
    <div className="flex items-center justify-center gap-1.5 mt-6 flex-wrap">
      <button
        onClick={() => onPageChange(Math.max(1, page - 1))}
        disabled={page === 1}
        className={navButtonClass}
      >
        &lt;
      </button>

      {pageNumbers.map((p, idx) =>
        p === "..." ? (
          <span key={`ellipsis-${idx}`} className="px-2 py-1.5 text-xs text-muted select-none">
            ...
          </span>
        ) : (
          <button
            key={p}
            onClick={() => onPageChange(p)}
            className={`px-3 py-1.5 text-xs rounded transition ${p === page ? activeClass : inactiveClass}`}
          >
            {p}
          </button>
        ),
      )}

      <button
        onClick={() => onPageChange(Math.min(totalPages, page + 1))}
        disabled={page === totalPages}
        className={navButtonClass}
      >
        &gt;
      </button>
    </div>
  );
}
