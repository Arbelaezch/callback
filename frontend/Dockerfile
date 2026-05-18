# frontend/Dockerfile
FROM node:lts-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# In prod this image is built with `next build` before starting
# In dev the command is overridden to `npm run dev` via compose
RUN npm run build 2>/dev/null || true

EXPOSE 3000
