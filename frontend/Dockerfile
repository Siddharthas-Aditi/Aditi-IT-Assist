# ==================================================
# Aditi IT Assist — Frontend Dockerfile
# ==================================================
# Targets:
#   development → Vite dev server with HMR
#   production  → Optimized nginx serving static assets

# ── Base stage ──────────────────────────────────
FROM node:20-alpine AS base

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

# ── Development stage ───────────────────────────
FROM base AS development

# Source is mounted as volume for HMR — copy for initial build
COPY . .

EXPOSE 5173

# Vite dev server — host 0.0.0.0 for Docker access
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]

# ── Build stage ─────────────────────────────────
FROM base AS builder

COPY . .
RUN npm run build

# ── Production stage ────────────────────────────
FROM nginx:1.27-alpine AS production

# Copy optimized build output
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config with API proxy and SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Non-root nginx
RUN chown -R nginx:nginx /usr/share/nginx/html \
    && chown -R nginx:nginx /var/cache/nginx \
    && chown -R nginx:nginx /var/log/nginx \
    && touch /var/run/nginx.pid \
    && chown -R nginx:nginx /var/run/nginx.pid
USER nginx

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
