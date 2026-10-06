# ==============================================================================
# Dockerfile Multi-Stage pour Knowledge Dashboard (Sprint 8, Tâche 8.9)
# ==============================================================================

# 1. Étape de Build (Node.js 22 Alpine)
FROM node:22-alpine AS build
WORKDIR /app

# Copie des manifestes de dépendances
COPY package.json package-lock.json* ./

# Installation propre des dépendances avec binaires natifs Linux
RUN npm install

# Copie du code source complet
COPY . .

# Compilation Vite de production
RUN npm run build

# 2. Étape de Runtime Production (Nginx 1.27 Alpine)
FROM nginx:1.27-alpine AS production

# Copie des fichiers statiques compilés depuis l'étape de build
COPY --from=build /app/dist /usr/share/nginx/html

# Configuration personnalisée Nginx pour SPA et proxy /v1/
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Port d'écoute standard
EXPOSE 80

# Healthcheck HTTP
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -q --spider http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]

