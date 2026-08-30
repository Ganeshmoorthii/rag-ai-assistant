/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'dark-bg': '#08111F',
        'dark-card': '#0F1B2E',
        'dark-surface': '#1a2540',
        'dark-border': '#2a3f5f',
        'status-success': '#10b981',
        'status-warning': '#f59e0b',
        'status-error': '#ef4444',
      },
      boxShadow: {
        'card': '0 1px 3px rgba(0, 0, 0, 0.12), 0 1px 2px rgba(0, 0, 0, 0.24)',
        'card-hover': '0 3px 6px rgba(0, 0, 0, 0.16), 0 3px 6px rgba(0, 0, 0, 0.23)',
        'glow': '0 0 0 1px rgba(148,163,184,0.08), 0 20px 45px rgba(15, 23, 42, 0.45)',
        'accent': '0 0 20px rgba(59, 130, 246, 0.2)',
      },
      spacing: {
        '4.5': '1.125rem',
      },
      fontSize: {
        'xs': ['0.75rem', { lineHeight: '1rem' }],
        'sm': ['0.875rem', { lineHeight: '1.25rem' }],
        'base': ['1rem', { lineHeight: '1.5rem' }],
      },
    },
  },
  plugins: [],
}
