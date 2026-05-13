# syntax=docker/dockerfile:1.7
#
# OpenClef docs site — Astro Starlight static build served by nginx.
# Versions pinned per CLAUDE.md design principle 6.
#
# Build:    docker build -t openclef-docs .
# Run:      docker run --rm -p 8080:80 openclef-docs
# Compose:  docker compose --profile preview up docs   (from repo root)

# --- Stage 1: build the static site ---
FROM node:22.22.2-alpine AS build
WORKDIR /src

# Copy lock + manifest first so npm ci is cached when only content changes.
COPY package.json package-lock.json ./
RUN npm ci

# Then copy the rest and build.
COPY . .
RUN npm run build

# --- Stage 2: minimal nginx runtime ---
FROM nginx:1.27.3-alpine AS runtime

# Drop the default config; we ship a small custom one tuned for static SPA
# semantics (clean-URL trailing-slash handling, 404 page, no server tokens).
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=build /src/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
