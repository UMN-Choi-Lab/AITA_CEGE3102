#!/usr/bin/env python3
"""Smoke-test the Gemini Developer API before deploying AITA to Fly.io.

Verifies, using ONLY the Developer API (not Vertex):
  1. GEMINI_API_KEY is set and valid.
  2. The chat model id (default: gemini-3.1-flash-lite) is actually servable.
  3. gemini-embedding-001 returns 3072-dim vectors (must match the FAISS index).

It also lists available *flash* chat models, so if the default id is not served
on the Developer API you can immediately see the correct one to put in config.py.

Usage:
    export GEMINI_API_KEY=...          # created in Google Cloud Console (see DEPLOY.md)
    python scripts/check_gemini.py                       # default model ids
    python scripts/check_gemini.py gemini-flash-lite-latest   # try another id

Exit code 0 = safe to deploy with these ids; non-zero = fix before deploying.
"""
import os
import sys

CHAT_MODEL = (
    sys.argv[1] if len(sys.argv) > 1
    else os.environ.get("AITA_LLM_MODEL", "gemini-3.1-flash-lite")
)
EMBED_MODEL = os.environ.get("AITA_EMBED_MODEL", "gemini-embedding-001")
EMBED_DIMS = int(os.environ.get("AITA_EMBED_DIMS", "3072"))


def main() -> int:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        print("FAIL: set GEMINI_API_KEY (create it in Google Cloud Console — see DEPLOY.md)")
        return 2

    # Guard: a stray Vertex env would make genai.Client() ignore the API key.
    for v in ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_GENAI_USE_ENTERPRISE"):
        if os.environ.get(v):
            print(f"WARN: {v} is set — unset it so this actually tests the Developer API.")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)  # explicit Developer API client

    # 1) List flash chat models so the right id is obvious if the default fails.
    print("Available chat models matching 'flash':")
    listed = []
    try:
        for m in client.models.list():
            name = m.name.split("/")[-1]
            if "flash" in name.lower():
                listed.append(name)
                print(f"  - {name}")
        if not listed:
            print("  (none matched 'flash' — showing this is informational only)")
    except Exception as e:  # noqa: BLE001
        print(f"  (could not list models: {e})")

    if listed and CHAT_MODEL not in listed:
        print(f"NOTE: '{CHAT_MODEL}' is not in the listed flash models. If the chat "
              f"test below fails, set llm_model in config.py to one of the ids above.")

    # 2) Chat smoke test.
    print(f"\nChat test with '{CHAT_MODEL}':")
    try:
        r = client.models.generate_content(
            model=CHAT_MODEL,
            contents="Reply with the single word: OK",
            config=types.GenerateContentConfig(max_output_tokens=10, temperature=0),
        )
        print("  PASS ->", (r.text or "").strip()[:60])
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL: {e}")
        if any(s in str(e) for s in ("429", "RESOURCE_EXHAUSTED")) or "quota" in str(e).lower():
            print("  -> rate-limited. Make sure the key is on the PAID tier (a")
            print("     billing-enabled project, created via Google Cloud Console),")
            print("     then check Quotas for this model before a class launch.")
        else:
            print("  -> pick a served id from the list above and re-run:")
            print("     python scripts/check_gemini.py <model-id>")
        return 1

    # 3) Embedding smoke test — dims must equal the FAISS index width.
    print(f"\nEmbedding test with '{EMBED_MODEL}' @ {EMBED_DIMS} dims:")
    try:
        er = client.models.embed_content(
            model=EMBED_MODEL,
            contents=["confidence interval"],
            config=types.EmbedContentConfig(output_dimensionality=EMBED_DIMS),
        )
        dim = len(er.embeddings[0].values)
        if dim == EMBED_DIMS:
            print(f"  PASS -> got {dim} dims")
        else:
            print(f"  FAIL -> got {dim} dims but the FAISS index needs {EMBED_DIMS}")
            print("  -> retrieval will be broken; re-ingest or fix embedding_dimensions.")
            return 1
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL: {e}")
        return 1

    print(f"\nAll checks passed. Deploy with llm_model='{CHAT_MODEL}', "
          f"embedding_model='{EMBED_MODEL}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
