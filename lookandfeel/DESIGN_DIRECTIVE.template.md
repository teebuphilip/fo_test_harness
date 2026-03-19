# DESIGN_DIRECTIVE.md
version: 1.0

## SCOPE
- CHANGE: colors, typography, spacing, shadows, borders, hover/focus states, transitions
- DO NOT CHANGE: props, business logic, routing, data flow, imports, component structure

## TARGET FILES
- src/components/DashboardLayout.jsx
- src/components/Navbar.jsx
- src/components/FeatureCard.jsx
- src/components/PricingCard.jsx
- src/index.css
- tailwind.config.js

## DESIGN TOKENS
theme: dark
primary_color: indigo-500
background: slate-950
surface: slate-900
text_primary: slate-100
text_muted: slate-400
border: slate-800
accent: indigo-500

## COMPONENT RULES
card: bg-slate-900 rounded-xl border border-slate-800 p-6 hover:border-slate-600 transition-all duration-200
button_primary: bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg px-4 py-2 font-medium transition-colors
button_outline: border border-slate-700 hover:border-slate-500 text-slate-300 rounded-lg px-4 py-2 transition-colors
navbar: bg-slate-950 border-b border-slate-800
nav_link: text-slate-400 hover:text-white transition-colors
nav_link_active: text-white font-medium
