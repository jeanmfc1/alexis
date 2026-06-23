ALEXIS desktop app (MVP)
========================

This is the source-mode app. The packaged installer is Phase 3.

To run from source:
    cd <repo>
    pip install fastapi "uvicorn[standard]" pywebview sse-starlette
    py -3.11 -m app

Or headless (uses your default browser):
    py -3.11 -m app --headless

Configure your data folder via the Settings tab in the app.
