FROM node:24-slim

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

CMD ["sh", "-c", "npx vite --host 0.0.0.0 --port ${FRONTEND_PORT:-5020}"]
