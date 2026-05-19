import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#f0f4ff",
          500: "#4f6ef7",
          600: "#3b55e6",
          900: "#1a2562",
        },
      },
      animation: {
        "fade-in": "fadeIn 0.25s ease-out",
      },
      keyframes: {
        fadeIn: { from: { opacity: "0", transform: "scale(0.96)" }, to: { opacity: "1", transform: "scale(1)" } },
      },
    },
  },
  plugins: [],
} satisfies Config;
