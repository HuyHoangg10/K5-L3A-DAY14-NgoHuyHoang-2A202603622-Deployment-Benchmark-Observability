# Day 14 Lab — Mission Answers

> **Học viên:** Ngô Huy Hoàng  
> **MSSV:** 2A202603622  
> **Lớp:** K5-L3A  
> **Bài làm:** Deployment, Benchmark & Observability  

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns tìm thấy trong `01-localhost-vs-production/develop/app.py`
1. **Hardcode secrets & credentials trong source code (dòng 17–18):**
   `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` — đẩy lên GitHub là lộ secret ngay lập tức.
2. **Hardcode config thay vì dùng env vars (dòng 21–22):** `DEBUG = True`, `MAX_TOKENS = 500` không thể đổi nhanh giữa dev / staging / production.
3. **Logging bằng `print()` và làm lộ secret ra log (dòng 33–34, 38):** `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` vừa khó parse tự động vừa in thẳng API key ra stdout.
4. **Thiếu Health Check / Readiness Endpoint (dòng 42–43):** Không có `/health` và `/ready`, nền tảng cloud/load balancer không phát hiện được khi app treo hoặc chưa sẵn sàng.
5. **Cấu hình server chỉ chạy được trên localhost và tắt đột ngột (dòng 49–53):** `host="localhost"`, cố định `port=8000`, bật `reload=True` trong production, và không xử lý `SIGTERM`/graceful shutdown.

**So sánh đối chiếu code đã sửa trong `01-localhost-vs-production/production/`:**
- `production/config.py` (dòng 17–43): Toàn bộ cấu hình đọc từ `os.getenv(...)`, và hàm `Settings.validate()` kiểm tra **fail-fast** (`raise ValueError("AGENT_API_KEY must be set in production!")` khi thiếu `AGENT_API_KEY` ở môi trường `production`).
- `production/app.py` (dòng 28–31, 40–67, 135–161, 180–198): Bổ sung JSON logging (`logging.basicConfig`), `lifespan` + `signal.signal(signal.SIGTERM, handle_sigterm)` để graceful shutdown, thêm `GET /health` + `GET /ready`, bind `host="0.0.0.0"` và đọc `PORT` từ env.

### Exercise 1.2: Kết quả chạy thực tế bản develop (và kiểm chứng production)
Chạy `01-localhost-vs-production/develop/app.py` và gọi đúng theo query param (lưu ý #3 K5):
```bash
curl -X POST "http://localhost:8000/ask?question=Hello"
```
Output thực tế ghi nhận:
```json
HTTP 200: {"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```
Khi chạy thử `01-localhost-vs-production/production/app.py` với `ENVIRONMENT=production` và chưa đặt `AGENT_API_KEY`, app báo lỗi ngay lúc khởi động đúng như thiết kế fail-fast: `ValueError: AGENT_API_KEY must be set in production!`. Khi cấp `AGENT_API_KEY=demo-key`, kết quả thực tế:
- `GET /health` → `200 {'status': 'ok', 'uptime_seconds': 0.1, 'version': '1.0.0', 'environment': 'production', ...}`
- `GET /ready` → `200 {'ready': True}`
- `POST /ask` (`{"question": "Hello"}`) → `200 {'question': 'Hello', 'answer': 'Đây là câu trả lời từ AI agent (mock)...', 'model': 'gpt-4o-mini'}`

### Exercise 1.3: Bảng so sánh Develop vs Production
| Feature | Develop (`develop/app.py`) | Production (`production/app.py` + `config.py`) | Tại sao quan trọng? |
| :--- | :--- | :--- | :--- |
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `port=8000` | Đọc qua `os.getenv(...)` trong `Settings`, có `validate()` fail-fast | Tuân thủ 12-Factor App; cùng một artifact chạy được mọi môi trường, không lộ secret lên Git. |
| **Health check** | Không có `/health`, `/ready` | Có `GET /health` (liveness) và `GET /ready` (readiness, trả 503 khi chưa sẵn sàng) | Giúp platform tự restart container lỗi và load balancer ngừng route traffic tới instance chưa sẵn sàng. |
| **Logging** | `print("[DEBUG] ...")`, lộ cả `OPENAI_API_KEY` | Structured JSON logging (`{"time":..., "level":..., "msg":...}`), không log secret | Dễ index, lọc và cảnh báo trên hệ thống log tập trung (Loki, Datadog, Cloud Logging). |
| **Shutdown** | Ngắt tiến trình đột ngột, không có lifecycle hook | `lifespan` (set `is_ready = False`, đợi in-flight) + bắt `SIGTERM` | Tránh cắt ngang request của khách hàng đang xử lý khi deploy rolling update hoặc scale down. |
| **Network binding** | `host="localhost"`, `reload=True` | `host="0.0.0.0"`, `reload=settings.debug` (False ở prod) | Container chỉ nhận được traffic từ bên ngoài khi lắng nghe `0.0.0.0`; tắt reload để ổn định và tiết kiệm CPU/RAM. |

---

## Part 2: Docker & Containerization

### Exercise 2.1: Phân tích `02-docker/develop/Dockerfile`
1. **Base image:** `python:3.11` (chứa Debian OS đầy đủ + bộ cài Python 3.11 và build tools, dung lượng gốc lớn ~1 GB; bản production đổi sang `python:3.11-slim`).
2. **Working directory:** `WORKDIR /app` — đặt thư mục làm việc mặc định trong container là `/app`, giúp các lệnh `COPY`, `RUN`, `CMD` phía sau hoạt động gọn trong `/app`.
3. **Tại sao `COPY 02-docker/develop/requirements.txt .` phải đứng trước `COPY 02-docker/develop/app.py .`?** Vì Docker build theo từng layer có cache. `requirements.txt` ít thay đổi hơn code trong `app.py`; đặt trước giúp Docker tái sử dụng layer cache của bước `RUN pip install`, không phải tải và cài lại toàn bộ thư viện mỗi lần chỉ sửa code Python.
4. **CMD vs ENTRYPOINT:** `ENTRYPOINT` cố định file thực thi chính khi container khởi chạy (khó bị ghi đè vô tình); `CMD` định nghĩa lệnh/tham số mặc định và có thể bị ghi đè dễ dàng khi truyền tham số vào cuối lệnh `docker run`.

### Exercise 2.2 & 2.3: Phân tích Multi-stage build (`02-docker/production/Dockerfile`)
- **Stage 1 (`builder` từ `python:3.11-slim`):** Cài compiler (`gcc`, `libpq-dev`) và chạy `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`. Image trung gian này chứa công cụ build nhưng không được đưa vào sản phẩm cuối.
- **Stage 2 (`runtime` từ `python:3.11-slim`):** Chỉ `COPY --from=builder /root/.local /home/appuser/.local`, copy code cần thiết, tạo user non-root `appuser`, khai báo `HEALTHCHECK` và `CMD ["uvicorn", ...]`. Nhờ loại bỏ `gcc`/`apt` cache và dùng base `slim`, dung lượng image giảm mạnh so với `python:3.11` full và thu hẹp bề mặt tấn công.

**Kết quả build & chạy thực tế (`docker build` từ repo root & `docker images my-agent`):**
| Image | Base / Cách build | User chạy | Kích thước thực tế (`docker images`) | Ghi chú test thực tế |
|---|---|---|---|---|
| `my-agent:develop` | Single-stage `python:3.11` | `root` | **`1.67GB`** (`1,667,792,001 bytes`) | `GET /health` → `200`, `POST /ask?question=Hello` → `200` |
| `my-agent:advanced` | Multi-stage `python:3.11-slim` | `appuser` | **`240MB`** (`239,811,353 bytes`) | Giảm **85.6%** (~1.43 GB); chạy non-root |

**Kết quả chạy thực tế Docker Compose `02-docker/production/` (`docker compose -p k5-day14-part2 up -d --build`):**
- Cả 4 container (`agent-1`, `nginx-1` `nginx:alpine`, `redis-1` `redis:7-alpine`, `qdrant-1` `qdrant/qdrant:v1.9.0`) khởi động và lên `healthy`.
- Gọi qua Nginx cổng `80`:
  - `GET http://localhost:80/health` → `200 {"status":"ok","uptime_seconds":3.6,"version":"2.0.0","timestamp":"2026-11-26T11:23:15.338201"}`
  - `POST http://localhost:80/ask` (`{"question":"Docker multi-stage la gi?"}`) → `200 {"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}`
- Đã dọn stack sạch bằng `docker compose -p k5-day14-part2 down -v`.

### Exercise 2.4: Sơ đồ kiến trúc Stack trong `02-docker/production/docker-compose.yml`
```text
Client ──▶ Nginx (:80, rate limit 10r/s burst 20)
                │
                ▼ (proxy_pass http://agent_backend -> agent:8000)
           Agent Service (:8000, non-root runtime)
             ├──▶ Redis (:6379, session cache & rate limit)
             └──▶ Qdrant (:6333, vector database cho RAG)
```
Trong `02-docker/production/nginx/nginx.conf`, Nginx chặn rate limit ở cổng 80 (`429` JSON), bỏ qua rate limit cho `/health`, và giấu port `8000` của `agent` trong mạng Docker `internal`.

---

## Part 3: Cloud Deployment

### Exercise 3.1 & 3.2: Trạng thái Deploy & So sánh `railway.toml` vs `render.yaml`
- **Trạng thái deploy:** Đã hoàn thiện cấu hình `06-lab-complete/railway.toml` và `06-lab-complete/render.yaml` đọc `$PORT`, `/health`, và biến môi trường không hardcode secret; tuy nhiên **chưa tạo service thực tế trên Railway/Render nên chưa có URL public hoạt động** (xem thêm [DEPLOYMENT.md](DEPLOYMENT.md)).
- **So sánh `06-lab-complete/railway.toml` với `06-lab-complete/render.yaml`:**
  - **`railway.toml`:** Khai báo ngắn gọn theo khối TOML (`[build] builder = "DOCKERFILE"`, `[deploy] healthcheckPath = "/health"`, `restartPolicyType = "ON_FAILURE"`). Railway tự cấp `$PORT` qua env, còn các biến nhạy cảm (`AGENT_API_KEY`, `REDIS_URL`) và addon Redis được cấu hình trực tiếp trên Dashboard hoặc Railway CLI chứ không khai báo trong `railway.toml`.
  - **`render.yaml`:** Dùng chuẩn Blueprint (Infrastructure as Code) dạng YAML khai báo cả kiến trúc service (`type: web`, `runtime: docker`, `plan: free`, `healthCheckPath: /health`) lẫn danh sách `envVars` ngay trong repo. Điểm khác biệt quan trọng là `render.yaml` kiểm soát cách xử lý secret ngay trong file cấu hình bằng `generateValue: true` (cho `AGENT_API_KEY` để Render tự sinh key ngẫu nhiên) hoặc `sync: false` (cho `REDIS_URL` để nhập tay lúc deploy, tuyệt đối không ghi plain secret).

### Exercise 3.3: Mô tả Pipeline CI/CD GCP Cloud Run (`03-cloud-deployment/production-cloud-run/`)
Đọc từ `cloudbuild.yaml` và `service.yaml`, pipeline đi qua **4 bước tuần tự**:
1. **`test`:** Chạy trên container `python:3.11-slim`, cài `requirements.txt` + `pytest` và chạy `pytest tests/ -v --tb=short` — chỉ khi pass hết mới sang bước tiếp theo (`waitFor: [test]`).
2. **`build`:** Dùng `gcr.io/cloud-builders/docker` build image gắn tag `gcr.io/$PROJECT_ID/ai-agent:$COMMIT_SHA` và `:latest` (tận dụng `--cache-from`).
3. **`push`:** Đẩy cả 2 tag lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy`:** Dùng `gcloud run deploy ai-agent` triển khai revision mới lên Cloud Run (`asia-southeast1`, `min-instances=1`, `max-instances=10`, `512Mi`/`1 CPU`) và nạp secret từ Google Secret Manager (`--set-secrets=OPENAI_API_KEY=openai-key:latest`). File `service.yaml` bổ sung đặc tả Knative Service (IaC) với `containerConcurrency: 80`, `livenessProbe` (`/health`), `startupProbe` (`/ready`) và `secretKeyRef` cho `OPENAI_API_KEY` & `AGENT_API_KEY`.

---

## Part 4: API Security

### Exercise 4.1: Kết quả chạy thực tế `04-api-gateway/develop/app.py` (API Key Auth)
Chạy với `AGENT_API_KEY=secret-key-123`:

1. **Không gửi API key (`401 Unauthorized`):**
```text
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```
2. **Gửi đúng `X-API-Key: secret-key-123` (`200 OK`):**
```text
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2 & 4.3: Kết quả chạy thực tế `04-api-gateway/production/app.py` (JWT + Rate Limit)
1. **Lấy JWT token từ `POST /auth/token` với `{"username": "student", "password": "demo123"}`:**
   Trả về `HTTP 200` với `access_token` (đã che: `eyJhbGciOiJIUzI1NiIsInR5...<REDACTED>`), hết hạn sau 60 phút, role `user` (giới hạn 10 req/phút).
2. **Gọi `/ask` không kèm token (`401 Unauthorized`):**
```text
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```
3. **Gọi `/ask` kèm `Authorization: Bearer <REDACTED>` (`200 OK`):**
```text
HTTP/1.1 200 OK
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY

{"question":"What is Docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
```
4. **Gửi burst liên tiếp vượt quá 10 request/phút (`429 Too Many Requests` ở request thứ 10 sau 1 request trước đó):**
```text
req 1..9: HTTP 200
req 10: HTTP 429
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795685257
retry-after: 59
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cơ chế Cost Guard
- **Trong `04-api-gateway/production/cost_guard.py`:** Dùng `CostGuard` tính tiền theo số token vào/ra (`PRICE_PER_1K_INPUT_TOKENS = 0.00015`, `PRICE_PER_1K_OUTPUT_TOKENS = 0.0006`). Trước khi gọi LLM sẽ gọi `check_budget(username)`: vượt ngân sách cá nhân (`$1.0/ngày`) trả **HTTP 402 Payment Required**, vượt ngân sách toàn hệ thống (`$10.0/ngày`) trả **503**, chạm 80% ghi log warning; sau khi LLM trả lời gọi `record_usage(...)` để cộng dồn.
- **Cách cải tiến sang Redis ở `06-lab-complete/app/cost_guard.py`:** Đưa tổng chi phí vào key `total_llm_cost` trên Redis dùng `client.incrbyfloat("total_llm_cost", cost)` để nhiều worker/instance dùng chung ngân sách chính xác, không bị reset khi restart. Rate limit chặn spam theo tốc độ (req/phút), còn Cost Guard chặn thiệt hại tài chính theo token tiêu thụ thực tế.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 – 5.5: Health Check, Graceful Shutdown & Stateless Design
1. **Liveness vs Readiness (`05-scaling-reliability/develop/app.py`):**
   - `GET /health` kiểm tra tiến trình & bộ nhớ (`psutil`), giúp platform biết container còn sống hay bị treo.
   - `GET /ready` kiểm tra cờ `_is_ready` (trả `503` khi đang khởi động/shutdown hoặc mất dependency) để load balancer chỉ gửi traffic tới instance sẵn sàng.
   - **Kết quả chạy thực tế `05-scaling-reliability/develop/app.py`:**
     - `GET /health` → `{"status":"ok","uptime_seconds":0.8,"version":"1.0.0","environment":"development","checks":{"memory":{"status":"ok","used_percent":89.1}}}`
     - `GET /ready` → `{"ready":true,"in_flight_requests":1}`
2. **Graceful Shutdown:** Khi nhận `SIGTERM`, `lifespan` chuyển `_is_ready = False` để ngừng nhận traffic mới và đợi `_in_flight_requests` về `0` (tối đa 30s với `timeout_graceful_shutdown=30`) trước khi thoát, không cắt ngang request đang xử lý.
3. **Stateless với Redis (`05-scaling-reliability/production/app.py` & `test_stateless.py`):**
   - Nếu lưu session trong RAM (`_memory_store`), khi scale 3 instance sau Nginx load balancer (`round-robin`), request 1 vào `instance-A` nhưng request 2 vào `instance-B` sẽ mất toàn bộ lịch sử hội thoại.
   - Bản production lưu lịch sử hội thoại vào Redis (`_redis.setex(f"session:{session_id}", 3600, ...)`), mỗi response gắn `served_by: INSTANCE_ID` để `test_stateless.py` gửi 5 câu tới `POST http://localhost:8080/chat` và đọc lại `GET /chat/{session_id}/history` đầy đủ dù đi qua các instance khác nhau.
   - **Kết quả chạy thực tế `docker compose -p k5-day14-scaling up -d --build --scale agent=3` + `python test_stateless.py`:**
     - Cả 5 container (`k5-day14-scaling-agent-1`, `agent-2`, `agent-3`, `redis-1`, `nginx-1`) lên trạng thái `healthy` / `Up`. `GET http://localhost:8080/health` → `{"status":"ok","instance_id":"instance-ad86f7","uptime_seconds":4.3,"storage":"redis","redis_connected":true}`.
     - Output thực tế từ `test_stateless.py` (`Session ID: 93c83a57-9708-4fdb-9d49-5b6d48419f8c`):
```text
Request 1: [instance-268873]  Q: What is Docker?
Request 2: [instance-923b58]  Q: Why do we need containers?
Request 3: [instance-ad86f7]  Q: What is Kubernetes?
Request 4: [instance-268873]  Q: How does load balancing work?
Request 5: [instance-923b58]  Q: What is Redis used for?

Total requests: 5
Instances used: {'instance-268873', 'instance-923b58', 'instance-ad86f7'}
✅ All requests served despite different instances!
Total messages: 10
✅ Session history preserved across all instances via Redis!
```
     - Đã dọn stack sạch bằng `docker compose -p k5-day14-scaling down -v`.

---

## Part 6: Final Project Verification (`06-lab-complete/`)

Output thực tế khi chạy đầy đủ `python3 check_production_ready.py` (không dùng `--skip-docker` / `--static-only`) bên trong WSL2 (`Day14Lab`, `os.name=posix`, tích hợp Docker Engine `29.9.3` với data dir trên `D:\Docker\data` và Redis cục bộ trên cổng `6379`):

```text
🔎 Kiểm tra /mnt/d/learning/vin_uni/day_14_deployment_benchmark_observability/06-lab-complete
  ⏳ Kiểm tra tĩnh: file, Dockerfile, compose, config, code...
  ⏳ Chuẩn bị Redis cho bài test stateless...
  ⏳ Khởi động agent: uvicorn app.main:app --workers 2 (Redis: redis-server tạm thời)
  ⏳ Restart agent để kiểm tra stateless...
  ⏳ Kiểm tra readiness khi Redis mất kết nối...
  ⏳ Kiểm tra cost guard (budget ≈ 0)...
  ⏳ Kiểm tra graceful shutdown (SIGTERM)...
  ⏳ Build Docker image prod-check:8731b3ee (Docker 29.9.3)

================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)         [build 47s, 238 MB, non-root, /health 200]
     ✅ docker-compose.yml (agent + redis)          [agent + redis via docker compose config]
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)         [uvicorn --workers 2 -> 200]
     ✅ Readiness endpoint (GET /ready)             [200 OK; mất Redis -> 503, /health vẫn 200]
     ✅ API Key authentication                      [thiếu/sai key -> 401; đúng -> 200]
     ✅ Rate limiting                               [429 sau 5 request; restart vẫn giữ state Redis]
     ✅ Cost guard                                  [budget ~ 0 -> 402 ở request thứ 1]
     ✅ Config từ environment variables             [AGENT_API_KEY & RATE_LIMIT_PER_MINUTE từ env]
     ✅ Structured logging                          [12 dòng JSON hợp lệ]
     ✅ Graceful shutdown                           [SIGTERM đang request -> 200, exit 0; docker stop 1.1s]
     ✅ Public URL ready (Railway / Render config)  [railway.toml & render.yaml hợp lệ]
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log

* **Công cụ sử dụng:** Trợ lý AI trong IDE (hỗ trợ phân tích code, debug Docker/WSL2 và chạy kiểm thử tự động).
* **Nội dung hỏi & nhận:**
  * Phân tích cấu trúc `check_production_ready.py` và bảng hợp đồng `06-lab-complete/README.md` để hoàn thiện `auth.py`, `rate_limiter.py` (Redis sorted set + UUID member tránh trùng key), `cost_guard.py`, `redis_client.py` (cache `ConnectionPool` + timeout ngắn), `main.py` (`/health`, `/ready`, JSON logging, `lifespan`, exception handler), `Dockerfile` multi-stage.
  * Cấu hình Docker Desktop WSL2 backend chuyển dữ liệu (`docker_data.vhdx`) sang `D:\Docker\data` tránh tràn ổ `C:\`, dựng distro WSL2 `Day14Lab` trên `D:\WSL\Day14Lab` để chạy `check_production_ready.py` đầy đủ trên Linux (`os.name=posix` + Docker 29.9.3), và tìm/sửa lỗi `PYTHONUSERBASE=/home/agent/.local` + `--chown=agent:agent` trong `06-lab-complete/benchmark-observability/production/Dockerfile`.
  * Chạy toàn bộ thực nghiệm Part 1, 2, 4, 5, 6, 7 (`load_test.py`, `run_eval.py`, `promtool`, Locust `scale_1` & `scale_3`, chaos A–E, thu thập Grafana/Prometheus/Jaeger UI & JSON logs).
* **Tự kiểm tra & sửa lỗi:** Tự đối chiếu toàn bộ số liệu và mô tả theo `RUBRIC.md`, `RULES.md` và `CHECKPOINTS.md`: xóa các ảnh placeholder cũ, giữ lại 100% số đo thật từ `docker images`, `test_stateless.py`, `check_production_ready.py` (`43/43` passes), CSV Locust (`scale_1_stats.csv`, `scale_3_stats.csv`), Prometheus firing alerts và 4 ảnh chụp thật từ Grafana/Prometheus/Jaeger trong `screenshots/`. Ghi rõ Part 3 (Public URL cloud) chưa deploy thực tế lên Railway/Render.
