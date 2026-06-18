# Build stage
FROM node:18-alpine AS builder

WORKDIR /app

ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend .
RUN npm run build

# Runtime stage
FROM nginx:alpine

# Copy nginx config
RUN rm -rf /etc/nginx/conf.d/*
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
