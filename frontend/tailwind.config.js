/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Aditi Consulting Official Brand Palette
        brand: {
          'dark-blue': '#052239',    // Primary
          'navy-blue': '#182D82',    // Primary
          'light-gray': '#EDEDED',   // Primary
          'sky-blue': '#00B9F1',     // Secondary
          'teal': '#00C48C',         // Secondary
          'gold': '#FFA300',         // Secondary
        },
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: 'hsl(var(--card))',
        'card-foreground': 'hsl(var(--card-foreground))',
        primary: 'hsl(var(--primary))',
        'primary-foreground': 'hsl(var(--primary-foreground))',
        secondary: 'hsl(var(--secondary))',
        'secondary-foreground': 'hsl(var(--secondary-foreground))',
        muted: 'hsl(var(--muted))',
        'muted-foreground': 'hsl(var(--muted-foreground))',
        accent: 'hsl(var(--accent))',
        'accent-foreground': 'hsl(var(--accent-foreground))',
        destructive: 'hsl(var(--destructive))',
        border: 'hsl(var(--border))',
        ring: 'hsl(var(--ring))',
        teal: 'hsl(var(--teal))',
        gold: 'hsl(var(--gold))',
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'var(--radius)',
        sm: 'var(--radius)',
        none: '0',
      },
      fontFamily: {
        sans: ['Lato', 'Roboto', 'system-ui', 'sans-serif'],
        heading: ['Lato', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(12px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-right': {
          from: { opacity: '0', transform: 'translateX(-12px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'scale(0.95)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.3s ease-out forwards',
        'slide-up': 'slide-up 0.35s ease-out forwards',
        'slide-right': 'slide-right 0.3s ease-out forwards',
        'scale-in': 'scale-in 0.2s ease-out forwards',
      },
    },
  },
  plugins: [],
};
