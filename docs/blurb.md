# VibeLens Blurb

## Elevator Pitch

Your agent finished a task — but what actually happened in there? VibeLens replays your Claude Code, Codex, and Gemini sessions with full cost and friction tracking.

## README Blurb

Your AI coding agents run hundreds of tool calls, burn thousands of tokens, and you have no idea what happened. VibeLens changes that.

- **Session visualization.** Step-by-step timeline with every tool call, thinking block, and sub-agent spawn.
- **Dashboard Analytics.** Cost breakdowns by model, peak-hour histograms, and per-project drill-downs.
- **Productivity Tips.** Flags retries, circular debugging, and abandoned approaches — with suggested fixes.
- **Skill personalization.** Recommend, create, and evolve reusable skills from your session history.
- **Session sharing.** Share your interactions with your teammates with a link.

Works with Claude Code, Codex, Gemini, and OpenClaw out of the box.

```
pip install vibelens && vibelens serve
```

## Social Post

### Twitter / X (English)

VibeLens: Let your agent know you better!

Your agent repeats the same mistakes. Every new session, it forgets your preferences.

VibeLens reveals your usage patterns and makes your agent actually learn from them:

- session visualization with every tool call and thinking block
- dashboard analytics to see where your tokens actually go
- productivity tips that spot retry loops and wasted approaches
- personalization: retrieve, customize, and evolve skills from your real sessions

works with Claude Code, Codex, Gemini CLI, OpenClaw. one install. no cloud.

`pip install vibelens`

https://github.com/yejh123/VibeLens

### Concise

Your agent repeats the same mistakes?

VibeLens reveals your usage patterns and makes your agent actually learn from them:

- Session visualization
- Dashboard analytics
- Personalize your skills
- Productivity tips summarized from your sessions

Works with different agents.

`pip install vibelens && vibelens serve`

https://github.com/yejh123/VibeLens

### Twitter / X (Chinese)

你的 AI 编程 agent 说 "搞定了"

你完全不知道它干了什么

VibeLens 逐步回放每个 session：

· 会话可视化，每个 tool call、thinking block 一览无余
· 数据看板，按模型和项目拆分 token 消耗
· 效率建议，定位重试循环和无效调试
· 个性化：检索、定制、进化 skills，从你的真实 session 中学习

支持 Claude Code / Codex / Gemini CLI / OpenClaw。一行安装，数据不出本机。

`pip install vibelens`

https://github.com/yejh123/VibeLens

### LinkedIn

I've been running AI coding agents for months but never looked at what they actually do turn by turn. Set up VibeLens yesterday — pip install, one command, done. It reads your local Claude Code / Codex / Gemini session files and shows you an interactive replay.

The friction detection alone was worth it. Found sessions where the agent looped on a failing test instead of changing approach. The skill personalization is the real killer — it analyzes your sessions and auto-generates reusable skills to prevent the same mistakes.

Works with Claude Code, Codex CLI, Gemini CLI, and OpenClaw. Fully local, nothing leaves your machine, open source.

`pip install vibelens && vibelens serve`

## 四宫格漫画 — "The 3am Ghost"

### Image Generation Prompt

```
Create a 4-panel comic strip arranged in a 2x2 grid. The overall image is square (2754 × 1536 px).

Each panel occupies one quadrant, separated by 8px white gutters. Each panel has a 3px black border with 6px rounded corners. A bold black title label centered at the top of each panel in 14pt sans-serif font.

Reading order numbers: Each panel has a small circled number in its top-left corner (inside the panel, 4px from the edges). The number is white text on a solid dark-gray (#333) circle, 18px diameter, clean sans-serif font. Panel 1 = ①, Panel 2 = ②, Panel 3 = ③, Panel 4 = ④. Reading order: top-left → top-right → bottom-left → bottom-right.

--- ART STYLE ---
Chibi / kawaii cartoon, similar to Webtoon or LINE sticker illustrations. Characters have oversized round heads (head-to-body ratio ~2:1), big circular expressive eyes with white highlights, small dot noses, rosy pink circle cheeks, stubby rounded limbs. Thick black outlines (2-3px), bright saturated flat colors with minimal shading (one shadow tone per surface, no gradients). Clean vector-like line art. Backgrounds use soft warm lighting with a slight vignette at panel edges. No crosshatching, no realistic textures.

Speech bubbles: white fill, 2px black outline, rounded rectangular shape with a triangular tail pointing to the speaker. Text inside is black, clean sans-serif, 10-11pt. Thought bubbles: white fill, 2px black outline, cloud-shaped with small trailing circles instead of a tail.

Callout bubbles (Panel 3 only): rounded rectangles with colored left border (amber, green). White fill, 9pt black sans-serif text. A thin dashed line connects each callout to a region of the monitor.

--- CHARACTERS ---
Alex: Short spiky dark-brown messy hair, big round brown eyes, rosy cheeks, wearing a solid blue zip-up hoodie with the zipper half-open over a white t-shirt, black over-ear headphones resting around his neck. Blue jeans, white sneakers. Appears in all 4 panels.

Junior: Short neat blonde hair swept to the side, green eyes, rosy cheeks, wearing a solid green pullover hoodie, dark gray joggers, gray sneakers. Confident relaxed posture. Appears in Panels 1 and 4 only.

Both characters maintain identical designs (hair, clothing, face) across every panel they appear in.

--- ENVIRONMENT ---
Setting: A modern startup-style office with light wood desks, ergonomic black mesh chairs, a small potted succulent on each desk, and a gray carpeted floor. The back wall is light beige with a single framed motivational poster (unreadable text, abstract geometric art). Overhead warm-white panel lighting. Each desk has a silver laptop and/or a 24-inch widescreen monitor on a slim monitor arm.

--- PANEL 1 (top-left) — Title: The Hype ---
Composition: Two-shot. Junior sits in his chair on the left side of the panel, leaning back casually with his left ankle crossed over his left knee. His 24-inch monitor is on the desk, screen facing slightly toward the viewer, displaying an AI coding agent interface: a dark terminal-style window with a friendly round robot face icon (simple circle head, two dot eyes, small antenna) centered at the top, and 5-6 lines of colored code text below it with a blinking green cursor at the bottom, suggesting an active coding session. His left hand gestures toward the monitor.

Alex stands to the right of the frame, holding a white coffee mug in his left hand at chest height. His posture is slightly leaning forward, eyebrows raised, mouth a small "o" shape — impressed but skeptical. A tiny sweat drop floats near his temple.

Junior's speech bubble (top-left of panel, tail pointing down-left to Junior):
"Done in 30 minutes!"

Alex's thought bubble (top-right of panel, cloud shape with trailing circles pointing to Alex's head):
"I should try this agent too..."

Background: Office desk, succulent plant, the motivational poster on the wall behind them.

--- PANEL 2 (top-right) — Title: The Frustration ---
Composition: Solo shot of Alex. Alex sits at his desk, center-frame, hunched forward with both hands gripping the sides of his head. His eyes are squeezed shut, mouth open in a frustrated grimace, with a small angry vein mark (cross shape) on his forehead. Three red anger lines radiate from his head.

His 24-inch monitor is directly behind him, displaying a code diff view: a dark background with lines of code highlighted in red (deletions) and green (additions). The diff is blurry/impressionistic but clearly a code editor with a split pane. A small yellow sticky note is stuck to the top-right corner of the monitor bezel, reading "CLAUDE.md" in tiny handwritten text, with a small red arrow drawn pointing to the screen.

On the desk surface: two crumpled white paper balls, his open silver laptop pushed to the side, and the succulent.

Alex's speech bubble 1 (upper-right, tail pointing to Alex):
"Same mistake. AGAIN!"

Alex's speech bubble 2 (lower-left, tail pointing to Alex, slightly smaller):
"I told you three times already!"

Background: Same office wall, slightly dimmer warm lighting to convey late-night frustration.

--- PANEL 3 (bottom-left) — Title: VibeLens Reveals ---
Composition: Solo shot of Alex, viewed from a slight over-the-shoulder angle (Alex on the left, monitor on the right taking up ~60% of the panel). Alex sits upright, turned toward the monitor, one hand on his chin in a curious thinking pose. His eyes are wide open, eyebrows raised, mouth slightly open in an "aha" expression.

The 24-inch monitor displays the VibeLens dashboard: a dark navy/charcoal background (#0f172a). The screen layout (impressionistic but recognizable):
- Top-left corner of the screen: only the word "VibeLens" in cyan sans-serif text.
- Main area center: a Productivity Tip module.
- Main area bottom: a Personalization module.

Two colored callout bubbles float around the monitor, connected by thin dashed lines to different parts of the screen:

Callout 1 (upper-right, amber left-border, connected to the bar chart):
"Tip: Add naming rules to CLAUDE.md"

Callout 2 (lower-right, green left-border, connected to the bottom chart area):
"Skill: Enforce project conventions"

Alex's speech bubble (bottom-left of panel, tail pointing up to Alex):
"So THAT'S why it keeps doing that..."

Background: Same desk, succulent, slightly brighter warm lighting than Panel 2 (mood is shifting positive).

--- PANEL 4 (bottom-right) — Title: Nailed It ---
Composition: Two-shot. Alex sits confidently at his desk, center-left of the frame, leaning back slightly with a wide satisfied smile, eyes happy (curved upward like anime happy eyes ^^). His left hand rests on the desk, his right hand gives a thumbs-up toward the viewer.

He now has TWO monitors on his desk, arranged side by side:
- Left monitor: Shows a text editor with a CLAUDE.md file. Dark editor background, with 8-10 lines of text visible. A tab bar at the top with a small file icon (white page with a folded corner) and the label "CLAUDE.md" in white text. Three lines are highlighted with a faint green/teal background glow, suggesting active rule sections. A small green checkmark icon is visible in the top-right of the editor tab bar.
- Right monitor: Shows VibeLens dashboard (same dark navy theme as Panel 3). Top-left corner has the same VibeLens logo as Panel 3 (cyan magnifying glass with pulse line + "VibeLens" wordmark). The timeline dots are now all green. A right-side panel is open labeled "Skills" in small white text at the top, listing 3-4 short items with small green checkmark icons next to each.

Junior peeks in from the right edge of the panel — only his head and one hand gripping the panel border are visible. His expression is wide-eyed and impressed, mouth forming a small surprised "o". A tiny sparkle star floats near his eyes.

Alex's speech bubble (top-center, tail pointing down to Alex):
"Custom skills + CLAUDE.md. No more repeats."

Background: Same office, bright warm lighting, the succulent, a second plant (small fern) added next to the new monitor to suggest time has passed and Alex has settled in.

--- GLOBAL NOTES ---
- All text in speech bubbles, thought bubbles, callouts, and panel titles must be rendered clearly and legibly — this is critical.
- Maintain consistent character proportions, clothing colors, and facial features across all panels.
- The visual progression should feel like a story arc: curiosity → frustration → discovery → mastery.
- Color palette for backgrounds subtly shifts: Panel 1 neutral warm → Panel 2 slightly dim/warm → Panel 3 slightly cool (monitor glow) → Panel 4 bright warm with a hint of golden light.
- Never show the icon of VibeLens.
- The sizes of monitors must be the same.
- Never change the style and face of characters.
- Must be very clear.
```

### Feature Mapping

| Panel | VibeLens Features Highlighted |
|-------|-------------------------------|
| P1 | The hook: coding agents are fast, Alex wants in |
| P2 | The problem: agent keeps repeating mistakes, no learning across sessions |
| P3 | Productivity tips (CLAUDE.md suggestions), skill recommendation |
| P4 | Custom skills from history, CLAUDE.md tips, mistake-free workflow |

### Tagline

**"Let your agent know you better!"**

### Image Beautify Prompt

```
Redraw this 4-panel comic at higher quality. Keep the exact same characters, poses, expressions, text, speech bubbles, and panel layout. Visual polish only — no content changes.

--- DETAIL & CLARITY ---
All objects must have clean, smooth, continuous outlines — especially keyboards, mice, desks, monitors, chairs, and laptops. No wobbly edges, no broken lines, no blurry shapes. Every object should look like it was drawn with a steady hand and a vector pen tool. Render desk surfaces, keyboard keys, monitor bezels, and small props (plants, cups, paper) with clear, recognizable shapes and sharp edges.

--- BORDERS ---
Every panel border must be a complete, continuous, unbroken black line with consistent small rounded corners. No gaps, no fading. Clean straight white gutters between panels.

--- COLOR & LIGHTING ---
Gentle, even, diffused lighting throughout. Subtle color temperature shift across panels:
- P1: warm cream, inviting
- P2: slightly cooler, muted tension
- P3: evening-dim with the monitor as soft light source
- P4: warm and bright, gentle celebration

Transitions are subtle — the four panels belong together as one gentle mood gradient.

--- QUALITY ---
High resolution, high contrast, high definition. Crisp uniform black outlines — thicker on character silhouettes, thinner on interior details. Colors are vivid and saturated but not garish. Text in all speech bubbles and callouts must be razor-sharp and fully legible. No compression artifacts, no color banding, no blurry areas.

--- OVERALL ---
Premium children's book illustration quality — soft, vivid, comfortable to look at. Clean and inviting with balanced composition.
```

## Logo Refinement Prompt

Concept: The letter "V" merges with a magnifying glass to form a single unified mark. The two strokes of V become the handle, and a circular lens sits where the V opens — reading simultaneously as "V for VibeLens" and "a lens that reveals what's hidden." This reflects the product tagline: "See what your AI coding agents are actually doing."

### Design Exploration Prompt (generate multiple variations)

```
Design a minimalist app icon for "VibeLens," a developer tool that replays and analyzes AI coding agent sessions. The core shape merges the letter V with a magnifying glass into one unified mark.

--- CONCEPT ---
The two strokes of the letter V form the handle of a magnifying glass. A circular lens sits at the top where the V opens. The V and the circle are one continuous, connected shape — not a V next to a circle, but a single integrated glyph. The overall silhouette should read as both "V" and "magnifying glass" simultaneously without effort.

Generate 4 variations exploring different interpretations:
1. V-handle with a clean circular lens at top, the lens slightly overlapping or intersecting the V strokes
2. V-handle with a subtle eye shape inside the lens circle (a minimal almond-shaped iris, not realistic)
3. V formed by two light beams converging through a circular lens, with a faint spectrum hint exiting
4. Abstract geometric V where the negative space between the strokes forms the lens shape

--- PROPORTIONS ---
Use golden ratio to size the relationship between the V-handle and the lens circle. The circle diameter relates to the V height at roughly 1:1.618. The V angle is open enough that the circle sits naturally in the opening without feeling cramped. The overall mark fits comfortably inside a square canvas with balanced padding.

--- LINES ---
All strokes are smooth, continuous, and uniform — vector-quality, as if drawn with a single confident pen stroke. Corners where the V meets the circle use gentle smooth rounding (squircle transitions, no hard joints). The stroke weight is consistent throughout the mark. The curves feel mathematically precise yet visually soft — think Apple logo quality.

--- COLOR ---
The icon should work in multiple color contexts. Primary version: the mark is rendered in a cool-toned gradient — deep indigo at the V base transitioning to cyan/teal at the lens circle. This matches VibeLens's dark-themed UI which uses zinc backgrounds with cyan, emerald, violet, and amber accents for data categories. The gradient direction (dark at bottom, bright at top) draws the eye upward toward the lens — the point of insight.

Monochrome version must also work: pure white on dark background, or pure dark on light background. The shape alone, without color, should still read as "V + magnifying glass."

Background: transparent (for versatility) or dark charcoal (#0a0a0f) for the primary version.

--- STYLE ---
Clean geometric minimalism. No fills inside the lens circle (or a very subtle tint at most). No realistic glass effects, no heavy shadows, no 3D. The mark is essentially a line drawing with consistent stroke weight — elegance through restraint. Think of how Stripe, Linear, or Vercel design their marks: simple, geometric, premium, instantly recognizable.

The icon must be legible at 16x16px (GitHub favicon, browser tab) where only the V+circle silhouette needs to register. At 512px it should feel refined and polished with smooth anti-aliased edges.

--- DO NOT ---
- Add the word "VibeLens" or any text
- Use rainbow colors or more than 2-3 gradient stops
- Add decorative elements (particles, glow, bokeh, data nodes, circuit patterns)
- Make the eye (in variation 2) look realistic — keep it abstract and geometric
- Use thick heavy strokes that feel clunky — the mark should feel light and precise
- Create a busy or complex composition — one unified shape is the goal
```
