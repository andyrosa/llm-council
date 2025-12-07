"""Probe which OpenRouter models honor the web-search plugin using SHA canary."""

import asyncio
import re
import subprocess
import sys
import pathlib
import time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx
from backend.config import OPENROUTER_API_KEY, OPENROUTER_API_URL, load_model_registry

CANARY_REPO, CANARY_BRANCH = "https://github.com/torvalds/linux", "master"
TEST_PROMPT = f"What is the full 40-character SHA of the most recent commit on {CANARY_BRANCH} of {CANARY_REPO}? Reply with ONLY the SHA."


def get_actual_sha() -> str:
    result = subprocess.run(["git", "ls-remote", CANARY_REPO, f"refs/heads/{CANARY_BRANCH}"],
                            capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"git ls-remote failed: {result.stderr}")
    return result.stdout.split()[0].lower()


async def probe_model(model: str, actual_sha: str) -> dict:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not configured")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": TEST_PROMPT}],
        "plugins": [{"id": "web", "engine": "native"}],
    }
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(OPENROUTER_API_URL,
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json=payload)
    except Exception as e:
        return {"model": model, "result": str(e)[:40], "match": False, "time": time.perf_counter() - start}

    elapsed = time.perf_counter() - start
    if resp.status_code != 200:
        return {"model": model, "result": f"http-{resp.status_code}", "match": False, "time": elapsed}

    content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    found = re.search(r"[0-9a-fA-F]{40}", content)
    sha = found.group(0).lower() if found else ""
    return {"model": model, "result": sha or content[:40], "match": sha == actual_sha, "time": elapsed}


async def main():
    # Allow optional single-model override via CLI
    cli_model = sys.argv[1] if len(sys.argv) > 1 else None
    models = [cli_model] if cli_model else [e["id"] for e in load_model_registry()]

    actual_sha = get_actual_sha()
    print(f"Actual: {actual_sha}\n")
    print(f"{'Model':<35} {'Result':<44} {'OK':<4} {'Time':>6}")
    print("-" * 95)

    results = await asyncio.gather(*[probe_model(m, actual_sha) for m in models])
    for r in sorted(results, key=lambda x: x["time"]):
        mark = "✓" if r["match"] else ""
        print(f"{r['model']:<35} {r['result']:<44} {mark:<4} {r['time']:>5.1f}s")

    winners = [r["model"] for r in results if r["match"]]
    print(f"\nVerified: {winners if winners else 'none'}")


if __name__ == "__main__":
    asyncio.run(main())
