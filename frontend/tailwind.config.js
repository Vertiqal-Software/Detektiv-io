/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],

  // Added: opt-in dark mode via a `.dark` class (no behavior change unless you use it)
  darkMode: "class",

  theme: {
    extend: {
      colors: {
        // VDI Brand Colors from brand guidelines
        'detecktiv-purple': '#6B46C1',
        'tech-black': '#0F172A',
        'trust-silver': '#9CA3AF',
        'success-green': '#10B981',
        'alert-orange': '#F59E0B',
        'critical-red': '#EF4444',
        
        // Brand-specific aliases
        primary: '#6B46C1',
        secondary: '#9CA3AF',
        accent: '#6B46C1',
        
        // Semantic colors matching brand
        success: '#10B981',
        warning: '#F59E0B',
        error: '#EF4444',
        
        // Background variations
        'bg-primary': '#0F172A',
        'bg-secondary': '#1E293B',
        'bg-card': 'rgba(255, 255, 255, 0.08)',
      },
      fontFamily: {
        // Inter font family as specified in brand guidelines
        'sans': ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      fontSize: {
        // Typography scale from brand guidelines
        'hero': ['56px', { lineHeight: '1.1', letterSpacing: '-0.02em' }],
        'hero-mobile': ['40px', { lineHeight: '1.1', letterSpacing: '-0.02em' }],
        'header': ['32px', { lineHeight: '1.2', letterSpacing: '-0.01em' }],
        'data': ['18px', { lineHeight: '1.4' }],
        'body': ['16px', { lineHeight: '1.5' }],
        'label': ['12px', { lineHeight: '1.4', letterSpacing: '0.05em' }],
      },
      spacing: {
        // 8px base spacing system from brand guidelines
        '18': '4.5rem',  // 72px
        '88': '22rem',   // 352px
      },
      borderRadius: {
        // Modern border radius from brand guidelines
        'small': '6px',
        'medium': '12px', 
        'large': '16px',
      },
      boxShadow: {
        // Modern shadows from brand guidelines
        'card': '0 4px 20px rgba(0, 0, 0, 0.08)',
        'elevated': '0 8px 40px rgba(107, 70, 193, 0.12)',
        'interactive': '0 12px 60px rgba(107, 70, 193, 0.16)',
      },
      backdropBlur: {
        'glass': '10px',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        }
      }
    },
  },

  // Kept empty on purpose; add official plugins here later if you install them
  plugins: [],
}
