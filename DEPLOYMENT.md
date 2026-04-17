# Deployment Information — Day 12 Final Project

> Student: Trần Gia Khánh · 2A202600293
> Project: `06-lab-complete/` — Production-ready AI Agent

---

## Public URL

> Chưa deploy public tại thời điểm submit (bước này yêu cầu tài khoản Railway/Render/Cloud Run).
> Cấu hình deploy đã sẵn sàng (`railway.toml` + `render.yaml`), chỉ cần chạy lệnh bên dưới.

Placeholder public URL khi deploy:

```
https://<agent-name>.up.railway.app
https://<agent-name>.onrender.com
```

Local URL đã được verify:

```
http://127.0.0.1:8010
```

## Platform

- **Primary:** Railway (`railway.toml`, `builder = DOCKERFILE`)
- **Backup:** Render (`render.yaml`)
- **Optional:** GCP Cloud Run (`03-cloud-deployment/production-cloud-run`)

## Deploy Railway trong 5 phút

```bash
cd 06-lab-complete
npm i -g @railway/cli
railway login
railway init
railway variables set AGENT_API_KEY=<một-chuỗi-random-đủ-mạnh>
railway variables set JWT_SECRET=<chuỗi-random-khác>
railway variables set ENVIRONMENT=production
railway variables set RATE_LIMIT_PER_MINUTE=20
railway variables set DAILY_BUDGET_USD=5
railway up
railway domain
```

## Deploy Render

1. Push repo lên GitHub.
2. Render Dashboard → **New** → **Blueprint** → connect repo.
3. Render đọc `06-lab-complete/render.yaml` và build service.
4. Dashboard → Environment → set:
   - `AGENT_API_KEY`
   - `JWT_SECRET`
   - `ENVIRONMENT=production`
5. **Manual Deploy → Deploy latest commit**.

## Environment Variables

| Variable               | Purpose                                    | Default           |
|------------------------|--------------------------------------------|-------------------|
| `HOST`                 | Bind address                               | `0.0.0.0`         |
| `PORT`                 | Listen port (cloud inject)                 | `8000`            |
| `ENVIRONMENT`          | `development` / `staging` / `production`   | `development`     |
| `AGENT_API_KEY`        | Shared secret cho `X-API-Key`              | `dev-key-change-me` *(bắt buộc đổi prod)* |
| `JWT_SECRET`           | Ký JWT token                               | `dev-jwt-secret`  |
| `RATE_LIMIT_PER_MINUTE`| Ngưỡng sliding window                      | `20`              |
| `DAILY_BUDGET_USD`     | Giới hạn cost daily                        | `5.0`             |
| `OPENAI_API_KEY`       | (optional) dùng LLM thật thay mock         | *(empty)*         |
| `REDIS_URL`            | (optional) cho stateless + cost guard prod | *(empty)*         |
| `ALLOWED_ORIGINS`      | CORS whitelist                             | `*`               |

## Test Commands

### 1) Health check

```bash
curl -sS $URL/health | jq
# Expected:
# {
#   "status": "ok",
#   "version": "1.0.0",
#   "environment": "...",
#   "uptime_seconds": <n>,
#   "checks": {"llm":"mock"},
#   ...
# }
```

### 2) Readiness

```bash
curl -sS $URL/ready
# Expected: {"ready":true}
```

### 3) Auth required (should 401)

```bash
curl -sS -o /dev/null -w "%{http_code}\n" -X POST $URL/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'
# Expected: 401
```

### 4) Valid key works (should 200)

```bash
curl -sS -X POST $URL/ask \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is deployment?"}'
```

### 5) Rate limiting (should eventually 429)

```bash
for i in $(seq 1 20); do
  curl -sS -o /dev/null -w "req $i -> %{http_code}\n" \
    -X POST $URL/ask \
    -H "X-API-Key: $AGENT_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"question\":\"probe $i\"}"
done
# Expected: status chuyển từ 200 sang 429 sau khi vượt RATE_LIMIT_PER_MINUTE
```

## Local Verification (đã chạy)

Terminal 1:
```powershell
cd 06-lab-complete
$env:AGENT_API_KEY="secret"
$env:RATE_LIMIT_PER_MINUTE="10"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Terminal 2:
```powershell
cd 06-lab-complete
$env:BASE_URL="http://127.0.0.1:8010"
$env:AGENT_API_KEY="secret"
python test_security.py
# Output:
#   [test_api_key] POST /ask WITHOUT key ...  -> 401 Unauthorized (OK)
#   [test_api_key] POST /ask WITH valid key ...  -> 200 OK
#   [test_rate_limit] Sending 20 requests ...  -> Hit 429 rate limit at request #11 (OK)
#   All tests passed
```

Production-readiness scan:
```powershell
cd 06-lab-complete
python check_production_ready.py
# Result: 20/20 checks passed (100%)  -> PRODUCTION READY
```

## Architecture

```
  Client
    │
    ▼
  Railway / Render Edge (TLS)
    │
    ▼
  uvicorn workers (2) — app.main:app
    │
    ├── CORS + security headers middleware
    ├── Auth dependency (X-API-Key)
    ├── Rate limit (sliding window, 60s)
    ├── Cost guard (daily budget USD)
    └── Mock LLM (replaced by OpenAI when OPENAI_API_KEY set)
```

When `REDIS_URL` is configured the rate limiter and cost guard are expected to
move to Redis so multiple replicas share state (see `CODE_LAB.md` Part 5).
