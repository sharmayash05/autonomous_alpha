import os
"""LLM Parallel Request Test"""
import httpx
import asyncio
import time

URL = os.getenv("LLM_BASE_URL", "http://localhost:3000/gemini-antigravity/v1") + "/chat/completions"
KEY = os.getenv("LLM_API_KEY", "")
MODEL = "gemini-3.0-pro-preview"

async def req(client, name):
    start = time.time()
    try:
        r = await client.post(URL, headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
            json={"model": MODEL, "messages": [{"role": "user", "content": f"{name}: Hi"}], "max_tokens": 50})
        data = r.json()
        ok = "choices" in data
        return f"{name}: {'OK' if ok else 'FAIL-403'} ({time.time()-start:.1f}s)"
    except Exception as e:
        return f"{name}: ERROR ({e})"

async def test(n):
    async with httpx.AsyncClient(timeout=60) as c:
        names = [chr(65+i) for i in range(n)]
        results = await asyncio.gather(*[req(c, name) for name in names])
        ok = sum(1 for r in results if "OK" in r)
        print(f"{n} parallel: {ok}/{n} OK")
        for r in results: print(f"  {r}")

async def main():
    print("="*50)
    print("PARALLEL REQUEST TEST")
    print("="*50)
    for n in [2, 3, 4, 5, 6]:
        await test(n)
        await asyncio.sleep(2)  # Rest between tests
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
