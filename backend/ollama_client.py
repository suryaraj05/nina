import httpx, json

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"

async def call_qwen(prompt: str, timeout: int = 45) -> str:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(OLLAMA_URL, json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 512,
                    "top_p": 0.9,
                }
            })
            r.raise_for_status()
            return r.json()["response"]
    except httpx.ConnectError:
        raise Exception(f"Cannot connect to Ollama at {OLLAMA_URL}. Make sure Ollama is running.")
    except httpx.TimeoutException:
        raise Exception(f"Ollama request timed out after {timeout} seconds.")
    except httpx.HTTPStatusError as e:
        raise Exception(f"Ollama returned error {e.response.status_code}: {e.response.text}")
    except Exception as e:
        raise Exception(f"Error calling Ollama: {str(e)}")

def safe_json(raw: str):
    clean = raw.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        clean = "\n".join(lines[1:-1])
    return json.loads(clean)

