FROM node:22-alpine

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
COPY frontend ./

ENV VITE_DEV_PROXY_TARGET=http://api:8000

EXPOSE 5173

CMD ["sh", "-c", "if [ ! -d node_modules/vite ] || [ ! -d node_modules/react ]; then npm ci; fi; npm run dev -- --host 0.0.0.0 --port 5173"]
