/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#102030",
        surf: "#f4f8f7",
        mint: "#2f8f83",
        sun: "#f4a259",
        coral: "#e76f51"
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body: ["'Manrope'", "sans-serif"]
      }
    }
  },
  plugins: []
};
