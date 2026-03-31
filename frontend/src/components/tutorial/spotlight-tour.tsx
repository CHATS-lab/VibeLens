import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  Eye,
  List,
  LayoutGrid,
  BarChart3,
  Sparkles,
  Upload,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { type TourStep, getStepsForMode, markTourSeen } from "./tour-steps";

const SPOTLIGHT_PADDING = 8;
const SPOTLIGHT_RADIUS = 12;
const RESIZE_DEBOUNCE_MS = 150;
const TRANSITION_DURATION = "0.3s";

const ICON_MAP: Record<string, React.ReactNode> = {
  eye: <Eye className="w-5 h-5 text-cyan-400" />,
  list: <List className="w-5 h-5 text-cyan-400" />,
  layout: <LayoutGrid className="w-5 h-5 text-cyan-400" />,
  "bar-chart": <BarChart3 className="w-5 h-5 text-cyan-400" />,
  sparkles: <Sparkles className="w-5 h-5 text-cyan-400" />,
  upload: <Upload className="w-5 h-5 text-violet-400" />,
};

interface SpotlightTourProps {
  onComplete: () => void;
  appMode: string;
}

interface TargetRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

function measureTarget(selector: string): TargetRect | null {
  const el = document.querySelector(`[data-tour="${selector}"]`);
  if (!el) return null;
  // Portal renders on document.body (outside #root zoom),
  // so raw viewport coords from getBoundingClientRect are correct as-is.
  const raw = el.getBoundingClientRect();
  return {
    top: raw.top,
    left: raw.left,
    width: raw.width,
    height: raw.height,
  };
}

const TOOLTIP_MARGIN = 16;
const TOOLTIP_WIDTH = 320;
const TOOLTIP_EST_HEIGHT = 180;

function computeTooltipPosition(
  rect: TargetRect,
  placement: TourStep["placement"]
): React.CSSProperties {
  const GAP = 12;
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  // Compute raw position, then clamp to keep tooltip inside viewport
  let top: number;
  let left: number | undefined;
  let right: number | undefined;

  switch (placement) {
    case "right":
      top = rect.top + rect.height / 2 - TOOLTIP_EST_HEIGHT / 2;
      left = rect.left + rect.width + SPOTLIGHT_PADDING + GAP;
      break;
    case "bottom":
      top = rect.top + rect.height + SPOTLIGHT_PADDING + GAP;
      left = rect.left + rect.width / 2 - TOOLTIP_WIDTH / 2;
      break;
    case "left":
      top = rect.top + rect.height / 2 - TOOLTIP_EST_HEIGHT / 2;
      right = vw - rect.left + SPOTLIGHT_PADDING + GAP;
      break;
  }

  // Clamp vertical position
  top = Math.max(TOOLTIP_MARGIN, Math.min(top, vh - TOOLTIP_EST_HEIGHT - TOOLTIP_MARGIN));

  // Clamp horizontal position
  if (left != null) {
    left = Math.max(TOOLTIP_MARGIN, Math.min(left, vw - TOOLTIP_WIDTH - TOOLTIP_MARGIN));
  }

  const style: React.CSSProperties = { top };
  if (right != null) style.right = right;
  else if (left != null) style.left = left;
  return style;
}

export function SpotlightTour({ onComplete, appMode }: SpotlightTourProps) {
  const steps = useMemo(() => getStepsForMode(appMode), [appMode]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [targetRect, setTargetRect] = useState<TargetRect | null>(null);
  const resizeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const currentStep = steps[currentIdx] as TourStep | undefined;

  const remeasure = useCallback(() => {
    if (!currentStep) return;
    const rect = measureTarget(currentStep.target);
    if (rect) {
      setTargetRect(rect);
    } else {
      // Target not found, auto-advance
      if (currentIdx < steps.length - 1) {
        setCurrentIdx((i) => i + 1);
      } else {
        markTourSeen();
        onComplete();
      }
    }
  }, [currentStep, currentIdx, steps.length, onComplete]);

  // Measure on step change
  useEffect(() => {
    remeasure();
  }, [remeasure]);

  // Debounced resize handler
  useEffect(() => {
    const handleResize = () => {
      if (resizeTimerRef.current) clearTimeout(resizeTimerRef.current);
      resizeTimerRef.current = setTimeout(remeasure, RESIZE_DEBOUNCE_MS);
    };
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      if (resizeTimerRef.current) clearTimeout(resizeTimerRef.current);
    };
  }, [remeasure]);

  // Keyboard navigation
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        markTourSeen();
        onComplete();
      } else if (e.key === "Enter" || e.key === "ArrowRight") {
        handleNext();
      } else if (e.key === "ArrowLeft") {
        handleBack();
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  });

  const handleNext = () => {
    if (currentIdx >= steps.length - 1) {
      markTourSeen();
      onComplete();
    } else {
      setCurrentIdx((i) => i + 1);
    }
  };

  const handleBack = () => {
    if (currentIdx > 0) {
      setCurrentIdx((i) => i - 1);
    }
  };

  const handleSkip = () => {
    markTourSeen();
    onComplete();
  };

  if (!currentStep || !targetRect) return null;

  const spotlightStyle: React.CSSProperties = {
    position: "fixed",
    top: targetRect.top - SPOTLIGHT_PADDING,
    left: targetRect.left - SPOTLIGHT_PADDING,
    width: targetRect.width + SPOTLIGHT_PADDING * 2,
    height: targetRect.height + SPOTLIGHT_PADDING * 2,
    borderRadius: SPOTLIGHT_RADIUS,
    boxShadow: "0 0 0 9999px rgba(0, 0, 0, 0.6)",
    pointerEvents: "none",
    zIndex: 9998,
    transition: `top ${TRANSITION_DURATION} ease, left ${TRANSITION_DURATION} ease, width ${TRANSITION_DURATION} ease, height ${TRANSITION_DURATION} ease`,
  };

  const tooltipStyle: React.CSSProperties = {
    position: "fixed",
    zIndex: 9999,
    ...computeTooltipPosition(targetRect, currentStep.placement),
  };

  const overlay = (
    <>
      {/* Clickable backdrop to prevent interaction behind spotlight */}
      <div
        className="fixed inset-0"
        style={{ zIndex: 9997 }}
        onClick={(e) => e.stopPropagation()}
      />

      {/* Spotlight cutout */}
      <div style={spotlightStyle} />

      {/* Tooltip card */}
      <div
        style={tooltipStyle}
        className="w-80 bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl p-4"
      >
        {/* Icon + Title */}
        <div className="flex items-center gap-2.5 mb-2">
          {ICON_MAP[currentStep.icon]}
          <h3 className="text-sm font-semibold text-white">{currentStep.title}</h3>
        </div>

        {/* Content */}
        <p className="text-sm text-zinc-300 leading-relaxed mb-4">
          {currentStep.content}
        </p>

        {/* Progress dots + buttons */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            {steps.map((_, i) => (
              <div
                key={i}
                className={`w-1.5 h-1.5 rounded-full transition ${
                  i === currentIdx
                    ? "bg-cyan-400"
                    : i < currentIdx
                      ? "bg-cyan-600/50"
                      : "bg-zinc-600"
                }`}
              />
            ))}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleSkip}
              className="px-2.5 py-1 text-xs text-zinc-500 hover:text-zinc-300 transition"
            >
              Skip
            </button>
            {currentIdx > 0 && (
              <button
                onClick={handleBack}
                className="flex items-center gap-1 px-2.5 py-1 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700 hover:border-zinc-600 rounded transition"
              >
                <ChevronLeft className="w-3 h-3" />
                Back
              </button>
            )}
            <button
              onClick={handleNext}
              className="flex items-center gap-1 px-3 py-1 text-xs font-medium text-white bg-cyan-600 hover:bg-cyan-500 rounded transition"
            >
              {currentIdx >= steps.length - 1 ? "Done" : "Next"}
              {currentIdx < steps.length - 1 && <ChevronRight className="w-3 h-3" />}
            </button>
          </div>
        </div>
      </div>
    </>
  );

  return createPortal(overlay, document.body);
}
