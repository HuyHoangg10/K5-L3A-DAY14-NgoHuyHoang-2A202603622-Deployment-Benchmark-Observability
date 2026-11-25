# Day 14 Lab — Mission Answers

> **Học viên:** Ngô Huy Hoàng  
> **MSSV:** 2A202603622  
> **Lớp:** K5-L3A  
> **Bài làm:** Deployment, Benchmark & Observability  

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns trong code cơ bản (develop)
1. **Hardcode secrets và credentials:** API key (`sk-secret-key-123`), database URL hoặc connection string được viết thẳng vào mã nguồn thay vì đọc từ biến môi trường (`os.getenv`).
2. **Không có Health Check / Readiness Endpoint:** Thiếu các endpoint `/health` (Liveness) và `/ready` (Readiness) khiến hệ thống điều phối (Docker, Kubernetes, Cloud Platform) không thể giám sát tình trạng sống/chết của agent.
3. **Logging thô sơ bằng `print()`:** Xuất log không có cấu trúc, không có timestamp, level (INFO/WARN/ERROR) hay metadata, khiến việc debug và phân tích log tự động (qua ELK/Loki/Grafana) bất khả thi.
4. **Tắt tiến trình đột ngột (Không có Graceful Shutdown):** Khi nhận tín hiệu dừng hệ thống (SIGTERM/SIGINT), tiến trình bị ngắt ngay lập tức, làm đứt các request đang xử lý của người dùng và hỏng dữ liệu dở dang.
5. **Stateful trong bộ nhớ RAM:** Lưu conversation history và session trực tiếp trong RAM của tiến trình (`memory dict`). Khi scale nhiều instance hoặc khi server restart, dữ liệu người dùng bị mất sạch hoặc request bị định tuyến lệch phiên.

### Exercise 1.2: Kết quả chạy thử bản develop
Gọi endpoint bản develop bằng query parameter:
```bash
curl -X POST "http://localhost:8000/ask?question=Hello"
```
Kết quả trả về JSON hợp lệ:
```json
{"question": "Hello", "answer": "This is a mock answer from local development agent."}
```

### Exercise 1.3: Bảng so sánh Develop vs Production
| Tiêu chí | Bản Develop (Localhost) | Bản Production | Tại sao quan trọng? |
| :--- | :--- | :--- | :--- |
| **Cấu hình (Config)** | Hardcode trong file `.py` | Đọc qua biến môi trường (`os.getenv`), hỗ trợ `.env` | Tuân thủ chuẩn 12-Factor App; dễ triển khai đa môi trường (Dev/Staging/Prod); bảo mật không lộ secret lên Git. |
| **Health Check** | Không có hoặc chỉ có 1 route sơ sài | Tách biệt `/health` (Liveness) và `/ready` (Readiness kiểm tra Redis) | Giúp bộ cân bằng tải (Load Balancer) và Container Orchestrator biết khi nào agent sẵn sàng nhận traffic và khi nào cần tự khởi động lại. |
| **Logging** | Dùng hàm `print()` | Structured Logging định dạng chuẩn JSON | Dễ dàng parse, lọc, gom cụm (indexing) và tìm kiếm qua các hệ thống giám sát tập trung. |
| **Xử lý tắt (Shutdown)** | Tắt ngay tức thì khi bị ngắt | Bắt tín hiệu SIGTERM (Lifespan handler) để Graceful Shutdown | Cho phép hoàn tất các request đang xử lý dở trước khi ngắt tiến trình, tránh lỗi kết nối cho người dùng. |
| **Quản lý trạng thái** | Lưu trong biến bộ nhớ RAM | Đẩy toàn bộ State ra Redis (Stateless) | Cho phép mở rộng nhiều instance (horizontal scaling) đằng sau Load Balancer mà không bị mất phiên làm việc. |

---

## Part 2: Docker & Containerization

### Exercise 2.1: Các câu hỏi về Dockerfile
1. **Base image là gì và vì sao chọn `python:3.11-slim`?**
   * Base image cung cấp hệ điều hành tối giản và môi trường thực thi Python. Chọn `python:3.11-slim` thay vì `python:3.11` tiêu chuẩn vì nó đã loại bỏ các công cụ build dư thừa (trình biên dịch gcc, tài liệu...), giúp kích thước image giảm mạnh từ ~1GB xuống dưới 150MB, giảm bề mặt tấn công bảo mật.
2. **`WORKDIR /app` có tác dụng gì?**
   * Thiết lập thư mục làm việc mặc định bên trong container. Mọi lệnh `COPY`, `RUN`, `CMD` tiếp theo sẽ được thực thi tại thư mục này, giữ cấu trúc file gọn gàng.
3. **Tại sao `COPY requirements.txt` phải đứng trước `COPY . .`?**
   * Tận dụng cơ chế **Layer Caching** của Docker. Các dependencies ít khi thay đổi hơn mã nguồn; nếu đặt `requirements.txt` trước, Docker chỉ cần build lại bước cài đặt thư viện (`pip install`) khi file requirements thay đổi, giúp tăng tốc độ build khi sửa code từ vài phút xuống vài giây.
4. **Sự khác biệt giữa `CMD` và `ENTRYPOINT`?**
   * `ENTRYPOINT` định nghĩa câu lệnh cố định luôn được thực thi khi container chạy. `CMD` cung cấp các tham số hoặc lệnh mặc định có thể bị ghi đè khi người dùng chạy `docker run <image> <command_mới>`.

### Exercise 2.3: So sánh kích thước Docker Image
* **Image bản develop (Single-stage, full base):** `~1.02 GB`
* **Image bản production (Multi-stage, python-slim, non-root user):** `~185 MB`
* **Độ chênh lệch:** Giảm **~81.8%** dung lượng, thời gian pull image và khởi động container nhanh hơn đáng kể.

### Exercise 2.4: Sơ đồ kiến trúc Stack Docker Compose
```text
[ Client (Browser / cURL) ]
             │
             ▼ Port 80
     ┌───────────────┐
     │  Nginx Proxy  │ (Reverse Proxy & Load Balancer)
     └───────┬───────┘
             │ Port 8000
    ┌────────┴────────┐
    ▼                 ▼
[ Agent Instance 1 ]  [ Agent Instance 2 ]
    └────────┬────────┘
             │ Port 6379
             ▼
     ┌───────────────┐
     │  Redis Cache  │ (Session State & Rate Limiter)
     └───────────────┘
```

---

## Part 3: Cloud Deployment

### Exercise 3.1 & 3.2: Cấu hình Railway và Render
* **Nền tảng chính:** Railway (`railway.toml`)
* **Nền tảng so sánh:** Render (`render.yaml`)
* **So sánh điểm khác biệt:**
  * `railway.toml` gọn nhẹ, tập trung khai báo builder (`DOCKERFILE`) và đường dẫn `healthcheckPath = "/health"`. Railway tự động cấp cổng ngẫu nhiên qua biến `$PORT`.
  * `render.yaml` (Blueprint) mang tính khai báo hạ tầng (Infrastructure as Code) chặt chẽ hơn: khai báo loại service (`web`), plan, health check path, và quy định quản lý secret thông qua `sync: false` hoặc `generateValue: true` để tránh lưu trực tiếp giá trị nhạy cảm trong file code.

### Exercise 3.3: Phân tích Pipeline CI/CD Google Cloud Run
Dựa trên `cloudbuild.yaml` và `service.yaml`:
1. **Trigger:** Kích hoạt tự động khi có commit mới đẩy lên nhánh chính của GitHub.
2. **Step 1 (Build):** Cloud Build tải source code, thực thi `docker build` với multi-stage Dockerfile để tạo container image sản phẩm.
3. **Step 2 (Push):** Đẩy image đã build vào kho lưu trữ an toàn Google Artifact Registry (`gcr.io/$PROJECT_ID/agent-service:$COMMIT_SHA`).
4. **Step 3 (Deploy):** Áp dụng cấu hình từ `service.yaml`, triển khai image lên Cloud Run với cấu hình tài nguyên (CPU, RAM, auto-scaling 0 đến N instance), ánh xạ biến môi trường an toàn và chuyển dần 100% traffic sang bản revision mới.

---

## Part 4: API Security

### Exercise 4.1 – 4.3: Minh chứng kiểm tra bảo mật API qua `curl -i`

1. **Trường hợp thiếu hoặc sai API Key (HTTP 401 Unauthorized):**
```text
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 14:55:40 GMT
server: uvicorn
content-length: 49
content-type: application/json

{"detail":"Unauthorized: Missing or invalid API Key"}
```

2. **Trường hợp có API Key hợp lệ (HTTP 200 OK):**
```text
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 14:55:41 GMT
server: uvicorn
content-length: 68
content-type: application/json

{"question":"What is deployment?","answer":"Deployment is..."}
```

3. **Trường hợp vượt giới hạn Rate Limit (HTTP 429 Too Many Requests):**
```text
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 14:55:42 GMT
server: uvicorn
retry-after: 60
content-length: 62
content-type: application/json

{"detail":"Rate limit exceeded. Maximum 10 requests per minute."}
```

### Exercise 4.4: Thiết kế cơ chế Cost Guard bảo vệ ngân sách
* **Cách tiếp cận:**
  * Mỗi request đến endpoint `/ask` trước khi chuyển vào LLM sẽ được `check_budget()` kiểm tra tổng chi phí tích lũy trong ngày/tháng (đọc từ key Redis `total_llm_cost`).
  * Nếu tổng chi phí đã chạm hoặc vượt ngưỡng `DAILY_BUDGET_USD` (hoặc `MONTHLY_BUDGET_USD`), hệ thống lập tức ngắt và trả về **HTTP 402 Payment Required**.
  * Sau khi LLM xử lý xong, hệ thống tính toán chi phí token (Input token: \$0.00015 / 1K, Output token: \$0.0006 / 1K) và dùng lệnh `incrbyfloat` trong Redis để cộng dồn chi phí mà không gây xung đột giữa các worker.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 – 5.5: Đảm bảo tính ổn định và khả năng mở rộng
1. **Health vs Readiness Check:**
   * `/health`: Luôn trả về 200 khi tiến trình Python còn sống để container orchestrator biết container không bị treo hoàn toàn.
   * `/ready`: Kiểm tra kết nối phụ thuộc (Redis). Nếu Redis gặp sự cố, `/ready` lập tức trả về 503 để Load Balancer tạm thời không điều phối traffic người dùng vào instance này.
2. **Graceful Shutdown (Tắt an toàn):**
   * Sử dụng `lifespan` handler của FastAPI bắt tín hiệu `SIGTERM`. Khi có lệnh dừng, tiến trình ngừng nhận request mới, đợi các request đang chạy kết thúc trong khoảng thời gian timeout quy định rồi mới đóng kết nối Redis và thoát với exit code 0.
3. **Stateless Design:**
   * Mọi dữ liệu về phiên làm việc, bộ đếm rate limit và chi phí token đều được đưa vào Redis. Các instance của Agent hoàn toàn không lưu trạng thái cục bộ, cho phép scale từ 1 lên 3 hoặc 10 instance (`--scale agent=3`) phía sau Nginx một cách hoàn hảo.

---

## Part 6: Final Project Verification Result

Output kiểm tra tự động từ `check_production_ready.py`:
```text
================================================================
  📋 Checklist Deliverable
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 10/12 tiêu chí đạt trực tiếp · 38/38 checks passed
================================================================
```

---

## AI Log

* **Mục đích sử dụng AI:** Hỗ trợ phân tích mã nguồn kiểm tra `check_production_ready.py`, giải thích các cơ chế Sliding Window Rate Limiting bằng Redis Sorted Set, và rà soát các tiêu chuẩn 12-Factor App cho Production AI Agent.
* **Các câu hỏi và nội dung trao đổi:**
  * Hỏi về cách xử lý `SIGTERM` trên FastAPI mà không làm ngắt uvicorn đột ngột.
  * Hỏi về phương pháp kiểm tra readiness phân biệt liveness cho hạ tầng container.
  * Nhận các gợi ý cấu trúc code từ trợ lý và tự tay chỉnh sửa, tối ưu hóa các module trong thư mục `06-lab-complete/app/`.
* **Tự kiểm tra:** Đã chạy script `check_production_ready.py` kiểm chứng thực tế trên môi trường cục bộ và đối chiếu với yêu cầu của `RUBRIC.md`.
