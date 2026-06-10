# Skill: Design System — Aditi Theme

> Visual design standards and component library for Aditi IT Assist.

---

## Brand Colors

```css
/* Aditi brand palette */
--aditi-primary: #1B3A5C;       /* Deep navy — trust, professionalism */
--aditi-primary-light: #2D5F8A; /* Lighter navy for hover states */
--aditi-accent: #E8792F;        /* Warm orange — energy, friendliness */
--aditi-accent-light: #F5A623;  /* Light orange for highlights */
```

### Tailwind Config

```javascript
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        aditi: {
          navy: '#1B3A5C',
          'navy-light': '#2D5F8A',
          orange: '#E8792F',
          'orange-light': '#F5A623',
        },
      },
    },
  },
};
```

---

## Component Library (shadcn/ui)

We use shadcn/ui components. Key components:

| Component | Usage |
|-----------|-------|
| `Button` | All actions |
| `Card` | Content containers |
| `Input` | Form fields |
| `Avatar` | User/AI avatars |
| `Badge` | Status indicators |
| `ScrollArea` | Scrollable regions |
| `Separator` | Visual dividers |

---

## Chat UI Patterns

### Message Bubbles
```typescript
// User messages: right-aligned, branded background
<div className="ml-auto max-w-[80%] rounded-lg bg-aditi-navy p-3 text-white">

// AI messages: left-aligned, card background
<div className="mr-auto max-w-[80%] rounded-lg bg-card p-3 border">
```

### Status Indicators
```typescript
// Confidence badges
<Badge variant={confidence >= 0.8 ? "success" : confidence >= 0.5 ? "warning" : "destructive"}>
  {Math.round(confidence * 100)}% confident
</Badge>

// Session status
<Badge variant="outline">{status}</Badge>
```

---

## Typography

```css
/* Font stack */
font-family: 'Inter', system-ui, -apple-system, sans-serif;

/* Scale */
.text-xs    { font-size: 0.75rem; }   /* Timestamps, metadata */
.text-sm    { font-size: 0.875rem; }  /* Secondary text */
.text-base  { font-size: 1rem; }      /* Body text */
.text-lg    { font-size: 1.125rem; }  /* Section headers */
.text-xl    { font-size: 1.25rem; }   /* Page titles */
```

---

## Responsive Breakpoints

```css
sm: 640px    /* Mobile landscape */
md: 768px    /* Tablet */
lg: 1024px   /* Desktop */
xl: 1280px   /* Wide desktop */
```

---

## Accessibility

- All interactive elements have visible focus rings
- Color contrast ratio ≥ 4.5:1 for text
- All images have alt text
- Keyboard navigation supported
- Screen reader labels on icons
