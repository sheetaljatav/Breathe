import type { Config } from "tailwindcss";

/**
 * Custom analyst-tool theme.
 *
 * Why these choices:
 *   - Neutral palette only (slate). No off-the-shelf gradient kit.
 *   - JetBrains Mono for any ID/code/unit. Inter for everything else.
 *   - One semantic-color scale per status (warn/danger/ok/info). No "primary"
 *     blue that gets overused — buttons inherit their color from intent.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', '"Menlo"', '"Consolas"', "monospace"],
      },
      colors: {
        surface: {
          DEFAULT: "#ffffff",
          subtle: "#fafafa",
          muted:  "#f5f5f5",
          border: "#e5e5e5",
          ring:   "#d4d4d4",
        },
        ink: {
          DEFAULT: "#0a0a0a",
          muted:   "#525252",
          subtle:  "#737373",
          inverse: "#fafafa",
        },
        status: {
          pending:  "#737373",   // neutral
          flagged:  "#b45309",   // amber-700
          approved: "#15803d",   // green-700
          rejected: "#b91c1c",   // red-700
          locked:   "#1d4ed8",   // blue-700
        },
      },
      fontSize: {
        // Slightly tighter base than Tailwind default — analyst tools are info-dense.
        sm: ["13px", { lineHeight: "18px" }],
        base: ["14px", { lineHeight: "20px" }],
        lg: ["16px", { lineHeight: "22px" }],
      },
      borderRadius: {
        DEFAULT: "4px",
        md: "6px",
        lg: "8px",
      },
      boxShadow: {
        // No drop shadows; only focus rings.
        focus: "0 0 0 2px #ffffff, 0 0 0 4px #525252",
      },
    },
  },
  plugins: [],
} satisfies Config;
