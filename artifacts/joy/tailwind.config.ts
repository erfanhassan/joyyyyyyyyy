import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./index.html",
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        background: "#FFFFFF",
        surface: "#FAFAF9",
        "surface-card": "#FFFFFF",
        "surface-hover": "#F4F4F5",
        border: "#E4E4E7",
        foreground: "#18181B",
        muted: "#71717A",
        // Project JOY Brand: Emerald Forest (Zero blue/purple policy)
        brand: {
          50: "#ECFDF5",
          100: "#D1FAE5",
          500: "#10B981",
          600: "#059669",
          700: "#047857",
          900: "#064E3B",
        },
        // Operational Accents
        warning: {
          light: "#FEF3C7",
          DEFAULT: "#D97706",
          dark: "#92400E",
        },
        alert: {
          light: "#FFE4E6",
          DEFAULT: "#E11D48",
          dark: "#9F1239",
        },
      },
    },
  },
  plugins: [],
};
export default config;
