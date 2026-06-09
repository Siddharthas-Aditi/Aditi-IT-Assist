# Aditi Theme

## Brand Colors
- Primary: `#2563eb` (Corporate Blue)
- Background: White / Light Gray
- Foreground: Dark Navy
- Accent: Subtle blue tint
- Destructive: Red for errors

## CSS Variables (in globals.css)
```css
:root {
  --primary: 221 83% 53%;
  --primary-foreground: 210 40% 98%;
  --background: 0 0% 100%;
  --foreground: 222 47% 11%;
  --muted: 210 40% 96%;
  --border: 214 32% 91%;
  --radius: 0.5rem;
}
```

## Typography
- Font: Inter (system-ui fallback)
- Headings: font-bold, text-foreground
- Body: text-sm, text-foreground
- Muted: text-muted-foreground

## Component Styling
- Cards: `rounded-lg border border-border bg-card p-4`
- Buttons: `rounded-lg bg-primary px-4 py-2 text-primary-foreground`
- Inputs: `rounded-lg border border-border bg-background px-4 py-2`
- Badges: `rounded-full px-2 py-0.5 text-xs font-medium`

## Design Principles
- Professional and trustworthy
- Clean whitespace
- Subtle shadows (shadow-sm only)
- No heavy gradients
- Consistent spacing (4px grid)
