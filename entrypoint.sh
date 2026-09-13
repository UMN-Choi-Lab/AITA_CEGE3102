#!/bin/sh
set -e

# Materialize the Vertex AI service-account key from the base64 secret GCP_SA_KEY
# into $GOOGLE_APPLICATION_CREDENTIALS *before* Streamlit starts, so the Vertex
# client can authenticate on the first request. No-op when GCP_SA_KEY is unset
# (e.g. local runs using ADC or the Gemini Developer API). Fails loudly (set -e)
# if the key is malformed, rather than booting without credentials.
if [ -n "$GCP_SA_KEY" ] && [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
  python -c "import os,base64; open(os.environ['GOOGLE_APPLICATION_CREDENTIALS'],'wb').write(base64.b64decode(os.environ['GCP_SA_KEY']))"
  echo "[entrypoint] wrote $GOOGLE_APPLICATION_CREDENTIALS ($(wc -c < "$GOOGLE_APPLICATION_CREDENTIALS") bytes)" >&2
fi

exec streamlit run main.py --server.port=8501 --server.address=0.0.0.0
