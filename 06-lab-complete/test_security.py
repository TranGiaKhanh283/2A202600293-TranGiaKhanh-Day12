"""
test_security.py — Security tests from INSTRUCTOR_GUIDE.md (Part 4)

Runs against a local instance of the Day 12 Final Project agent.

Usage:
    # In one terminal (from 06-lab-complete folder):
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

    # In another terminal:
    python test_security.py
"""
import os
import sys
import time
import requests

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("AGENT_API_KEY", "secret")


def wait_for_server(url: str, timeout: int = 30) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{url}/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def test_api_key():
    print("[test_api_key] POST /ask WITHOUT key ...")
    r = requests.post(f"{BASE_URL}/ask", json={"question": "test"}, timeout=10)
    assert r.status_code == 401, f"Expected 401 without API key, got {r.status_code}"
    print("  -> 401 Unauthorized (OK)")

    print("[test_api_key] POST /ask WITH valid key ...")
    r = requests.post(
        f"{BASE_URL}/ask",
        headers={"X-API-Key": API_KEY},
        json={"question": "test"},
        timeout=10,
    )
    assert r.status_code == 200, f"Expected 200 with valid API key, got {r.status_code} body={r.text}"
    body = r.json()
    assert "answer" in body, "Response missing 'answer' field"
    print(f"  -> 200 OK, answer='{body['answer'][:60]}...'")


def test_rate_limit():
    print("[test_rate_limit] Sending 20 requests with same key ...")
    r = None
    hit_limit_at = None
    for i in range(20):
        r = requests.post(
            f"{BASE_URL}/ask",
            headers={"X-API-Key": API_KEY},
            json={"question": f"test {i}"},
            timeout=10,
        )
        if r.status_code == 429 and hit_limit_at is None:
            hit_limit_at = i + 1
    assert r.status_code == 429, (
        f"Expected 429 after exceeding rate limit, "
        f"final status={r.status_code} body={r.text[:200]}"
    )
    print(f"  -> Hit 429 rate limit at request #{hit_limit_at} (OK)")


if __name__ == "__main__":
    print(f"Target: {BASE_URL}")
    print(f"API Key: {API_KEY[:4]}****")

    if not wait_for_server(BASE_URL):
        print(f"[ERROR] Server not reachable at {BASE_URL}/health")
        sys.exit(2)

    try:
        test_api_key()
        test_rate_limit()
    except AssertionError as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)

    print("\nAll tests passed")
