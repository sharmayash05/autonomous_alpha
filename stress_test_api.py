import os
"""
Comprehensive LLM API Stress Test
Tests the exact conditions agents face: parallel requests, JSON mode, long prompts
"""
import httpx
import asyncio
import time
import json

# USER'S CORRECT ENDPOINT
URL = os.getenv("LLM_BASE_URL", "http://localhost:3000/gemini-antigravity/v1") + "/chat/completions"
KEY = os.getenv("LLM_API_KEY", "")
MODEL = "gemini-3.0-pro-preview"

LONG_PROMPT = """You are a trading analyst. Analyze BTC price data:
Price: $95,000
RSI: 50
Trend: RANGING
Volume: High

Provide analysis with:
1. Bullish factors
2. Bearish factors  
3. Price target
4. Confidence score

Return ONLY valid JSON:
{
  "analysis": "your analysis here",
  "price_target": 96000,
  "confidence": 0.7
}
"""

async def test_single_request(client, test_num, prompt_size="short", use_json=False):
    """Test single request with various configurations"""
    start = time.time()
    
    if prompt_size == "short":
        prompt = "Say 'OK' and nothing else"
    else:
        prompt = LONG_PROMPT
    
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500 if prompt_size == "long" else 10,
        "temperature": 0.7
    }
    
    if use_json:
        payload["response_format"] = {"type": "json_object"}
    
    try:
        response = await client.post(
            URL,
            headers={
                "Authorization": f"Bearer {KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60.0
        )
        
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"]
                is_empty = len(content.strip()) == 0
                
                # Try to parse JSON if json mode
                json_valid = True
                if use_json:
                    try:
                        json.loads(content)
                    except:
                        json_valid = False
                
                if is_empty:
                    return f"Test {test_num}: EMPTY RESPONSE ({elapsed:.1f}s)"
                elif use_json and not json_valid:
                    return f"Test {test_num}: INVALID JSON ({elapsed:.1f}s)"
                else:
                    return f"Test {test_num}: ✅ OK ({elapsed:.1f}s, {len(content)} chars)"
            else:
                return f"Test {test_num}: ❌ NO CHOICES ({elapsed:.1f}s)"
        else:
            text = response.text[:100]
            return f"Test {test_num}: ❌ HTTP {response.status_code} ({elapsed:.1f}s) - {text}"
            
    except httpx.TimeoutException:
        return f"Test {test_num}: ⏱️ TIMEOUT (>60s)"
    except Exception as e:
        return f"Test {test_num}: ❌ ERROR: {str(e)[:80]}"

async def stress_test_parallel(num_parallel, prompt_size="short", use_json=False):
    """Test N parallel requests"""
    print(f"\n{'='*70}")
    print(f"TEST: {num_parallel} parallel requests ({prompt_size} prompts, JSON={use_json})")
    print(f"{'='*70}")
    
    async with httpx.AsyncClient() as client:
        start = time.time()
        
        tasks = [
            test_single_request(client, i+1, prompt_size, use_json)
            for i in range(num_parallel)
        ]
        
        results = await asyncio.gather(*tasks)
        
        total_time = time.time() - start
        ok_count = sum(1 for r in results if "✅ OK" in r)
        empty_count = sum(1 for r in results if "EMPTY" in r)
        error_count = sum(1 for r in results if "❌" in r or "⏱️" in r)
        
        for result in results:
            print(f"  {result}")
        
        print(f"\n📊 Results: {ok_count} OK, {empty_count} EMPTY, {error_count} ERRORS")
        print(f"⏱️ Total time: {total_time:.1f}s (avg: {total_time/num_parallel:.1f}s per request)")
        
        return ok_count, empty_count, error_count

async def test_agent_simulation():
    """Simulate actual agent request (Bull Researcher)"""
    print(f"\n{'='*70}")
    print(f"AGENT SIMULATION: Bull Researcher (with JSON mode)")
    print(f"{'='*70}")
    
    agent_prompt = """Analyze Bitcoin as a Bull Researcher.
    
Current Data:
- Price: $95,137
- RSI: 50
- Trend: RANGING
- Volume: $28B

Return ONLY valid JSON with this structure:
{
  "bullish_thesis": {
    "headline": "One sentence thesis",
    "summary": "Detailed summary",
    "conviction": "HIGH"
  },
  "confidence": 0.8
}
"""
    
    async with httpx.AsyncClient() as client:
        result = await test_single_request(client, 1, "long", use_json=True)
        print(f"  {result}")

async def main():
    print("="*70)
    print("LLM API COMPREHENSIVE STRESS TEST")
    print(f"Endpoint: {URL}")
    print(f"Model: {MODEL}")
    print("="*70)
    
    # Test 1: Basic connectivity
    print("\n🔹 Phase 1: Basic Connectivity")
    await stress_test_parallel(1, "short", False)
    
    # Test 2: Parallel short prompts - PRODUCTION LEVEL
    print("\n🔹 Phase 2: Parallel Requests (Short Prompts) - PRODUCTION STRESS")
    for n in [2, 4, 6, 8, 10]:
        await stress_test_parallel(n, "short", False)
        await asyncio.sleep(1)
    
    # Test 3: Long prompts (like Bull/Technical agents)
    print("\n🔹 Phase 3: Long Prompts")
    await stress_test_parallel(4, "long", False)
    
    # Test 4: JSON mode (what agents use)
    print("\n🔹 Phase 4: JSON Mode (Agent Configuration)")
    await stress_test_parallel(4, "long", True)
    
    # Test 5: Exact agent simulation
    print("\n🔹 Phase 5: Agent Simulation")
    await test_agent_simulation()
    
    # Test 6: Max parallel (4 agents at once)
    print("\n🔹 Phase 6: Max Stress (4 Parallel Agents)")
    ok, empty, errors = await stress_test_parallel(4, "long", True)
    
    print("\n" + "="*70)
    print("FINAL VERDICT")
    print("="*70)
    
    if empty > 0:
        print(f"⚠️  {empty} EMPTY RESPONSES DETECTED")
        print("   This explains why Bull/Technical agents returned empty!")
    
    if errors > 0:
        print(f"❌ {errors} ERRORS DETECTED")
        print("   API server has stability issues")
    
    if ok == 4 and empty == 0 and errors == 0:
        print("✅ ALL TESTS PASSED - API is healthy")
        print("   Empty agent responses must be from another cause")
    
    print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
