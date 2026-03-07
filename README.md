# AITA CEGE 3102: Uncertainty and Decision Analysis

AI Teaching Assistant chatbot for **CEGE 3102: Uncertainty and Decision Analysis** at the University of Minnesota.

Built on [aita-core](https://github.com/UMN-Choi-Lab/aita-core) — see that repo for full setup instructions, architecture details, and deployment guide.

## Quick Start

1. Install dependencies: `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in your API keys
3. Add course materials to `course_materials/`
4. Build the vector store: `python add_document.py`
5. Run locally: `streamlit run main.py`

## Deployment

```bash
docker compose build
docker compose up -d
```

See the [aita-core README](https://github.com/UMN-Choi-Lab/aita-core#readme) for detailed step-by-step instructions.
