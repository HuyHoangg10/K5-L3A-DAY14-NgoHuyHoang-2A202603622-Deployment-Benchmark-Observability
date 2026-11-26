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
- *(Ghi chú trung thực: Máy Windows hiện tại chưa bật được WSL2/cài Docker Desktop nên chưa đo trực tiếp số MB bằng `docker images` và chưa chạy stack Nginx ở 2.4; phần phân tích dựa trên Dockerfile và `docker-compose.yml` thực tế trong repo.)*

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
   - *(Ghi chú trung thực: chưa chạy lệnh `docker compose -p k5-day14-scaling up -d --build --scale agent=3` vì máy chưa có Docker Desktop.)*

---

## Part 6: Final Project Verification (`06-lab-complete/`)

Output thực tế khi chạy `python check_production_ready.py --skip-docker --redis-url redis://127.0.0.1:6399/0` trên Windows cùng Redis cục bộ (sau khi sửa rò rỉ connection pool Redis, race condition `rate_limiter.py`, exception handler và `Dockerfile`):

```text
================================================================
  📋 Checklist Deliverable
     ⚠️  Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ⚠️  Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 10/12 tiêu chí đạt · 38/38 checks passed
  ⚠️  Chưa kiểm tra được: Dockerfile (multi-stage, < 500 MB), Graceful shutdown
  ℹ️  Đang chạy chế độ nhanh — kết quả chấm phải chạy đầy đủ (không --static-only / --skip-docker)
  ❌ CHƯA ĐẠT — còn tiêu chí chưa kiểm tra được (⚠️). Chạy đầy đủ trên máy có Docker.
================================================================
```

*(Ghi chú: Toàn bộ 38/38 check chạy được trên Windows đều PASS; 2 mục ⚠️ còn lại là phần build/run Docker image và gửi `SIGTERM` POSIX trên Windows chưa có WSL2/Docker.)*

---

## AI Log

* **Công cụ sử dụng:** Trợ lý AI trong IDE (Gemini / Claude qua các phiên làm việc).
* **Nội dung hỏi & nhận:**
  * Phân tích cấu trúc `check_production_ready.py` và bảng hợp đồng `06-lab-complete/README.md` để hoàn thiện `auth.py`, `rate_limiter.py` (Redis sorted set + UUID member tránh trùng key), `cost_guard.py`, `redis_client.py` (cache `ConnectionPool` + timeout ngắn), `main.py` (`/health`, `/ready`, JSON logging, `lifespan`, exception handler), `Dockerfile` multi-stage.
  * Hỗ trợ viết script tự động chạy lại các bài thực hành local (Part 1, Part 4, Part 5 develop, Part 7 `load_test.py`, `run_eval.py`, và chạy trực tiếp `benchmark-observability/production/app/main.py` bằng Python để thu thập `/metrics` và OTel trace thật).
* **Tự kiểm tra & sửa lỗi:** Tự đối chiếu lại toàn bộ code và báo cáo theo `RUBRIC.md` và `RULES.md`: loại bỏ các ảnh placeholder/số đo ước lượng cũ chưa chạy Docker, sửa lại các mô tả `cloudbuild.yaml`, `alert_rules.yml`, tên span OTel cho khớp 100% với mã nguồn thực tế, và chạy lại `check_production_ready.py --skip-docker` (38/38 checks passed) cùng `TestClient` cho tất cả edge cases (`401`, `422`, `503`).
