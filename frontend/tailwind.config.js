/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: 'var(--color-brand-primary, #3b82f6)',
          secondary: 'var(--color-brand-secondary, #1e40af)',
        },
      },
    },
  },
  plugins: [],
}

