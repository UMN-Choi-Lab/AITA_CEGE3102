FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY config.py main.py ./

# Copy Google OAuth credentials if present (optional)
COPY client_secret*.json* ./

# Copy pre-built FAISS index
COPY faiss_db/ ./faiss_db/

# Copy course materials for PDF downloads
COPY course_materials/ ./course_materials/

# Data directory (mounted as volume in production)
RUN mkdir -p /app/data

# Streamlit config: disable telemetry, set port
RUN mkdir -p /root/.streamlit
RUN echo '[server]\nheadless = true\nport = 8501\nenableCORS = false\nenableXsrfProtection = false\n\n[browser]\ngatherUsageStats = false' > /root/.streamlit/config.toml

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]
