# Nina Backend

## Prerequisites

1. **Python 3.10+** installed
2. **Ollama** running locally with `qwen2.5:7b` model
   - Download from: https://ollama.ai
   - Install the model: `ollama pull qwen2.5:7b`
   - Make sure Ollama is running: `ollama serve` (usually runs on http://localhost:11434)

## Setup

1. **Create and activate a virtual environment** (recommended):
   ```bash
   python -m venv venv
   
   # On Windows:
   venv\Scripts\activate
   
   # On macOS/Linux:
   source venv/bin/activate
   ```

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers**:
   ```bash
   playwright install chromium
   ```

## Running the Backend

### On Windows (Recommended):
Use the startup script to fix asyncio issues:

```bash
python start_server.py
```

### On macOS/Linux:
```bash
uvicorn main:app --reload --port 8000
```

The API will be available at:
- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs (FastAPI auto-generated docs)
- **Health Check**: http://localhost:8000/health (checks Ollama connection)

## API Endpoint

**POST** `/run`

Request body:
```json
{
  "user_input": "Create an account with raju@gmail.com and password Asdf@1234",
  "base_url": "https://tighthug.in",
  "extra_params": null
}
```

## Troubleshooting

- **Ollama not responding**: Make sure Ollama is running (`ollama serve`)
- **Playwright errors on Windows**: Use `python start_server.py` instead of `uvicorn` directly
- **Playwright errors**: Run `playwright install chromium` again
- **Port 8000 already in use**: Change the port in `start_server.py` or use `--port 8001`
- **"Cannot connect to Ollama"**: Check that Ollama is running and the model is installed (`ollama list`)

