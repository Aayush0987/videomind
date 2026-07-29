import type { Config } from "tailwindcss";

// §16.2 palette — two accents, each with exactly one meaning:
//   cyan  → playhead + active chapter
//   amber → citations + retry indicators (never reused for anything else)
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ground: "#12151C",
        // A hair lighter than ground, for raised surfaces (cards, drawers).
        surface: "#1A1F29",
        // Hairline borders and the un-played portion of the timeline spine.
        hairline: "#2A303C",
        paper: "#ECEFF4",
        // Dimmed paper for secondary copy and timecodes at rest.
        muted: "#8B93A3",
        signal: {
          // Cyan — the playhead and the active chapter. Nothing else.
          DEFAULT: "#38E1D4",
          dim: "#38E1D433",
        },
        citation: {
          // Amber — citations and retry indicators only.
          DEFAULT: "#E0A458",
          dim: "#E0A45822",
        },
      },
      fontFamily: {
        // Condensed grotesque for chapter titles + timecodes (tabular, tight).
        condensed: ["var(--font-condensed)", "sans-serif"],
        // Humanist sans for summaries and answers (comfortable reading).
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
      },
      keyframes: {
        "stage-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "rail-assemble": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "citation-pulse": {
          "0%": { transform: "scale(1)", boxShadow: "0 0 0 0 #E0A45899" },
          "70%": { transform: "scale(1.35)", boxShadow: "0 0 0 10px #E0A45800" },
          "100%": { transform: "scale(1)", boxShadow: "0 0 0 0 #E0A45800" },
        },
      },
      animation: {
        "stage-in": "stage-in 240ms ease-out",
        "rail-assemble": "rail-assemble 320ms ease-out both",
        "citation-pulse": "citation-pulse 700ms ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
