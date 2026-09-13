FROM python:3.11-slim

WORKDIR /app

# Install dependencies
# aita-core is not on PyPI — install the vendored wheel first (pulls google-genai etc.),
# then the rest of requirements (aita-core>=0.6.0 is then already satisfied).
COPY requirements.txt .
COPY aita_core-*.whl ./
RUN pip install --no-cache-dir aita_core-*.whl && rm -f aita_core-*.whl
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir pymupdf

# Copy application code
COPY config.py main.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

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

ENTRYPOINT ["/app/entrypoint.sh"]
