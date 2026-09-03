"""Databricks Apps entry point. Platform assigns the port via
DATABRICKS_APP_PORT; 8000 is the local-dev fallback."""

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("DATABRICKS_APP_PORT", 8000))
    uvicorn.run("server.main:app", host="0.0.0.0", port=port)
