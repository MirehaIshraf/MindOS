/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        app: {
          background: "#0f0f0f",
          sidebar: "#161616",
          panel: "#1c1c1c",
          border: "#2a2a2a",
          primary: "#7c3aed",
          text: "#f0f0f0",
          muted: "#a1a1aa",
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
