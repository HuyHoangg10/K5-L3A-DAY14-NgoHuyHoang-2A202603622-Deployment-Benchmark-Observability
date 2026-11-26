# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được trích xuất từ kết quả chạy thật các script trong `06-lab-complete/benchmark-observability/` (`develop/` và chạy trực tiếp `production/app/main.py` bằng Python). Các phần đòi hỏi Docker Compose full stack (Grafana UI, Jaeger UI, Prometheus server, Locust headless) được ghi rõ trạng thái chưa chạy và thay bằng kết quả chạy Python trực tiếp + phân tích PromQL theo hướng dẫn Partial Credit trong `INSTRUCTOR_GUIDE.md`.

**Họ tên:** Ngô Huy Hoàng  
**MSSV:** 2A202603622  
**Ngày chạy:** 25–26/11/2026  
**Môi trường:** Windows 11, SSD Lexar NVMe, Python 3.13.15 (`.venv`), FastAPI 0.115.0, Uvicorn 0.30.0 (chưa cài Docker Desktop / WSL2)  

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Bảo đảm 95% người dùng nhận câu trả lời mượt trong tác vụ hỏi đáp thời gian thực (ứng với ngưỡng `SLO_P95_MS=500` trong `load_test.py`). |
| Error rate `/ask` | `< 2.0 %` | Cho phép sai số nhỏ từ lỗi tạm thời (mock LLM có ~1% lỗi 503), giữ mức ổn định cao trước khi cảnh báo. |
| Accuracy trên golden dataset | `≥ 85.0 %` (mục tiêu sau sửa KB: `100%`) | Làm quality gate trong CI/CD để đảm bảo nâng cấp prompt/RAG không làm tụt chất lượng câu trả lời (không có regression). |

---

## 2. Benchmark hiệu năng (`develop/load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Số liệu thực tế từ `reports/load_v2_c1.json`, `load_v2_c10.json`, `load_v2_c50.json`, `load_v2_c100.json` (`--requests 300`):

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.23 | 196.7 | 229.4 | 1688.5 | 0.67% | ✅ PASS |
| 10 | 40.38 | 197.3 | 431.2 | 1705.2 | 1.33% | ✅ PASS |
| 50 | 98.26 | 203.1 | 502.8 | 1713.2 | 0.33% | ❌ FAIL (p95 > 500ms) |
| 100 | 38.24 | 1229.7 | 4775.1 | 5213.3 | 0.67% | ❌ FAIL (p95 > 500ms) |

**Nhận xét:**
* **RPS không tăng tuyến tính mãi theo concurrency.** Từ `c=1 → 10 → 50`, RPS tăng từ `4.23` lên `40.38` rồi đạt đỉnh `98.26 req/s` nhờ xử lý I/O bất đồng bộ (`async/await`). Nhưng khi tăng tiếp lên `c=100`, RPS **tụt mạnh còn `38.24 req/s`**, `p50` nhảy từ `203.1 ms` lên `1229.7 ms` và `p95` vọt lên `4775.1 ms`.
* **Nguyên nhân:** Quá ngưỡng bão hòa của 1 process Uvicorn (queueing delay, context switching và giới hạn socket/event loop đồng thời), khiến hàng loạt request phải xếp hàng chờ xử lý.

### 2.2 Tail latency (`--requests 300 --concurrency 20`)

Số liệu thực tế từ `reports/load_v2_slow_0.json`, `load_v2_slow_0.03.json`, `load_v2_slow_0.1.json`:

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| `0` | 213.8 | 442.3 | 485.7 |
| `0.03` (mặc định) | 269.4 | 526.6 | 1712.5 |
| `0.1` | 371.0 | 1712.7 | 1971.3 |

**Nhận xét:**
* **Chỉ số nhạy nhất với request chậm là `p99` và `p95`:**
  * Khi `MOCK_SLOW_RATE = 0.03` (3% request bị chậm), `avg` chỉ tăng nhẹ từ `213.8 ms` → `269.4 ms` (+55.6 ms), nhưng `p99` nhảy vọt từ `485.7 ms` lên **`1712.5 ms`** (+1226.8 ms).
  * Khi `MOCK_SLOW_RATE = 0.1` (10% request chậm > 5%), `avg` mới tăng lên `371.0 ms` (vẫn dưới 500 ms), nhưng **cả `p95` cũng vọt lên `1712.7 ms`**.
* **Vì sao không đặt SLO theo average:** Giá trị trung bình bị 90–97% request nhanh kéo xuống nên che giấu hoàn toàn trải nghiệm tệ của nhóm người dùng gặp tail latency.

---

## 3. Benchmark chất lượng (`develop/eval/run_eval.py`)

Số liệu thực tế từ `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json` (23 câu hỏi trong `eval/golden_dataset.jsonl`):

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | **4.3%** (1/23) | **91.3%** (21/23) | **100.0%** (23/23) |
| Avg tokens / câu | 57.2 | 108.7 | 113.5 |
| Tổng cost (USD) | $0.000406 | $0.000756 | $0.000789 |
| Cost / câu đúng (USD) | $0.00040575 | $0.00003599 | **$0.00003430** |
| Quality gate | ❌ FAIL | ✅ PASS | ✅ **PASS (0 regression)** |

**Những câu v2 trả lời sai ban đầu và cách sửa (`utils/mock_llm.py`):**

| ID | Keyword bị thiếu | Đã sửa trong `KNOWLEDGE_BASE` |
|---|---|---|
| `security-02` | `["token", "hết hạn", "chữ ký"]` | Thêm entry `(["jwt", "token", "xác thực"], ...)` mô tả JWT tự chứa thông tin, có thời gian hết hạn và chữ ký số. |
| `scaling-03` | `["cpu", "memory", "custom metrics"]` | Thêm entry `(["hpa", "kubernetes", "scale"], ...)` mô tả Kubernetes HPA tự scale theo CPU, memory và custom metrics. |

**Nhận xét trade-off chất lượng / chi phí / latency giữa v1 và v2:**
* **Chất lượng:** v1 không có bước retrieval (RAG) nên chỉ đạt `4.3%` (1/23); v2 có retrieval đạt `91.3%` và `100.0%` (23/23) sau khi bổ sung 2 mục thiếu vào `KNOWLEDGE_BASE`.
* **Chi phí:** v2 dùng trung bình `113.5` tokens/câu (~gấp 2 lần v1 là `57.2` tokens) do chèn context vào prompt, nhưng **chi phí trên mỗi câu trả lời đúng (`cost / câu đúng`) của v2 rẻ hơn gần 12 lần** (`$0.00003430` so với `$0.00040575`).
* **Latency:** v2 chậm hơn v1 ở `p50` khoảng ~30 ms (`201.9 ms` vs `165.2 ms`) do tốn thêm bước `search_knowledge_base`, hoàn toàn chấp nhận được để đổi lấy độ chính xác 100%.

**Quality Gate trong CI/CD (kiểm chứng thực tế với `eval/run_eval.py`):**
Khi chạy thử đánh giá lại `v1` với `--baseline reports/eval_v2_fixed.json --min-accuracy 0.85`, script báo `22` câu bị regression, `Quality gate: ❌ FAIL` và trả về **`exit code = 1`**. Trong GitHub Actions, một job CI dùng bước này sẽ tự động chặn merge PR khi model/prompt mới bị tụt accuracy hoặc gây regression:

```yaml
jobs:
  eval-quality-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: |
          cd 06-lab-complete/benchmark-observability/develop
          pip install -r requirements.txt
          AGENT_VERSION=v2 MOCK_ERROR_RATE=0 PORT=8002 python app.py &
          sleep 3
          python eval/run_eval.py --url http://localhost:8002 \
            --baseline reports/eval_v2_fixed.json \
            --min-accuracy 1.0
```

---

## 4. Observability (Chạy trực tiếp `production/app/main.py` + Phân tích PromQL & Alerts)

> **Lưu ý trung thực (Partial Credit theo `INSTRUCTOR_GUIDE.md`):** Do máy Windows chưa cài Docker Desktop nên chưa bật được stack Docker Compose gồm Grafana UI, Jaeger UI, Prometheus server và Locust để chụp ảnh màn hình. Thay vào đó, tôi đã **chạy trực tiếp `06-lab-complete/benchmark-observability/production/app/main.py` bằng Python** (với `AGENT_VERSION=v2`, `MOCK_SLOW_RATE=0.25`, `MOCK_ERROR_RATE=0.2`, gắn `InMemorySpanExporter` của OpenTelemetry), gửi 20 requests `/ask` và thu thập toàn bộ output `/metrics`, span trace và JSON logs thật dưới đây.

### 4.1 Kết quả thật từ `GET /metrics` (20 requests tới `production/app/main.py`)

```text
http_requests_total{method="POST",route="/ask",status="503"} 4.0
http_requests_total{method="POST",route="/ask",status="200"} 16.0
http_request_duration_seconds_bucket{le="0.2",method="POST",route="/ask"} 4.0
http_request_duration_seconds_bucket{le="0.3",method="POST",route="/ask"} 9.0
http_request_duration_seconds_bucket{le="1.5",method="POST",route="/ask"} 12.0
http_request_duration_seconds_bucket{le="2.0",method="POST",route="/ask"} 20.0
http_request_duration_seconds_count{method="POST",route="/ask"} 20.0
http_request_duration_seconds_sum{method="POST",route="/ask"} 18.094791200001055
agent_in_flight_requests 0.0
llm_requests_total{model="mock-llm-small",status="error"} 4.0
llm_requests_total{model="mock-llm-small",status="ok"} 16.0
llm_tokens_total{model="mock-llm-small",type="input"} 1368.0
llm_tokens_total{model="mock-llm-small",type="output"} 808.0
llm_cost_usd_total{model="mock-llm-small"} 0.0006899999999999999
agent_retrieval_total{result="hit"} 20.0
agent_info{model="mock-llm-small",version="v2"} 1.0
```

**Trả lời Exercise 7.4 (dựa trên `/metrics`, Grafana dashboard & `nginx.conf`):**
1. **Khoảng cách giữa `avg` và `p95` trên panel Latency:** Trên Prometheus, `avg` tính bằng `rate(http_request_duration_seconds_sum[1m]) / rate(http_request_duration_seconds_count[1m])`, còn `p95` tính từ histogram buckets bằng `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job="agent", route="/ask"}[1m])))`. Khi có request chậm (~1.7s), `avg` bị số đông request ~200ms kéo xuống nên tăng rất ít, còn `p95` bám theo nhóm đuôi chậm nên tách xa khỏi `avg`.
2. **Vì sao `input_tokens` (`1368`) luôn lớn hơn `output_tokens` (`808`):** Ở agent `v2`, bước RAG chèn thêm tài liệu truy xuất từ `KNOWLEDGE_BASE` (context) vào prompt gửi cho LLM, khiến số lượng input token đầu vào lớn hơn hẳn câu trả lời đầu ra.
3. **Vì sao `/metrics` bị chặn (`404`) ở `nginx/nginx.conf` (dòng 22–24):** `location = /metrics { return 404; }` ngăn người dùng bên ngoài Internet truy cập `/metrics` vì metric làm lộ lưu lượng, các endpoint nội bộ, tỷ lệ lỗi và chi phí hệ thống. Prometheus vẫn scrape bình thường vì nằm cùng mạng Docker nội bộ và gọi thẳng container `agent:8000/metrics`.

### 4.2 Phân tích 4 Alert Rules trong `prometheus/alert_rules.yml` & Thí nghiệm "phá hệ thống"

Các rule định nghĩa thật trong `06-lab-complete/benchmark-observability/production/prometheus/alert_rules.yml`:
- `AgentHighErrorRate`: `error_rate > 0.05` (`5%`), `for: 1m` (`severity: critical`)
- `AgentHighLatencyP95`: `histogram_quantile(0.95, ...) > 1` (`1s`), `for: 2m` (`severity: warning`)
- `AgentInstanceDown`: `up{job="agent"} == 0`, `for: 30s` (`severity: critical`)
- `LLMCostBurnRateHigh`: `sum(rate(llm_cost_usd_total{job="agent"}[5m])) * 3600 > 2` (`$2/giờ`), `for: 2m` (`severity: warning`)

Phân tích cơ chế từng thí nghiệm (A–E):
- **A (`MOCK_ERROR_RATE=0.2`):** Tỷ lệ status `503` đạt ~20% (> 5%), nên `AgentHighErrorRate` sẽ chuyển `pending` → `firing` sau cửa sổ `for: 1m`.
- **B (`MOCK_SLOW_RATE=0.3`):** `p95` vượt 1s liên tục, kích hoạt `AgentHighLatencyP95` sau `for: 2m`.
- **C (`LLM_MODEL=mock-llm-large`):** Chi phí mỗi token cao hơn nhiều lần làm burn rate tăng, kích hoạt `LLMCostBurnRateHigh` sau `for: 2m` (nếu vượt $2/giờ).
- **D (`docker pause` 1 instance):** Khác với `docker stop` (xóa container khỏi Docker DNS khiến Prometheus bỏ target), `docker pause` giữ container trong DNS nhưng không phản hồi scrape `/metrics` → `up == 0`, kích hoạt `AgentInstanceDown` sau `for: 30s`. Đồng thời, các request dính vào instance bị pause sẽ bị **Nginx cắt bằng lỗi `504 Gateway Timeout`** sau `proxy_read_timeout 10s` — lỗi 504 này xảy ra ở Nginx trước khi agent phản hồi nên **không hiện trên metric của agent**, cần giám sát thêm tầng load balancer/synthetic check.
- **E (`AGENT_VERSION=v1`):** **Không có alert hạ tầng nào firing**, vì `v1` vẫn trả HTTP `200` rất nhanh (`~170ms`), không gây 5xx hay tốn nhiều chi phí. **Cách phát hiện trong production:** Chạy synthetic eval định kỳ với golden dataset để phát hiện sụt giảm accuracy, kết hợp giám sát metric `agent_retrieval_total{result="hit"}` (v1 khiến lượt retrieval hit giảm về 0) và `agent_info{version=...}`.

### 4.3 Debug bằng Trace thật (OpenTelemetry + JSON Log từ `production/app/main.py`)

Từ lần chạy trực tiếp `production/app/main.py` bằng Python ở trên, ghi nhận 1 **slow trace** và 1 **error trace** thật:

- **Slow Trace thật (`trace_id`: `5f0f9e86a698192d68db36810d55951c`):**
  - Tổng thời gian (`POST /ask`): **`1735.2 ms`** (`agent.run`: `1730.22 ms`)
  - `agent.retrieve_context`: `22.96 ms` (`retrieval.documents = 1`)
  - **Span chiếm nhiều thời gian nhất:** `chat mock-llm-small` = **`1706.6 ms`** (**~98.4%** tổng thời gian request; `gen_ai.usage.input_tokens = 90`, `output_tokens = 55`, `llm.cost_usd = 4.65e-05`)
  - **2 dòng log JSON thật khớp `trace_id`:**
```json
{"ts": "2026-11-26T09:30:02.087159+00:00", "level": "INFO", "service": "observable-agent", "instance": "local", "event": "llm_call", "trace_id": "5f0f9e86a698192d68db36810d55951c", "span_id": "7f1bd3676db10fb0", "request_id": "f5970f4adf84", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 90, "output_tokens": 55, "cost_usd": 4.6e-05, "llm_ms": 1694.6}
{"ts": "2026-11-26T09:30:02.088256+00:00", "level": "INFO", "service": "observable-agent", "instance": "local", "event": "http_request", "trace_id": "5f0f9e86a698192d68db36810d55951c", "span_id": "7f1bd3676db10fb0", "request_id": "f5970f4adf84", "method": "POST", "route": "/ask", "status": 200, "ms": 1733.3}
```

- **Error Trace thật (`trace_id`: `3ab792ddb9f320cd75811eeecbcf509e`):**
  - `POST /ask`: `886.28 ms`, `http.status_code = 503`, `status = ERROR`
  - Span lỗi: `chat mock-llm-small` (`845.74 ms`, `status = ERROR`, `error.type = upstream_unavailable`)
  - **2 dòng log JSON thật khớp `trace_id`:**
```json
{"ts": "2026-11-26T09:29:56.538761+00:00", "level": "INFO", "service": "observable-agent", "instance": "local", "event": "llm_error", "trace_id": "3ab792ddb9f320cd75811eeecbcf509e", "span_id": "25775500fc890cfa", "request_id": "56c9ccf68589", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-26T09:29:56.539753+00:00", "level": "INFO", "service": "observable-agent", "instance": "local", "event": "http_request", "trace_id": "3ab792ddb9f320cd75811eeecbcf509e", "span_id": "25775500fc890cfa", "request_id": "56c9ccf68589", "method": "POST", "route": "/ask", "status": 503, "ms": 885.5}
```

---

## 5. Benchmark scaling (`production/`, Locust headless)

* *(Trạng thái trung thực: Chưa chạy `docker compose -p k5-day14-observability up --scale agent=1 / 3` và Locust headless vì máy Windows chưa cài Docker Desktop nên không điền số đo giả.)*
* **Phân tích kiến trúc scale:** Do agent hoàn toàn stateless (và dùng bất đồng bộ `async/await`), tăng từ 1 lên 3 instance giúp tăng tổng thông lượng (`RPS`) khi Nginx chia tải (`server agent:8000 resolve` qua Docker DNS mỗi 10s). Tuy nhiên, `p95` latency của từng request có thể giảm ít nếu nút thắt nằm ở thời gian chờ upstream LLM (`chat mock-llm-small` vốn chiếm ~98% latency của mỗi request chứ không phải CPU của FastAPI).

---

## 6. Kết luận

- **3 điều rút ra về benchmark & observability:**
  1. **Không bao giờ dùng `avg` thay cho `p95`/`p99` làm SLO:** Thực nghiệm `MOCK_SLOW_RATE=0.03` cho thấy `avg` chỉ nhích `+55ms` nhưng `p99` nhảy lên `1712.5 ms`.
  2. **Chất lượng (`eval`) phải đi cùng hiệu năng (`load test`):** Thay đổi nhỏ ở `KNOWLEDGE_BASE` tăng accuracy từ `91.3%` lên `100%` và giúp `cost / câu đúng` của `v2` rẻ hơn v1 gần 12 lần; đồng thời quality gate trong CI giúp chặn mọi regression trước khi merge.
  3. **Liên kết 3 trụ cột Metrics – Traces – Logs qua `trace_id`:** Metric cho biết hệ thống chậm/lỗi ở đâu, trace chỉ rõ span `chat mock-llm-small` chiếm ~98% thời gian hay gặp lỗi upstream `503`, và `trace_id` giúp truy vết chính xác dòng log JSON sự cố.
- **Nếu đưa lên production thật, sẽ bổ sung:** Synthetic evaluation chạy định kỳ để bắt lỗi suy giảm chất lượng kiểu thí nghiệm E; tích hợp Alertmanager gửi cảnh báo về Slack/Discord; và tail-based sampling cho OpenTelemetry để giữ lại 100% error trace & slow trace nhưng giảm chi phí lưu trữ trace bình thường.
