/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        serif: ['"Noto Serif SC"', 'Georgia', 'serif'],
        sans: ['"Inter"', '"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'Consolas', 'monospace'],
      },
      colors: {
        stage: {
          950: '#0b0b10',
          900: '#12121a',
          800: '#1a1a26',
          700: '#252535',
          600: '#34344a',
        },
        gold: '#c9a86a',
      },
    },
  },
  plugins: [],
}
