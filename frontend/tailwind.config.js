/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        app: {
          background: "rgb(var(--app-background) / <alpha-value>)",
          sidebar: "rgb(var(--app-sidebar) / <alpha-value>)",
          panel: "rgb(var(--app-panel) / <alpha-value>)",
          inset: "rgb(var(--app-inset) / <alpha-value>)",
          elevated: "rgb(var(--app-elevated) / <alpha-value>)",
          border: "rgb(var(--app-border) / <alpha-value>)",
          primary: "rgb(var(--app-primary) / <alpha-value>)",
          text: "rgb(var(--app-text) / <alpha-value>)",
          muted: "rgb(var(--app-muted) / <alpha-value>)",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
