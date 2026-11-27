# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được trích xuất từ kết quả chạy thật toàn bộ các script trong `06-lab-complete/benchmark-observability/` (`develop/` với `load_test.py` + `eval/run_eval.py`, và `production/` full Docker Compose stack gồm Nginx, FastAPI Agent, Prometheus v3.16.0, Grafana 13.2.4, Jaeger 2.23.0, Locust 2.47.0).

**Họ tên:** Ngô Huy Hoàng  
**MSSV:** 2A202603622  
**Ngày chạy:** 25–26/11/2026  
**Môi trường:** Windows 11, Docker Desktop 4.100.1 (Docker Engine 29.9.3, WSL2 backend lưu trên `D:\Docker\data`), SSD Lexar NVMe, Python 3.13.15 (`.venv`) / Python 3.11 trong container, FastAPI 0.115.0, Uvicorn 0.30.0  

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

## 4. Observability (Full Docker Compose Stack: Prometheus, Grafana, Jaeger)

> **Khắc phục lỗi khởi chạy container agent:** `06-lab-complete/benchmark-observability/production/Dockerfile` ban đầu gặp `ModuleNotFoundError: No module named 'uvicorn'` (user `agent` có `$HOME=/app` nên Python không tìm `/home/agent/.local`). Sau khi thêm `--chown=agent:agent` và `ENV PYTHONUSERBASE=/home/agent/.local`, toàn bộ stack (`agent` x1/x3, `nginx:1.28-alpine`, `prometheus:v3.16.0`, `grafana:13.2.4`, `jaeger:2.23.0`, `locust:2.47.0`) khởi động khỏe mạnh 100%.

### 4.1 Metrics & Grafana Dashboard ([`screenshots/grafana-dashboard.png`](screenshots/grafana-dashboard.png))

Snapshot PromQL thu từ Prometheus (`http://localhost:9090/api/v1/query`) trong đợt tải hỗn hợp & fault-injection (`mock-llm-large`, `MOCK_ERROR_RATE=0.25`, `MOCK_SLOW_RATE=0.30`):
- `sum(rate(http_requests_total{job="agent",route="/ask"}[1m]))` = **`0.764 req/s`** (khi chạy burst) · đỉnh trong Locust đạt **`~60 req/s`**
- `sum(rate(http_requests_total{job="agent",route="/ask",status=~"5.."}[1m])) / sum(rate(http_requests_total{job="agent",route="/ask"}[1m]))` = **`0.2619` (`26.2%`)**
- `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job="agent",route="/ask"}[1m])))` = **`2.838 s`** (Grafana panel hiển thị `2.90 s` vượt ngưỡng SLO đỏ `1s`)
- `sum(llm_cost_usd_total{job="agent"})` = **`$0.048485`** (burn rate 1h tăng gần **$6/giờ** trong nhịp burst); `llm_tokens_total{model="mock-llm-large"}` = **`9,182` tokens**

**Trả lời Exercise 7.4 (từ Grafana dashboard, Prometheus & `nginx/nginx.conf`):**
1. **Khoảng cách giữa `avg` và `p95` trên panel Latency:** `avg` tính bằng `rate(http_request_duration_seconds_sum[1m]) / rate(http_request_duration_seconds_count[1m])`, còn `p95` tính từ histogram buckets qua `histogram_quantile(0.95, ...)`. Khi có request chậm (~1.7–2.1s), `avg` bị các request nhanh (~150–200ms) kéo xuống dưới `1s`, còn `p95` vọt lên `2.8–2.9s`, tách xa hẳn đường `avg`.
2. **Vì sao `input_tokens` luôn lớn hơn `output_tokens`:** Ở agent `v2`, bước RAG chèn ngữ cảnh truy xuất từ `KNOWLEDGE_BASE` vào prompt gửi LLM (ví dụ `92` input tokens vs `55` output tokens ở trace bên dưới), khiến token đầu vào luôn cao hơn câu trả lời đầu ra.
3. **Vì sao `/metrics` bị chặn (`404`) ở `nginx/nginx.conf` (dòng 22–24):** `location = /metrics { return 404; }` ngăn truy cập công khai từ Internet để tránh lộ nội bộ lưu lượng, error rate, model và chi phí LLM. Prometheus vẫn scrape bình thường qua mạng Docker nội bộ (`agent:8000/metrics` bằng DNS service discovery mỗi 5s).

### 4.2 Alert Unit Test & Thí nghiệm "phá hệ thống" (`prometheus/alert_rules.yml`)

- **Kiểm thử unit test rule bằng `promtool`:**
  `docker run --rm -v ".../prometheus:/p" --entrypoint promtool prom/prometheus:v3.16.0 test rules /p/alert_rules_test.yml` → **`SUCCESS`**.
- **Kết quả chạy thực tế các thí nghiệm A–E trên stack Docker Compose:**
  1. **C + A + B (`LLM_MODEL=mock-llm-large`, `MOCK_ERROR_RATE=0.25`, `MOCK_SLOW_RATE=0.30`):**
     - `LLMCostBurnRateHigh` (`for: 2m`): chuyển sang **`FIRING`** từ `11:56:27Z` với burn rate **`$2.89 – $3.39/giờ`** (vượt ngưỡng `$2/giờ`).
     - `AgentHighErrorRate` (`for: 1m`): `pending` lúc `12:01:07Z` (`35.8%`) → **`FIRING`** sau ~1 phút (`25.0% – 25.8%` > `5%`, `severity="critical"`).
     - `AgentHighLatencyP95` (`for: 2m`): `pending` lúc `12:01:12Z` (`2.66s`) → **`FIRING`** sau ~2 phút (**`2.806 s`** > `1s`, `severity="warning"`).
     - Ảnh chụp cả hai alert `AgentHighErrorRate` và `AgentHighLatencyP95` cùng đang `FIRING` tại `http://localhost:9090/alerts`: [`screenshots/prometheus-alert-firing.png`](screenshots/prometheus-alert-firing.png).
  2. **D (`docker pause k5-day14-observability-agent-1`):** Container vẫn còn IP trong Docker DNS nhưng tiến trình đóng băng nên Prometheus scrape timeout → `up{job="agent"} == 0`. Alert `AgentInstanceDown` chuyển sang **`pending`** sau ~20s (`Instance agent 172.18.0.4:8000 không scrape được`; unpause sau 25s trước khi hết `for: 30s`). Ngoài ra, các request Nginx chuyển tới instance bị pause sẽ nhận **504 Gateway Timeout** ở tầng proxy (sau `proxy_read_timeout`), không xuất hiện trong metric của agent nên cần monitor thêm tầng proxy/synthetic.
  3. **E (`AGENT_VERSION=v1`):** Đổi sang `v1`, `agent_info` chuyển `version="v1"` trên cả 3 instance (`172.18.0.4`, `.8`, `.9`); câu hỏi `"What is RAG?"` trả HTTP `200` nhanh (`llm_latency_ms: 155.5`, `input_tokens: 29`, `cost_usd: 1.875e-05`) nhưng trả câu generic sai ngữ cảnh RAG và `agent_retrieval_total` không tăng. **Không alert hạ tầng nào firing** — buộc phải dùng **synthetic evaluation** định kỳ trên `golden_dataset.jsonl` + theo dõi sụt giảm `agent_retrieval_total{result="hit"}` để phát hiện regression.

### 4.3 Debug bằng Trace thật (Jaeger UI + JSON Log khớp `trace_id`)

1. **Slow Trace thật (`trace_id: b55e41c90f48d0253fd881e2083bc268`) — [`screenshots/jaeger-slow-trace.png`](screenshots/jaeger-slow-trace.png):**
   - Tổng thời gian (`POST /ask`): **`2.1 s`** (`2084.4 ms` trên log), Depth `3`, `4` spans (`agent.run`: `2.1s`, `agent.retrieve_context`: **`18.8 ms`**).
   - **Span chậm nhất:** `chat mock-llm-large` = **`2.1 s`** (`llm_ms = 2055.7 ms`, chiếm **~98.6%** thời gian request; `Input: 92`, `Output: 55` tokens, `cost_usd: 0.00078`).
   - **2 dòng log JSON thật từ `docker compose logs agent` khớp `trace_id`:**
```json
{"ts": "2026-11-26T12:02:55.032819+00:00", "level": "INFO", "service": "observable-agent", "instance": "c7e3091e04e5", "event": "llm_call", "trace_id": "b55e41c90f48d0253fd881e2083bc268", "span_id": "6c9669f64f895722", "request_id": "6271d15de4b8", "model": "mock-llm-large", "agent_version": "v2", "input_tokens": 92, "output_tokens": 55, "cost_usd": 0.00078, "llm_ms": 2055.7}
{"ts": "2026-11-26T12:02:55.036320+00:00", "level": "INFO", "service": "observable-agent", "instance": "c7e3091e04e5", "event": "http_request", "trace_id": "b55e41c90f48d0253fd881e2083bc268", "span_id": "6c9669f64f895722", "request_id": "6271d15de4b8", "method": "POST", "route": "/ask", "status": 200, "ms": 2084.4}
```

2. **Error Trace thật (`trace_id: 61bd3fb5e2bacc3bfd082a27fdeb7861`) — [`screenshots/jaeger-error-trace.png`](screenshots/jaeger-error-trace.png):**
   - Tổng thời gian (`POST /ask`): **`1.1 s`** (`1079.4 ms`), `http.status_code = 503`, `agent.retrieve_context` chạy thành công (`25.5 ms`).
   - Span lỗi (`chat mock-llm-large`, `1.0 s`, `SpanID: 4363a186e50cb5c2`, `error.type = upstream_unavailable`): ghi event exception `utils.mock_llm.LLMError: Upstream LLM error: 503 Service Unavailable (mock)` tại `/app/app/main.py:153` → `/app/utils/mock_llm.py:203`.
   - **Dòng log JSON thật khớp `trace_id`:**
```json
{"ts": "2026-11-26T12:01:11.663728+00:00", "level": "INFO", "service": "observable-agent", "instance": "9c13905928f6", "event": "http_request", "trace_id": "61bd3fb5e2bacc3bfd082a27fdeb7861", "span_id": "6afa6d4e477ae449", "request_id": "b29ee9ad9c00", "method": "POST", "route": "/ask", "status": 503, "ms": 1079.4}
```

---

## 5. Benchmark scaling (`production/`, Locust headless: 1 vs 3 replicas)

Chạy Locust (`-u 100 -r 10 -t 2m`) qua Nginx tới stack Docker Compose với cấu hình mặc định (`AGENT_VERSION=v2`, `MOCK_LATENCY_MS=120`, `MOCK_SLOW_RATE=0.03`, `MOCK_ERROR_RATE=0.01`). Trích trực tiếp từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv`:

| Cấu hình | Endpoint | # Reqs | Fails | Req/s | Avg (ms) | p50 (ms) | p90 (ms) | p95 (ms) | p99 (ms) | Max (ms) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`scale=1`** | `POST /ask` | 6,535 | 55 (`0.84%`) | 55.03 | 361.4 | 220 | 820 | **1,400** | 1,900 | 3,063 |
| **`scale=1`** | `GET /health` | 675 | 0 (`0.00%`) | 5.68 | 67.1 | 8 | 140 | **470** | 910 | 1,448 |
| **`scale=1`** | **Aggregated** | **7,210** | **55 (`0.76%`)** | **60.71** | **333.8** | **210** | **740** | **1,300** | **1,900** | **3,063** |
| **`scale=3`** | `POST /ask` | 6,991 | 73 (`1.04%`) | 58.76 | 260.6 | 200 | 270 | **400** | 1,700 | 2,246 |
| **`scale=3`** | `GET /health` | 698 | 0 (`0.00%`) | 5.87 | 16.7 | 7 | 24 | **54** | 170 | 814 |
| **`scale=3`** | **Aggregated** | **7,689** | **73 (`0.95%`)** | **64.63** | **238.4** | **200** | **260** | **380** | **1,700** | **2,246** |

**Phân tích kết quả scale `1 → 3`:**
- **Hiệu quả giảm tail latency rõ rệt nhờ triệt tiêu hàng đợi ở CPU/event loop:** Ở 1 container bị giới hạn `0.5 CPU`, `p95` của `POST /ask` bị đẩy lên **`1,400 ms`** (`p90 = 820 ms`) và ngay cả `GET /health` nhẹ cũng đội `p95` lên **`470 ms`** do nghẽn cổ chai. Khi scale lên **3 instance** (xác nhận Prometheus scrape `3/3 up`), Nginx rải tải khiến **`p95` của `/ask` giảm 3.5 lần (`1,400 ms → 400 ms`, đạt SLO < 500ms!)**, `p90` giảm **`820 ms → 270 ms`**, và `/health` `p95` giảm gần 9 lần (**`470 ms → 54 ms`**).
- **Vì sao RPS chỉ tăng nhẹ (`60.7 → 64.6 req/s`) thay vì gấp 3:** Do bài test dùng 100 closed-loop Locust users có `wait_time` nghỉ giữa các request (khi response nhanh hơn, user vẫn phải chờ `wait_time` cố định nên tải phát ra bị chặn trần bởi số user), còn tỷ lệ lỗi `~0.8–1.0%` là lỗi upstream cố ý từ `MOCK_ERROR_RATE=0.01` chứ không phải quá tải.

---

## 6. Kết luận

- **3 điều rút ra về benchmark & observability:**
  1. **Không bao giờ dùng `avg` thay cho `p95`/`p99` làm SLO:** Thực nghiệm `MOCK_SLOW_RATE=0.03` cho thấy `avg` chỉ nhích `+55ms` nhưng `p99` nhảy lên `1712.5 ms`.
  2. **Chất lượng (`eval`) phải đi cùng hiệu năng (`load test`):** Thay đổi nhỏ ở `KNOWLEDGE_BASE` tăng accuracy từ `91.3%` lên `100%` và giúp `cost / câu đúng` của `v2` rẻ hơn v1 gần 12 lần; đồng thời quality gate trong CI giúp chặn mọi regression trước khi merge.
  3. **Liên kết 3 trụ cột Metrics – Traces – Logs qua `trace_id`:** Metric cho biết hệ thống chậm/lỗi ở đâu, trace chỉ rõ span `chat mock-llm-small` chiếm ~98% thời gian hay gặp lỗi upstream `503`, và `trace_id` giúp truy vết chính xác dòng log JSON sự cố.
- **Nếu đưa lên production thật, sẽ bổ sung:** Synthetic evaluation chạy định kỳ để bắt lỗi suy giảm chất lượng kiểu thí nghiệm E; tích hợp Alertmanager gửi cảnh báo về Slack/Discord; và tail-based sampling cho OpenTelemetry để giữ lại 100% error trace & slow trace nhưng giảm chi phí lưu trữ trace bình thường.
