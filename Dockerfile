# Start from an official lightweight Python image
# 3.11-slim is a minimal version - no extras we don't need
FROM python:3.11-slim

# Set the working directory inside the container
# All subsequent commands run from here
WORKDIR /app

# Copy requirements first - before the rest of the code
# Docker builds in layers and caches each one.
# If requirements.txt hasn't changed, Docker skips this
# layer on rebuild and goes straight to copying your code.
# This makes rebuilds much faster during development.
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project into the container
COPY . .

# Default command - runs the sync script
# We'll change this to main.py in Phase 2
CMD ["python", "main.py"]