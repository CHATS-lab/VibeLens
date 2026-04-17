# VibeLens Design System

## 1. Visual Theme & Atmosphere

VibeLens is a developer tool for analyzing coding agent trajectories. The design prioritizes information density and readability across long sessions, with a dual-mode system that treats light and dark as equal citizens. The light mode draws from Apple's cool neutral palette -- near-white canvas, high-contrast black text hierarchy, and soft diffused shadows. The dark mode uses a zinc-based theme with softened near-white text and border-driven elevation, inspired by Linear's dark-first engineering tools.

The typography uses the system font stack (`-apple-system, BlinkMacSystemFont, Segoe UI, Roboto`) for UI chrome and Geist Mono for code, session IDs, and technical labels. The system is built on semantic color tokens via CSS custom properties, with Tailwind's `dark:` prefix handling mode switching. Every color has both a light and dark variant, defined in `:root` and `.dark` respectively.

The color story uses a cool neutral base with semantic accent colors that carry meaning rather than decoration. Cyan marks navigation and primary session context. Teal marks skills, tutorials, and guided actions. Violet marks sub-agents and continuation chains. Amber marks warnings and verification phases. Rose marks destructive actions and errors. These accents appear at low opacity for backgrounds and borders, with full saturation reserved for icons and interactive text.

**Key Characteristics:**
- Dual-mode: light (`#fafafa` canvas, `#ffffff` panels) and dark (`#09090b` canvas, `#18181b` panels)
- System font stack for UI, Geist Mono for code and technical content
- CSS custom properties for all colors, consumed via Tailwind `extend.colors`
- Semantic accent colors: cyan (navigation), teal (skills/tutorials), violet (sub-agents), amber (warnings), rose (destructive)
- `dark:` prefix pattern for dual-mode overrides: `text-cyan-800 dark:text-cyan-100`
- Accent colors at 6% opacity for light-mode backgrounds, 15-20% for dark-mode backgrounds
- High-contrast text hierarchy: 5 tiers from primary to faint
- Lucide React for all iconography
- No gradients on surfaces, no textures, no decorative elements

## 2. Color Palette & Roles

### Surfaces

| Token | Light | Dark | Use |
|-------|-------|------|-----|
| `canvas` | `#fafafa` | `#09090b` | Page background, outermost container |
| `panel` | `#ffffff` | `#18181b` | Cards, modals, elevated content areas |
| `control` | `#f0f0f2` | `#27272a` | Input backgrounds, toggle containers, inactive controls |
| `control-hover` | `#e5e5ea` | `#3f3f46` | Hover state for controls and interactive surfaces |
| `subtle` | `rgba(0,0,0,0.025)` | `rgba(39,39,42,0.5)` | Barely-visible tinting for depth |
| `overlay` | `rgba(0,0,0,0.45)` | `rgba(0,0,0,0.6)` | Modal backdrop |

### Text

| Token | Light | Dark | Use |
|-------|-------|------|-----|
| `primary` | `#000000` | `#f4f4f5` | Headings, names, primary content |
| `secondary` | `#1d1d1f` | `#e4e4e7` | Body text, descriptions |
| `muted` | `#48484a` | `#a1a1aa` | Labels, metadata |
| `dimmed` | `#6e6e73` | `#71717a` | Timestamps, tertiary info |
| `faint` | `#aeaeb2` | `#52525b` | Placeholders, disabled states |
| `on-accent` | `#ffffff` | `#ffffff` | Text on filled accent buttons |

### Borders

Dark mode borders use semi-transparent white for natural depth on dark surfaces, not solid zinc values.

| Token | Light | Dark | Use |
|-------|-------|------|-----|
| `default` | `#e5e5ea` | `rgba(255,255,255,0.06)` | Panel boundary borders (`border-l` on right sidebars) |
| `card` | `rgba(0,0,0,0.08)` | `rgba(255,255,255,0.04)` | Row dividers, interior card borders |
| `control` | `#d1d1d6` | `rgba(255,255,255,0.07)` | Input field borders |
| `hover` | `#c7c7cc` | `rgba(255,255,255,0.10)` | Border on hover |

**Border hierarchy:** `default` (6% white) is used for structural boundaries like panel edges. `card` (4% white) is used for softer interior dividers between rows and list items. This two-tier system keeps panel boundaries visible while row dividers remain subtle.

### Accent Colors

Each accent defines a full token set: base (icons/text), bg (filled buttons), subtle (background tint), border, focus, shadow.

| Accent | Light Base | Dark Base | Semantic Role |
|--------|-----------|-----------|---------------|
| **Cyan** | `#0e7490` | `#22d3ee` | Navigation, session IDs, primary interactive |
| **Teal** | `#0f766e` | `#5eead4` | Skills, tutorials, guided actions |
| **Violet** | `#6d28d9` | `#a78bfa` | Sub-agents, continuation chains |
| **Amber** | `#b45309` | `#fcd34d` | Warnings, verification, star ratings |
| **Rose** | `#be123c` | `#fda4af` | Destructive actions, errors, donate |
| **Emerald** | `#047857` | `#34d399` | Success states, installed/synced |
| **Indigo** | `#4338ca` | `#a5b4fc` | Mixed phases, secondary grouping |
| **Blue** | `#1d4ed8` | `#60a5fa` | Exploration phase, view toggles |

### Accent Opacity Scale

Accent token suffixes follow a consistent opacity pattern:

| Suffix | Light Opacity | Dark Opacity | Use |
|--------|--------------|--------------|-----|
| `-subtle` | 6% | 15-20% | Background tint for cards, badges |
| `-border` | 15-18% | 25-40% | Colored borders on accent containers |
| `-muted` | 10% | 35% | Slightly stronger tint (cyan only) |
| `-shadow` | 10% | 40% | Focus ring shadows |

## 3. Typography Rules

### Font Families

| Role | Stack | Use |
|------|-------|-----|
| UI / Body | `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif` | All interface text |
| Code / Numbers | `'Geist Mono', 'SF Mono', 'Fira Code', 'Fira Mono', 'Roboto Mono', monospace` | Code blocks, token counts, costs, session IDs |

Geist Mono is loaded via Google Fonts at weights 400, 500, and 600.

### Hierarchy

| Role | Classes | Use |
|------|---------|-----|
| Page heading | `text-lg font-bold text-primary` | Panel titles, dialog headers |
| Section heading | `text-sm font-semibold text-primary` | Section labels within panels |
| Body | `text-sm text-secondary` | Descriptions, body content |
| Label | `text-xs text-muted` | Metadata, counts, timestamps |
| Caption | `text-[11px] text-muted` | Stat card descriptions, small labels |
| Micro | `text-[10px] text-dimmed` | Badge text, tool counts |
| Nano | `text-[9px] uppercase tracking-wider` | Auto-prompt labels |
| Code | `font-mono text-sm text-primary` | Skill names, session IDs |
| Code small | `font-mono text-[11px]` | Tool chip names, prompt indices |

### Principles
- Text color always uses semantic tokens (`text-primary`, `text-secondary`, etc.) for content that must adapt to both modes
- Tailwind color classes with `dark:` prefix for inline colored text: `text-cyan-800 dark:text-cyan-100`
- Never use raw hex colors in component classes; all theme colors flow through CSS custom properties
- `font-mono` for anything the user might want to copy: skill names, session IDs, file paths, tool names
- `tabular-nums` on all numeric values for column alignment

## 4. Component Patterns

### Buttons

**Primary (Teal CTA)**
- Classes: `px-3 py-1.5 text-xs font-medium text-white bg-teal-600 hover:bg-teal-500 rounded-md transition`
- Use: "New Skill", "Install", primary actions

**Secondary (Ghost)**
- Classes: `px-3 py-1.5 text-xs font-medium text-secondary hover:text-primary bg-control hover:bg-control-hover border border-card rounded-md transition`
- Use: Refresh, close, secondary actions

**Destructive (Inline)**
- Classes: `text-dimmed hover:text-red-600 dark:hover:text-red-400 hover:bg-control-hover rounded transition`
- Use: Delete buttons (icon-only in lists)

**Toggle (Segmented Control) -- Simple**
- Container: `flex gap-0.5 bg-control rounded p-0.5`
- Active: `bg-control-hover text-primary`
- Inactive: `text-dimmed hover:text-secondary`
- Use: Small metric/time-group toggles (e.g., Day/Month/Year in charts)
- Defined as shared constants in `styles.ts`: `TOGGLE_CONTAINER`, `TOGGLE_ACTIVE`, `TOGGLE_INACTIVE`

**Toggle (Segmented Control) -- Apple-style Pill**
- Container: `flex rounded-lg bg-zinc-100 dark:bg-zinc-800/60 p-0.5`
- Active: `bg-white dark:bg-zinc-700 text-primary font-semibold shadow-sm`
- Inactive: `text-muted hover:text-secondary`
- Use: Primary mode switches (View Mode: Concise/Detail/Workflow, Nav Mode: User/Sub-Agents)
- Uses hardcoded zinc values (not semantic tokens) for the distinctive white-pill-on-gray-track appearance

### Cards

**Skill Card (Local/Explore)**
- Container: `border border-card rounded-lg bg-panel hover:bg-control/80 transition`
- Title: `font-mono text-base font-bold text-primary`
- Description: `text-sm text-secondary mt-1 line-clamp-2`
- Icon container: `p-1.5 rounded-md bg-accent-teal-subtle`

**Installed Skill Card (Explore)**
- Container: `border-emerald-300/40 bg-emerald-50 hover:bg-emerald-100/80 dark:border-emerald-800/40 dark:bg-emerald-950/20 dark:hover:bg-emerald-950/30`
- Green tint signals "already installed" state

**Flow Card (Workflow Diagram)**

Flow cards use a dual-mode strategy: neutral zinc in light mode for readability, colored accents in dark mode for visual richness.

- Agent card: `border-zinc-200 dark:border-cyan-500/20 bg-zinc-50/50 dark:bg-cyan-950/20 hover:border-zinc-300 dark:hover:border-cyan-400/35`
- User anchor (manual): `border-zinc-200 dark:border-cyan-500/25 bg-zinc-50/50 dark:bg-cyan-950/20`
- User anchor (auto-prompt): `border-zinc-200 dark:border-teal-500/20 bg-zinc-50/50 dark:bg-teal-950/20`
- Agent text: `text-zinc-800 dark:text-cyan-100`
- Icon container: `bg-zinc-100 border-zinc-200/50 dark:bg-cyan-500/20 dark:border-cyan-400/15`

**Tool Chip (Workflow Diagram)**
- Base: category-colored `bg-{color}-500/20` with `text-{color}-600 dark:text-{color}-300`
- Highlight on hover: `ring-2 ring-{color}-400/60`

### Tutorial Banners

All tutorial/info banners follow a consistent pattern:

```
border border-{color}-300 dark:border-{color}-800/40
bg-{color}-50 dark:bg-{color}-950/20
```

- Icon container: `bg-{color}-100 dark:bg-{color}-500/15 border border-{color}-200 dark:border-{color}-500/20`
- Icon: `text-{color}-600 dark:text-{color}-400`
- Title: `text-primary` (always semantic, never colored)
- Description: `text-secondary` (always semantic)

Supported colors: teal (skills), cyan (session viewer), amber (friction analysis).

### Modals

- Always use shared `Modal` / `ModalHeader` / `ModalBody` / `ModalFooter` from `components/ui/modal.tsx`
- Background: `bg-panel` with `border border-card`
- Overlay: `bg-overlay` backdrop with `backdrop-blur-sm`

### Tooltips

- Always use shared `Tooltip` from `components/ui/tooltip.tsx`
- Renders via portal, shows instantly, auto-flips
- Never use native `title` attributes

### Right Sidebar Panels

- Width: `SIDEBAR_DEFAULT_WIDTH` (252px), min 180px, max 400px from `styles.ts`
- Background: `bg-canvas` with `border-l border-default`
- All sidebar panels (prompt nav, friction history, skills history) share these dimensions

### Custom Dropdowns

Use custom dropdown components instead of native `<select>` elements. Native selects break the dark theme.

### Error Banners

```
flex items-start gap-2 px-4 py-3 rounded-lg
bg-red-50 dark:bg-red-900/20
border border-red-200 dark:border-red-800/30
```
- Icon: `text-red-600 dark:text-red-400`
- Text: `text-red-700 dark:text-red-300`

## 5. Layout Principles

### App Shell

```
Root:    flex h-full overflow-hidden bg-canvas text-primary
Left:    Sidebar (resizable, default 280px), bg-panel, border-r border-default
Center:  Main content (flex-1), bg-canvas
Right:   Optional panel (default 252px), border-l border-default, bg-canvas
```

### Spacing
- Base unit: Tailwind's 4px scale (`gap-1` = 4px, `gap-2` = 8px, etc.)
- Panel padding: `px-6 py-8` for main content areas
- Card padding: `px-4 py-3` for list items
- Section gaps: `space-y-2` for card lists, `mb-4`/`mb-5` between sections

### Widths
- Main content: `max-w-5xl mx-auto` for skills panels
- Flow diagram: `max-w-3xl mx-auto` for workflow view
- Sidebar: 252px default (resizable 180-400px)
- Dashboard: `max-w-[1400px] mx-auto`

### Content Pattern
- Filter bars sit above search bars, both above content lists
- Error banners appear between controls and content
- Loading/empty states center vertically in the content area
- Pagination at bottom of lists, hidden when total fits in one page

### Shared Width Constants

```
SIDEBAR_DEFAULT_WIDTH = 252
SIDEBAR_MIN_WIDTH     = 180
SIDEBAR_MAX_WIDTH     = 400
```

All right-side panels must use these shared values. Never hardcode panel widths locally.

## 6. Depth & Elevation

| Level | Light | Dark | Use |
|-------|-------|------|-----|
| Flat | `bg-canvas` | `bg-canvas` | Page background |
| Surface | `bg-panel` | `bg-panel` | Cards, modals, sidebar |
| Control | `bg-control` | `bg-control` | Inputs, toggles, inactive tabs |
| Hover | `bg-control-hover` | `bg-control-hover` | Hover states, active tabs |
| Card shadow | `0 1px 3px rgba(0,0,0,0.06), 0 2px 8px rgba(0,0,0,0.04)` | `none` | Light mode card elevation |

**Shadow philosophy:** Light mode uses Apple-inspired soft diffused shadows for subtle elevation. Dark mode uses no shadows; elevation is communicated through background luminance steps (`#09090b` < `#18181b` < `#27272a` < `#3f3f46`). Borders on dark mode are semi-transparent white (`rgba(255,255,255,0.04-0.06)`) to provide structure without visual noise.

### Border Radius Scale

| Size | Tailwind | Use |
|------|----------|-----|
| Micro | `rounded` (4px) | Small controls, inputs, toggle buttons |
| Standard | `rounded-md` (6px) | Buttons, dropdown items |
| Comfortable | `rounded-lg` (8px) | Cards, modals, banners, code blocks |
| Large | `rounded-xl` (12px) | Dashboard stat cards, chart panels |
| Full | `rounded-full` | Pills, progress bars, status dots |

## 7. Phase & Category Colors

### Workflow Phases

Used in flow diagram sections and nav panel entries:

| Phase | Border | Label | Dot |
|-------|--------|-------|-----|
| Exploration | `border-l-blue-400` | `text-blue-600 dark:text-blue-400` | `bg-blue-400` |
| Implementation | `border-l-emerald-400` | `text-emerald-600 dark:text-emerald-400` | `bg-emerald-400` |
| Debugging | `border-l-red-400` | `text-red-600 dark:text-red-400` | `bg-red-400` |
| Verification | `border-l-amber-400` | `text-amber-600 dark:text-amber-400` | `bg-amber-400` |
| Planning | `border-l-violet-400` | `text-violet-600 dark:text-violet-400` | `bg-violet-400` |
| Mixed | `border-l-indigo-400` | `text-indigo-600 dark:text-indigo-400` | `bg-indigo-400` |

### Tool Categories

Used in flow diagram tool chips and category breakdowns:

| Category | Background | Text | Label | Tools |
|----------|-----------|------|-------|-------|
| File Read | `bg-blue-500/20` | `text-blue-600 dark:text-blue-300` | read | Read, NotebookRead, cat |
| File Write | `bg-emerald-500/20` | `text-emerald-600 dark:text-emerald-300` | write | Edit, Write, NotebookEdit, MultiEdit, apply_patch |
| Shell | `bg-amber-500/20` | `text-amber-600 dark:text-amber-300` | shell | Bash, execute_command |
| Search | `bg-sky-500/20` | `text-sky-600 dark:text-sky-300` | search | Glob, Grep, find, LS |
| Web | `bg-orange-500/20` | `text-orange-600 dark:text-orange-300` | web | WebSearch, WebFetch |
| Agent | `bg-violet-500/20` | `text-violet-600 dark:text-violet-300` | agent | Agent, Task, Skill |
| Task | `bg-rose-500/20` | `text-rose-600 dark:text-rose-300` | task | TaskCreate, TaskUpdate, TaskList, TaskGet, TaskOutput, TaskStop, TodoWrite, TodoRead |
| Interact | `bg-cyan-500/20` | `text-cyan-600 dark:text-cyan-300` | interact | AskUserQuestion, AskUser, EnterPlanMode, ExitPlanMode, EnterWorktree |
| Other | `bg-zinc-500/20` | `text-zinc-500 dark:text-zinc-400` | other | (fallback for unmapped tools) |

Tool category mappings are maintained in parallel: `frontend/src/components/conversation/flow-layout.ts` (TypeScript) and `src/vibelens/services/session/tool_categories.py` (Python). Both must be kept in sync.

### Severity Colors (Friction Analysis)

| Level | Light | Dark |
|-------|-------|------|
| 1 (info) | `bg-control-hover/50 text-secondary` | Same (semantic tokens) |
| 2 (low) | `bg-sky-50 text-sky-700 border-sky-200` | `bg-sky-900/40 text-sky-300 border-sky-700/30` |
| 3 (medium) | `bg-yellow-50 text-yellow-700 border-yellow-200` | `bg-yellow-900/40 text-yellow-300 border-yellow-700/30` |
| 4 (high) | `bg-orange-50 text-orange-700 border-orange-200` | `bg-orange-900/50 text-orange-200 border-orange-600/40` |
| 5 (critical) | `bg-rose-50 text-rose-700 border-rose-200` | `bg-rose-900/50 text-rose-200 border-rose-600/40` |

## 8. Do's and Don'ts

### Do
- Use CSS custom properties for all theme colors; consume via Tailwind `extend.colors` tokens
- Use `dark:` prefix for every color that differs between modes: `text-cyan-800 dark:text-cyan-100`
- Use semantic text tokens (`text-primary`, `text-secondary`) for content text
- Use `bg-panel` for card/block backgrounds, `bg-canvas` for page background
- Use the shared Modal, Tooltip, and sidebar dimension constants
- Keep tutorial banners consistent: `text-primary` title, `text-secondary` description, flat colored background
- Match existing patterns when adding new components
- Use `font-mono` for technical identifiers (skill names, session IDs, file paths)
- Use `font-mono tabular-nums` for all numeric data
- Apply `transition` or `transition-colors` on all interactive elements

### Don't
- Don't use raw dark-only colors without a light equivalent: `text-cyan-100` alone is invisible in light mode
- Don't use `hover:brightness-125` as a hover effect; it does nothing meaningful on light backgrounds. Use `hover:bg-control-hover` or explicit hover colors
- Don't use CSS variable values with Tailwind opacity modifiers (`border-card/40`); the `/40` suffix silently fails on CSS variables containing hex or rgba
- Don't use `bg-subtle` for content cards; use `bg-panel` for a clean white/dark-zinc appearance
- Don't use gradients or radial overlays on tutorial/info banners; use flat colored backgrounds
- Don't hardcode sidebar widths; use `SIDEBAR_DEFAULT_WIDTH` / `SIDEBAR_MIN_WIDTH` / `SIDEBAR_MAX_WIDTH` from `styles.ts`
- Don't use native `<select>` elements; they break the dark theme. Use custom dropdown components
- Don't use native `title` attributes; they have delayed display and unstyled appearance. Use the shared Tooltip
- Don't hand-roll modal overlay markup; use the shared `Modal` component
- Don't add decorative elements, illustrations, or ornamental spacing

## 9. File Architecture

### Theme Definition
- `frontend/src/index.css` -- CSS custom properties in `:root` (light) and `.dark` (dark)
- `frontend/tailwind.config.js` -- Maps CSS variables to Tailwind token names via `extend.colors`
- `frontend/src/styles.ts` -- Shared constants: phase colors, category styles, severity colors, layout dimensions

### Component Structure
Feature panels follow a consistent file-splitting pattern:
- `*-panel.tsx` -- Thin orchestrator with tab routing and top-level state
- `*-tab.tsx` -- One file per tab with its own state management
- `*-cards.tsx` -- Card and detail popup components
- `*-shared.tsx` -- Reusable sub-components (search bars, filter bars, empty states)
- `*-constants.ts` -- Color maps, label maps, config arrays

### Shared Primitives
- `components/ui/modal.tsx` -- `Modal`, `ModalHeader`, `ModalBody`, `ModalFooter`
- `components/ui/tooltip.tsx` -- Portal-rendered `Tooltip` with auto-flip
- `components/ui/confirm-dialog.tsx` -- Confirmation dialogs for destructive actions
- `components/ui/markdown-renderer.tsx` -- Syntax-highlighted markdown rendering

## 10. Chart & Data Visualization

### Chart Colors (via CSS variables)

| Token | Light | Dark | Use |
|-------|-------|------|-----|
| `chart-line` | `rgb(8,145,178)` | `rgb(34,211,238)` | Line strokes |
| `chart-area-start` | `rgba(8,145,178,0.15)` | `rgba(34,211,238,0.3)` | Area gradient top |
| `chart-area-end` | `rgba(8,145,178,0.02)` | `rgba(34,211,238,0.02)` | Area gradient bottom |
| `chart-grid` | `rgba(0,0,0,0.06)` | `rgba(255,255,255,0.06)` | Grid lines |
| `chart-axis` | `rgba(0,0,0,0.1)` | `rgba(255,255,255,0.08)` | Axis baselines |
| `chart-text` | `#6e6e73` | `#a1a1aa` | Axis labels |

### Heatmap (5-level scale)

Level 0 uses neutral gray (not cyan) so empty cells form a visible grid without implying activity.

| Level | Light | Dark |
|-------|-------|------|
| 0 | `rgba(0,0,0,0.04)` | `rgba(255,255,255,0.04)` |
| 1 | `rgba(8,145,178,0.15)` | `rgba(34,211,238,0.20)` |
| 2 | `rgba(8,145,178,0.30)` | `rgba(34,211,238,0.40)` |
| 3 | `rgba(8,145,178,0.50)` | `rgba(34,211,238,0.60)` |
| 4 | `rgba(8,145,178,0.70)` | `rgba(34,211,238,0.80)` |

### Scrollbar

| Part | Light | Dark |
|------|-------|------|
| Thumb | `rgba(0,0,0,0.15)` | `rgba(63,63,70,0.5)` |
| Thumb hover | `rgba(0,0,0,0.25)` | `rgba(82,82,91,0.7)` |
| Width/height | 6px | 6px |
| Border radius | 3px | 3px |

## 11. Loading & Empty States

### Loading Spinners

Three tiers of loading indication, each for a different context:

**Page-level: Concentric Rings (`LoadingSpinnerRings`)**
- Defined in `components/loading-spinner.tsx`
- Three rotating rings at different speeds (3s, 1.8s, 1s) with a pulsing center dot and a soft glow backdrop
- Color prop: `"cyan"` (default), `"amber"`, or `"teal"`
- Wrapped by `LoadingSpinner` which adds an optional label and sublabel
- Use: Full-page or full-panel loading (session loading, dashboard loading, shared session loading)

**Section-level: `Loader2` icon (w-4 to w-6)**
- From `lucide-react`, with `animate-spin`
- Dual-mode color: `text-zinc-400 dark:text-cyan-400/60` -- neutral gray in light mode, cyan tint in dark mode
- Use: Panel loading (history sidebar, skill content, modal content)

**Button-level: `Loader2` icon (w-3 to w-3.5)**
- Inherits text color from the parent button context
- Use: Inline spinners in buttons during async operations (export, save, install)

### Empty States

Empty states use a centered icon + title + subtitle pattern:

```
<div className="flex flex-col items-center justify-center py-12 gap-2">
  <Icon className="w-8 h-8 text-faint" />
  <p className="text-sm text-muted">Primary message</p>
  <p className="text-xs text-dimmed">Secondary explanation</p>
</div>
```

The shared `EmptyState` component in `skills/skill-shared.tsx` provides a reusable version.

## 12. List & History Patterns

### Flat Row Pattern (History Cards)

History cards in right sidebar panels (skills history, friction history) use a flat row design that mirrors the left sidebar's session list:

- Row: `border-b border-card` bottom divider (no card border, no background)
- Hover: `hover:bg-zinc-100 dark:hover:bg-zinc-800/60`
- Layout: Title on first line, metadata (session count, cost, duration, date) on subsequent lines
- Session count: subtle `text-accent-cyan/70` for visual accent
- Running indicator: `border-b border-card animate-pulse` (no colored badge)
- Example tag: amber bordered tag `bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700/50`

### Session List (Left Sidebar)

- Row dividers: `border-b border-card`
- Project group headers: `border-b border-card`
- Active session: `bg-accent-cyan-subtle` highlight
- Hover: `hover:bg-control/60`
