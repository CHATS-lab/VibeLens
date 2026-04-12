/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Surfaces
        canvas: 'var(--color-bg-canvas)',
        panel: 'var(--color-bg-panel)',
        control: 'var(--color-bg-control)',
        'control-hover': 'var(--color-bg-control-hover)',
        subtle: 'var(--color-bg-subtle)',
        overlay: 'var(--color-bg-overlay)',

        // Text
        primary: 'var(--color-text-primary)',
        secondary: 'var(--color-text-secondary)',
        muted: 'var(--color-text-muted)',
        dimmed: 'var(--color-text-dimmed)',
        faint: 'var(--color-text-faint)',
        'on-accent': 'var(--color-text-on-accent)',

        // Borders (also usable as bg/text/ring via Tailwind's color system)
        default: 'var(--color-border-default)',
        card: 'var(--color-border-card)',
        hover: 'var(--color-border-hover)',

        // Accent colors
        'accent-cyan': 'var(--color-accent-cyan)',
        'accent-cyan-bg': 'var(--color-accent-cyan-bg)',
        'accent-cyan-subtle': 'var(--color-accent-cyan-subtle)',
        'accent-cyan-muted': 'var(--color-accent-cyan-muted)',
        'accent-cyan-border': 'var(--color-accent-cyan-border)',
        'accent-cyan-focus': 'var(--color-accent-cyan-focus)',
        'accent-cyan-shadow': 'var(--color-accent-cyan-shadow)',

        'accent-violet': 'var(--color-accent-violet)',
        'accent-violet-bg': 'var(--color-accent-violet-bg)',
        'accent-violet-subtle': 'var(--color-accent-violet-subtle)',
        'accent-violet-border': 'var(--color-accent-violet-border)',

        'accent-teal': 'var(--color-accent-teal)',
        'accent-teal-subtle': 'var(--color-accent-teal-subtle)',
        'accent-teal-border': 'var(--color-accent-teal-border)',
        'accent-teal-focus': 'var(--color-accent-teal-focus)',
        'accent-teal-shadow': 'var(--color-accent-teal-shadow)',

        'accent-amber': 'var(--color-accent-amber)',
        'accent-amber-subtle': 'var(--color-accent-amber-subtle)',
        'accent-amber-border': 'var(--color-accent-amber-border)',
        'accent-amber-focus': 'var(--color-accent-amber-focus)',
        'accent-amber-shadow': 'var(--color-accent-amber-shadow)',

        'accent-rose': 'var(--color-accent-rose)',
        'accent-rose-bg': 'var(--color-accent-rose-bg)',
        'accent-rose-subtle': 'var(--color-accent-rose-subtle)',
        'accent-rose-border': 'var(--color-accent-rose-border)',

        'accent-emerald': 'var(--color-accent-emerald)',
        'accent-emerald-subtle': 'var(--color-accent-emerald-subtle)',
        'accent-emerald-border': 'var(--color-accent-emerald-border)',

        'accent-indigo': 'var(--color-accent-indigo)',
        'accent-indigo-subtle': 'var(--color-accent-indigo-subtle)',
        'accent-indigo-border': 'var(--color-accent-indigo-border)',
        'accent-indigo-shadow': 'var(--color-accent-indigo-shadow)',

        'accent-blue': 'var(--color-accent-blue)',

        // Chart
        'chart-line': 'var(--color-chart-line)',
        'chart-text': 'var(--color-chart-text)',

        // Shadow
        shadow: 'var(--color-shadow)',
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.2s ease-out",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
