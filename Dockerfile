# Build the Vue SPA
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Copy the built SPA (not committed to git, so build it above)
COPY --from=frontend /app/static/spa ./app/static/spa

# Create data directory for config and logs
RUN mkdir -p /app/data

ENV POSTERPILOT_DOCKER=true
ENV POSTERPILOT_DATA_DIR=/app/data

EXPOSE 8888

CMD ["python", "run.py"]
