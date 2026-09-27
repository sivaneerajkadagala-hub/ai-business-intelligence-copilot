FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Empty NEXT_PUBLIC_API_URL → api.ts calls /api/v1 on this app's own
# origin; next.config rewrites proxy it to API_INTERNAL_URL (the
# backend's private host on Railway). Cookies stay same-origin, so
# SameSite=lax keeps working — no cross-site cookie config needed.
ARG NEXT_PUBLIC_API_URL=""
ARG API_INTERNAL_URL="http://localhost:8000"
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    API_INTERNAL_URL=$API_INTERNAL_URL
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
