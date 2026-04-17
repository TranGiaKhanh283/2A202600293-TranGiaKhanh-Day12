# Day 12 Lab — Mission Answers

> **Student:** Trần Gia Khánh · **Student ID:** 2A202600293
> **AICB-P1 · VinUniversity 2026**

---

## Part 1: Localhost vs Production

### Exercise 1.1 — Anti-patterns found in `01-localhost-vs-production/develop/app.py`

1. **Hardcoded secrets** — `OPENAI_API_KEY = "sk-..."` và `DATABASE_URL` có password baked thẳng vào code. Push lên GitHub là lộ key / credential ngay lập tức.
2. **Không tách config khỏi code** — `DEBUG = True`, `MAX_TOKENS = 500` fix cứng. Muốn đổi giữa dev / staging / prod phải sửa code và redeploy.
3. **`print()` thay vì logging** — Không có log level, không JSON structured, không ship được lên log aggregator; thậm chí còn `print(OPENAI_API_KEY)` ra stdout (leak secret).
4. **Thiếu `/health` endpoint** — Platform (Railway/Render/K8s) không có cách biết container còn sống hay đã treo để restart.
5. **Port & host cứng** — `host="localhost"` chỉ bind loopback, không nhận traffic từ ngoài container; `port=8000` fix cứng, không đọc `$PORT` do cloud inject.
6. **`reload=True` trong production** — Hot reload tốn RAM, khởi lại worker khi có file change, không phù hợp production.
7. **Không có graceful shutdown** — Không handle `SIGTERM`; cloud kill container giữa chừng là request đang chạy bị đứt.
8. **Không validate input** — `question: str` nhận bất cứ thứ gì, không giới hạn length, không có Pydantic schema.
9. **Không có rate limit / auth** — Public URL đồng nghĩa với việc ai cũng gọi được.

### Exercise 1.2 — Basic version

Chạy `python app.py` trong `01-localhost-vs-production/develop` thành công. `POST /ask` trả về câu trả lời từ `mock_llm`. Nó **chạy** nhưng không production-ready vì các lý do ở 1.1.

### Exercise 1.3 — So sánh Basic vs Advanced

| Feature         | Basic (`develop/app.py`) | Advanced (`production/app.py`) | Tại sao quan trọng?                                                                                   |
|-----------------|--------------------------|--------------------------------|--------------------------------------------------------------------------------------------------------|
| Config          | Hardcode trong code      | `os.getenv(...)` qua `config.py` + `.env` | Cho phép thay đổi giữa env (dev/staging/prod) mà không đổi code; secret không lọt vào git lịch sử. |
| Health check    | Không có                 | `GET /health` + `GET /ready`   | Platform (Railway/Render/K8s) biết container nào còn sống để restart và route traffic.                |
| Logging         | `print()`                 | JSON structured (`logging` + `json.dumps`) | Log có level, tag, ship được vào Datadog/Loki/CloudWatch, search và alert được.                      |
| Shutdown        | Đột ngột (không handler) | `signal.SIGTERM` + lifespan    | Không mất data, hoàn tất request đang xử lý, đóng connection gọn gàng trước khi container chết.       |
| Auth            | Không có                 | `X-API-Key` header             | Không lộ endpoint public cho cả thế giới gọi → tiết kiệm cost và chống abuse.                         |
| Rate limit      | Không có                 | Sliding window / token bucket  | Một user đi loop không ddos được cả service.                                                          |
| Input validation| Không                    | Pydantic `BaseModel`           | Trả 422 thay vì 500, bảo vệ khỏi input xấu.                                                           |

### Checkpoint 1

- [x] Hiểu tại sao hardcode secrets là nguy hiểm
- [x] Biết cách dùng environment variables (`Settings` dataclass + `os.getenv`)
- [x] Hiểu vai trò của `/health` endpoint
- [x] Biết graceful shutdown là gì và cách đăng ký handler cho `SIGTERM`

---

## Part 2: Docker Containerization

### Exercise 2.1 — Đọc `02-docker/develop/Dockerfile`

1. **Base image:** `python:3.11-slim` — Debian slim, đã có sẵn Python 3.11, nhẹ (~50 MB) hơn `python:3.11` (~120 MB+), không có toolchain thừa.
2. **Working directory:** `/app` — nơi chứa code, tách biệt khỏi `/` và `/tmp`.
3. **Tại sao `COPY requirements.txt` trước code?** Docker build theo layer và cache theo từng instruction. Nếu chỉ đổi code Python (không đổi requirements), Docker reuse layer `pip install` đã cache → rebuild nhanh hơn rất nhiều.
4. **`CMD` vs `ENTRYPOINT`:**
   - `CMD` = lệnh mặc định, có thể override khi `docker run <image> <other-cmd>`.
   - `ENTRYPOINT` = lệnh cố định không override được, arg truyền vào `CMD` sẽ thành argument cho `ENTRYPOINT`.
   - Pattern phổ biến: `ENTRYPOINT ["python"]` + `CMD ["app.py"]`.

### Exercise 2.2 — Basic image

```
docker build -t my-agent:develop 02-docker/develop
docker images my-agent:develop   # ~180–220 MB tùy version pip packages
docker run -p 8000:8000 my-agent:develop
```

### Exercise 2.3 — Multi-stage build

- **Stage 1 (builder):** dùng `python:3.11-slim` + `gcc`/`libpq-dev`, `pip install --user` vào `/root/.local`.
- **Stage 2 (runtime):** `python:3.11-slim` mới, tạo user non-root, `COPY --from=builder /root/.local /home/agent/.local`, chỉ copy code, **không copy toolchain**.
- **Kết quả:** image runtime không có `gcc`, build cache, pip wheels, doc → nhỏ hơn đáng kể.

| Image                  | Size (approx.) |
|------------------------|----------------|
| `my-agent:develop`     | ~220 MB        |
| `my-agent:advanced`    | ~130 MB        |
| Giảm                   | ~40–50%        |

### Exercise 2.4 — Docker Compose stack

```
┌─────────┐        ┌─────────┐        ┌──────────┐
│ Client  │──────► │  Nginx  │──────► │  Agent   │
└─────────┘        │  :80    │        │  :8000   │
                   └────┬────┘        └────┬─────┘
                                           │
                                           ▼
                                     ┌──────────┐
                                     │  Redis   │
                                     │  :6379   │
                                     └──────────┘
```

- `agent` service (FastAPI) kết nối `redis` qua DNS service name `redis:6379`.
- `nginx` là reverse proxy / load balancer đứng trước `agent`.
- `depends_on` với `condition: service_healthy` giúp agent chỉ khởi động sau khi Redis healthy.

### Checkpoint 2

- [x] Hiểu cấu trúc Dockerfile (FROM / WORKDIR / COPY / RUN / CMD)
- [x] Biết lợi ích của multi-stage (ảnh nhỏ, bề mặt tấn công hẹp)
- [x] Hiểu Docker Compose orchestration (services, depends_on, healthcheck)
- [x] Biết debug container (`docker logs`, `docker exec -it ... /bin/sh`)

---

## Part 3: Cloud Deployment

### Exercise 3.1 — Railway (planned)

Lab sẵn `railway.toml`:

```
[build]
builder = "DOCKERFILE"

[deploy]
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2"
healthcheckPath = "/health"
```

Quy trình:

```
railway login
railway init
railway variables set AGENT_API_KEY=<secret>
railway variables set ENVIRONMENT=production
railway up
railway domain           # -> https://<name>.up.railway.app
```

### Exercise 3.2 — Render vs Railway

| Điểm                | `railway.toml`                   | `render.yaml`                         |
|---------------------|----------------------------------|---------------------------------------|
| Scope               | 1 service                        | 1 file mô tả **nhiều** services       |
| Secret              | `railway variables set`          | `sync: false` + set qua dashboard     |
| Healthcheck         | `healthcheckPath`                | `healthCheckPath`                     |
| Build               | Dockerfile / Nixpacks            | Docker / native / Blueprint           |
| Scale               | CLI `railway scale`              | Dashboard → Instances                 |

Cả hai đều declarative (IaC-lite), nhưng `render.yaml` gần với format như Kubernetes / Helm hơn (multi-service blueprint).

### Exercise 3.3 — GCP Cloud Run (đọc hiểu)

`cloudbuild.yaml` + `service.yaml` chỉ ra pipeline: `gcloud builds submit → build image → push Artifact Registry → deploy Cloud Run`. CI/CD thật sẽ chạy từ GitHub Actions / Cloud Build trigger khi push `main`.

### Checkpoint 3

- [x] Hiểu cấu hình deploy cho ít nhất 1 platform (Railway)
- [x] Biết cách set env vars trên cloud
- [x] Biết cách xem log (`railway logs`, Render dashboard)

---

## Part 4: API Security

### Exercise 4.1 — API Key authentication (`04-api-gateway/develop`)

- Key được check ở dependency `verify_api_key` qua header `X-API-Key`.
- Sai key → `raise HTTPException(401, "Invalid API key")`.
- Rotate: đổi biến env `AGENT_API_KEY` + restart container; cấp nhiều key bằng cách so sánh với 1 set thay vì 1 chuỗi.

Test đã chạy OK:

```
POST /ask  (no key)           -> 401 Unauthorized
POST /ask  X-API-Key: secret  -> 200 OK + answer
```

### Exercise 4.2 — JWT (`04-api-gateway/production/auth.py`)

- Flow: `POST /token` với `username/password` → server ký `HS256` bằng `JWT_SECRET` → client dùng `Authorization: Bearer <token>` cho các request sau.
- Payload: `{sub, exp, role}`.
- Ưu điểm so với API key: token có expiry, có thể encode role/permission.

### Exercise 4.3 — Rate limiting

- Algorithm dùng trong Final Project: **sliding window** — `deque` các timestamp, pop các entry cũ hơn 60s, nếu còn ≥ `RATE_LIMIT_PER_MINUTE` → 429.
- Limit mặc định: 20 req/min (đã chỉnh xuống 10 khi chạy test_security).
- Bypass cho admin: thêm check role trong dependency (ví dụ `if role == "admin": return`).

Test đã chạy OK: gửi 20 request → hit `429 Too Many Requests` ngay tại request #11 (limit 10/min).

### Exercise 4.4 — Cost guard

Final Project tracking `_daily_cost` global (in-memory) + reset theo ngày. Khi có Redis sẽ đổi sang key `budget:<user_id>:<YYYY-MM>` và `INCRBYFLOAT`:

```python
def check_budget(user_id, estimated_cost):
    month = datetime.utcnow().strftime("%Y-%m")
    key = f"budget:{user_id}:{month}"
    current = float(r.get(key) or 0)
    if current + estimated_cost > MONTHLY_BUDGET:
        return False
    r.incrbyfloat(key, estimated_cost)
    r.expire(key, 32 * 24 * 3600)
    return True
```

Lý do dùng Redis: nhiều instance cùng chia sẻ counter → không double-spend khi scale ngang.

### Checkpoint 4

- [x] Implement API key auth
- [x] Hiểu JWT flow
- [x] Implement rate limiting (sliding window)
- [x] Implement cost guard (daily budget version hoạt động; Redis version sẵn sàng khi bật REDIS_URL)

---

## Part 5: Scaling & Reliability

### Exercise 5.1 — Health + Readiness

- `GET /health` → luôn 200 nếu process sống (liveness).
- `GET /ready` → 503 khi `_is_ready == False` (lifespan chưa complete) hoặc downstream (Redis / DB) fail. Khi ready, trả 200.

Kết quả `curl`:

```
GET /health  -> {"status":"ok", ...}
GET /ready   -> {"ready":true}
```

### Exercise 5.2 — Graceful shutdown

`signal.signal(signal.SIGTERM, _handle_signal)` log lại `{"event":"signal"}`. FastAPI lifespan đóng resource khi uvicorn gửi `SIGTERM` với `timeout_graceful_shutdown=30`. Request đang xử lý có 30 giây để finish.

### Exercise 5.3 — Stateless design

- Không giữ `conversation_history` trong dict global → chuyển sang Redis key `history:<user_id>` bằng `LRANGE / RPUSH`.
- Lý do: khi scale lên 3 instance, user request có thể rơi vào bất kỳ instance nào; nếu state trong RAM, user A hỏi lần 2 nhưng routing sang instance B → mất context.

### Exercise 5.4 — Load balancing

`docker compose up --scale agent=3` tạo 3 replica. Nginx `upstream agent_backend` round-robin sang 3 container. Kill 1 container → Nginx tự route sang 2 cái còn lại, traffic không gián đoạn.

### Exercise 5.5 — Test stateless

`05-scaling-reliability/production/test_stateless.py` chạy kịch bản: tạo conversation → kill 1 replica → tiếp tục hỏi → vẫn nhớ được context (nhờ Redis).

### Checkpoint 5

- [x] `/health` + `/ready` hoạt động đúng
- [x] `SIGTERM` handler được đăng ký
- [x] Final Project stateless-ready (dùng Redis nếu `REDIS_URL` set)
- [x] Hiểu load balancing với Nginx
- [x] Hiểu cách verify stateless design

---

## Part 6 — Final Project self-check

Tất cả yêu cầu từ `CODE_LAB.md` đã đạt, được xác nhận qua 2 script:

1. `python 06-lab-complete/check_production_ready.py` → **20/20** (100%).
2. `python 06-lab-complete/test_security.py` (chạy cùng uvicorn) → **All tests passed** (auth 401/200 + rate limit 429).

Xem chi tiết trong `DEPLOYMENT.md` và logs của `06-lab-complete`.
