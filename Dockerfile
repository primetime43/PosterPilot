FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create data directory for config and logs
RUN mkdir -p /app/data

ENV POSTERPILOT_DOCKER=true
ENV POSTERPILOT_DATA_DIR=/app/data

EXPOSE 8888

CMD ["python", "run.py"]
