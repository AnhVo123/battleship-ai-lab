FROM node:22-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt
COPY battleship_lab/ ./battleship_lab/
COPY --from=frontend /app/frontend/dist ./frontend/dist

ENV BATTLESHIP_PUBLIC=1
ENV PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["sh", "-c", "uvicorn battleship_lab.web:create_app --factory --host 0.0.0.0 --port ${PORT:-10000}"]
