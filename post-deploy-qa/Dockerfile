FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Install Node.js + Newman
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g newman newman-reporter-json && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install -r requirements.txt

# Clone test repo at build time OR override at runtime via env
# Tests expected at:
#   /app/tests/postman/   -> Newman collections + environments
#   /app/tests/playwright/ -> Playwright specs

COPY entrypoint.py .
COPY clone_tests.sh .
RUN chmod +x clone_tests.sh

# Results written here — mount or read via Railway logs
RUN mkdir -p /app/results

ENTRYPOINT ["python", "entrypoint.py"]
