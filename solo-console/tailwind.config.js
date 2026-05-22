import tailwindcssAnimate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: 'hsl(222 47% 8%)',
        foreground: 'hsl(210 40% 98%)',
        border: 'hsl(215 32% 17%)',
        muted: {
          DEFAULT: 'hsl(217 33% 12%)',
          foreground: 'hsl(215 20% 65%)',
        },
        primary: {
          DEFAULT: 'hsl(142 72% 45%)',
          foreground: 'hsl(222 47% 8%)',
        },
        card: {
          DEFAULT: 'hsl(222 47% 10%)',
          foreground: 'hsl(210 40% 98%)',
        },
      },
      boxShadow: {
        soft: '0 12px 40px rgba(0,0,0,0.25)',
      },
      keyframes: {
        pulseDot: {
          '0%, 100%': { opacity: 0.35, transform: 'scale(0.9)' },
          '50%': { opacity: 1, transform: 'scale(1.15)' },
        },
      },
      animation: {
        'pulse-dot': 'pulseDot 1.2s ease-in-out infinite',
      },
    },
  },
  plugins: [tailwindcssAnimate],
}
