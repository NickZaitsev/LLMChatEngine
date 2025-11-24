# ---- Builder Stage ----
# This stage installs dependencies and creates a virtual environment.
# It includes build tools that are not needed in the final image.
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system dependencies needed for building some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment
RUN python -m venv /opt/venv

# Activate the virtual environment for subsequent commands
ENV PATH="/opt/venv/bin:$PATH"

# Copy only the requirements file to leverage Docker's layer caching
COPY requirements.txt .

# Install Python dependencies into the virtual environment
# Use a cache mount to speed up dependency installation in subsequent builds.
# This requires BuildKit to be enabled (which is the default in modern Docker).
# The cache is persisted by Docker and reused, avoiding re-downloads.
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

# Pre-cache tiktoken models to avoid runtime downloads
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"


# ---- Final Stage ----
# This stage creates the lean, production-ready image.
FROM python:3.11-slim

WORKDIR /app

# Create a non-root user for better security
RUN useradd --create-home --shell /bin/bash bot

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy the application code
COPY . .

# Set the PATH to use the virtual environment's Python and packages
ENV PATH="/opt/venv/bin:$PATH"

# Change ownership of the app directory to the non-root user
RUN chown -R bot:bot /app

# Switch to the non-root user
USER bot

# Set the command to run the bot
CMD ["python", "bot.py"]