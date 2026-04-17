#!/usr/bin/env python3
"""
Automated grading script for Day 12 Lab (verbatim from INSTRUCTOR_GUIDE.md).

Usage: python grade.py <student-repo-path> <public-url> <api-key>
"""

import sys
import os
import subprocess
import requests
import time
from pathlib import Path


class Grader:
    def __init__(self, repo_path, public_url, api_key):
        self.repo_path = Path(repo_path)
        self.public_url = public_url
        self.api_key = api_key
        self.score = 0
        self.max_score = 60
        self.results = []

    def test(self, name, points, func):
        try:
            func()
            self.score += points
            self.results.append(f"PASS {name}: {points}/{points}")
            return True
        except AssertionError as e:
            self.results.append(f"FAIL {name}: 0/{points} - {e}")
            return False
        except Exception as e:
            self.results.append(f"FAIL {name}: 0/{points} - Error: {e}")
            return False

    def check_file_exists(self, filepath):
        assert (self.repo_path / filepath).exists(), f"{filepath} not found"

    def check_dockerfile(self):
        dockerfile = (self.repo_path / "Dockerfile").read_text(encoding="utf-8")
        assert "FROM" in dockerfile, "No FROM instruction"
        assert "as builder" in dockerfile.lower(), "Not multi-stage"
        assert "slim" in dockerfile.lower(), "Not using slim image"

    def check_docker_compose(self):
        compose = (self.repo_path / "docker-compose.yml").read_text(encoding="utf-8")
        assert "redis:" in compose, "No redis service"
        assert "agent:" in compose or "app:" in compose, "No agent service"

    def check_no_secrets(self):
        bad_tokens = ["sk-", "password123", "hardcoded"]
        app_dir = self.repo_path / "app"
        found = []
        for path in app_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for bad in bad_tokens:
                if bad in text:
                    found.append(f"{path.name}:{bad}")
        assert not found, f"Found hardcoded secrets: {found}"

    def test_health_endpoint(self):
        r = requests.get(f"{self.public_url}/health", timeout=10)
        assert r.status_code == 200, f"Health check failed: {r.status_code}"

    def test_ready_endpoint(self):
        r = requests.get(f"{self.public_url}/ready", timeout=10)
        assert r.status_code in [200, 503], f"Ready check failed: {r.status_code}"

    def test_auth_required(self):
        r = requests.post(f"{self.public_url}/ask", json={"question": "test"})
        assert r.status_code == 401, "Should require authentication"

    def test_auth_works(self):
        r = requests.post(
            f"{self.public_url}/ask",
            headers={"X-API-Key": self.api_key},
            json={"question": "Hello"},
        )
        assert r.status_code == 200, f"Auth failed: {r.status_code}"

    def test_rate_limiting(self):
        for i in range(15):
            r = requests.post(
                f"{self.public_url}/ask",
                headers={"X-API-Key": self.api_key},
                json={"question": f"test {i}"},
            )
        assert r.status_code == 429, "Rate limiting not working"

    def test_conversation_history(self):
        # Wait a bit so the rate-limit window has space
        time.sleep(60)
        r1 = requests.post(
            f"{self.public_url}/ask",
            headers={"X-API-Key": self.api_key},
            json={"question": "My name is Alice"},
        )
        assert r1.status_code == 200, f"first call {r1.status_code}"
        r2 = requests.post(
            f"{self.public_url}/ask",
            headers={"X-API-Key": self.api_key},
            json={"question": "What is my name?"},
        )
        assert r2.status_code == 200, f"second call {r2.status_code}"

    def run_all_tests(self):
        print("Running automated tests...\n")

        self.test("Dockerfile exists", 2, lambda: self.check_file_exists("Dockerfile"))
        self.test("docker-compose.yml exists", 2, lambda: self.check_file_exists("docker-compose.yml"))
        self.test("requirements.txt exists", 1, lambda: self.check_file_exists("requirements.txt"))

        self.test("Multi-stage Dockerfile", 5, self.check_dockerfile)
        self.test("Docker Compose has services", 4, self.check_docker_compose)

        self.test("No hardcoded secrets", 5, self.check_no_secrets)
        self.test("Auth required", 5, self.test_auth_required)
        self.test("Auth works", 5, self.test_auth_works)
        self.test("Rate limiting", 5, self.test_rate_limiting)

        self.test("Health endpoint", 3, self.test_health_endpoint)
        self.test("Ready endpoint", 3, self.test_ready_endpoint)

        self.test("Conversation history", 5, self.test_conversation_history)

        self.test("Public URL works", 5, self.test_health_endpoint)

        print("\n" + "=" * 60)
        print("GRADING RESULTS")
        print("=" * 60)
        for result in self.results:
            print(result)
        print("=" * 60)
        print(f"TOTAL SCORE: {self.score}/{self.max_score}")
        print(f"PERCENTAGE:  {self.score / self.max_score * 100:.1f}%")

        if self.score >= self.max_score * 0.7:
            print("PASSED")
        else:
            print("FAILED (need 70% to pass)")

        return self.score


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python grade.py <repo-path> <public-url> <api-key>")
        sys.exit(1)

    repo_path = sys.argv[1]
    public_url = sys.argv[2].rstrip("/")
    api_key = sys.argv[3]

    grader = Grader(repo_path, public_url, api_key)
    score = grader.run_all_tests()
    sys.exit(0 if score >= grader.max_score * 0.7 else 1)
