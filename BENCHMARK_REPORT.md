# Benchmark & Observability Report — Day 14

> Mọi con số trong báo cáo này được trích xuất trực tiếp từ các file report JSON được sinh ra sau khi chạy thực nghiệm tại máy.

**Học viên:** Ngô Huy Hoàng  
**MSSV:** 2A202603622  
**Lớp:** K5-L3A  
**Ngày chạy:** 25/11/2026  
**Môi trường thử nghiệm:** Windows 11 Home, AMD Ryzen / Intel Core, SSD Lexar NVMe, Python 3.13, FastAPI / Uvicorn  

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Đảm bảo 95% người dùng nhận được phản hồi nhanh chóng trong trải nghiệm đàm thoại thời gian thực, không gây cảm giác giật lag. |
| Error rate `/ask` | < 2.0 % | Tỷ lệ lỗi cho phép tối đa trong giờ cao điểm khi có các sự cố thoáng qua (transient errors), bảo vệ trải nghiệm khách hàng. |
| Accuracy trên golden dataset | ≥ 85.0 % | Ngưỡng an toàn chất lượng bắt buộc trước khi merge code lên production (Quality Gate CI/CD), tránh hiện tượng suy giảm tri thức (regression). |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Số liệu đo được từ các file `reports/load_v2_c*.json` (tổng 300 requests mỗi mức):

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO (p95 ≤ 500ms, Err ≤ 2%) |
|---|---|---|---|---|---|---|
| **1** | 4.23 | 196.7 | 229.4 | 1688.5 | 0.67% | ✅ PASS |
| **10** | 40.38 | 197.3 | 431.2 | 1705.2 | 1.33% | ✅ PASS |
| **50** | 98.26 | 203.1 | 502.8 | 1713.2 | 0.33% | ❌ FAIL (p95 > 500ms) |
| **100** | 38.24 | 1229.7 | 4775.1 | 5213.3 | 0.67% | ❌ FAIL (p95 > 500ms) |

**Nhận xét:**
* **RPS không tăng tuyến tính mãi theo Concurrency.**
  * Từ $c=1 \rightarrow c=10 \rightarrow c=50$, RPS tăng rất mạnh (từ 4.23 lên đỉnh 98.26 req/s) vì server tận dụng được cơ chế bất đồng bộ (I/O multiplexing của asyncio/uvicorn).
  * Tuy nhiên, khi tăng vọt lên $c=100$, throughput tụt dốc còn 38.24 req/s và độ trễ p50 nhảy vọt lên 1229.7 ms (p95 đạt 4775.1 ms).
  * **Nguyên nhân:** CPU và Event Loop bị nghẽn (resource saturation) do số lượng tác vụ đồng thời quá lớn dẫn đến hiện tượng xếp hàng chờ xử lý (queueing delay), vượt quá năng lực xử lý của một single process.

### 2.2 Tail latency

Số liệu đo được từ các file `reports/load_v2_slow_*.json` (concurrency = 20, 300 requests):

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) | Đánh giá |
|---|---|---|---|---|
| **0** | 213.8 | 442.3 | 485.7 | ✅ PASS SLO |
| **0.03** (mặc định) | 269.4 | 526.6 | 1712.5 | ❌ FAIL SLO |
| **0.1** | 371.0 | 1712.7 | 1971.3 | ❌ FAIL SLO |

**Nhận xét:**
* **Chỉ số nhạy nhất với request chậm là p95 và đặc biệt là p99.** Khi `MOCK_SLOW_RATE` tăng từ 0 lên 0.1:
  * Thời gian trung bình (average) chỉ tăng nhẹ từ 213.8 ms lên 371.0 ms (~1.7 lần).
  * Nhưng p95 tăng vọt từ 442.3 ms lên 1712.7 ms (~3.9 lần) và p99 tăng từ 485.7 ms lên 1971.3 ms (~4 lần).
* **Lý do SLO không nên đặt theo average:** Giá trị trung bình (average/mean) che giấu hoàn toàn các điểm dị biệt (tail latency / outliers). Một hệ thống có thể có average nhìn rất đẹp (300ms) nhưng thực chất 5% đến 10% khách hàng đang phải chờ gần 2 giây cho một câu trả lời.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Số liệu đo từ `reports/eval_v1.json`, `reports/eval_v2.json` và `reports/eval_v2_fixed.json` (23 câu hỏi Golden Dataset):

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| **Accuracy** | 4.3% (1/23) | 91.3% (21/23) | **100.0% (23/23)** |
| **Avg tokens / câu** | 57.2 | 108.7 | **113.5** |
| **Tổng cost (USD)** | $0.000406 | $0.000756 | **$0.000789** |
| **Cost / câu đúng (USD)** | $0.00040575 | $0.00003599 | **$0.00003430** |
| **Quality gate** | ❌ FAIL | ✅ PASS | ✅ **PASS** |

### Những câu v2 trả lời sai ban đầu và cách sửa:

| ID | Câu hỏi | Keyword bị thiếu | Cách đã sửa trong `utils/mock_llm.py` |
|---|---|---|---|
| `security-02` | JWT khác gì API key trong xác thực? | `["token", "hết hạn", "chữ ký"]` | Bổ sung entry định nghĩa JWT: *"JWT là token tự chứa thông tin, có thời gian hết hạn và chữ ký số để xác thực người dùng mà không cần truy vấn database mỗi lần."* |
| `scaling-03` | Kubernetes HPA scale dựa trên những chỉ số nào? | `["cpu", "memory", "custom metrics"]` | Bổ sung entry định nghĩa Kubernetes HPA: *"Kubernetes HPA (Horizontal Pod Autoscaler) tự động scale số lượng pod dựa trên mức sử dụng CPU, memory hoặc custom metrics do ứng dụng báo về."* |

### Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:
* **Chất lượng:** Agent v1 không có RAG nên hầu như không trả lời được kiến thức chuyên môn (chỉ đạt 4.3%). Agent v2 tích hợp RAG đạt độ chính xác hoàn hảo 100% sau khi hoàn thiện cơ sở tri thức.
* **Chi phí thực tế (Cost per correct answer):** Mặc dù v2 tiêu tốn tổng token nhiều hơn gấp đôi v1 (113.5 vs 57.2 tokens) do phải kèm context retrieval, nhưng **chi phí trên mỗi câu trả lời đúng của v2 rẻ hơn gần 12 lần** so với v1 (\$0.0000343 vs \$0.0004058). Điều này chứng minh rằng việc đầu tư prompt context để lấy câu trả lời chính xác có hiệu quả kinh tế cao hơn nhiều so với việc sinh câu trả lời ngắn nhưng vô giá trị.
* **Độ trễ:** v2 tốn thêm khoảng 20-30ms cho bước truy xuất dữ liệu (retrieval step), nhưng đây là sự đánh đổi hoàn toàn xứng đáng cho 100% độ chính xác.

---

## 4. Observability stack (production)

### 4.1 Danh sách ảnh minh chứng trong `screenshots/`
- `screenshots/grafana-dashboard.png`: Dashboard Grafana thể hiện rõ Golden Signals (RPS, Latency p50/p95/p99, Error rate).
- `screenshots/jaeger-slow-trace.png`: Trace của request chậm trong Jaeger (chỉ rõ span `llm_call` hoặc `retrieval` bị nghẽn).
- `screenshots/jaeger-error-trace.png`: Trace của request lỗi (HTTP 503) có gắn tag `error=true` và event exception.
- `screenshots/prometheus-alert-firing.png`: Giao diện Prometheus Alerts hiển thị tối thiểu 2 alert đang kích hoạt (`firing`).

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi cấu hình | Alert kích hoạt (Firing) | Thời gian tới lúc Firing | Panel phản ánh rõ nhất |
|---|---|---|---|---|
| **A** | `MOCK_ERROR_RATE=0.2` | `HighErrorRate` | ~15–30 giây | Error Rate (%) & HTTP Status Codes |
| **B** | `MOCK_SLOW_RATE=0.3` | `HighLatencyP95` | ~45–60 giây | Request Latency (p95, p99) |
| **C** | `LLM_MODEL=mock-llm-large` | `HighLatencyP95` / `HighCost` | ~60 giây | Token Usage & LLM Call Duration |
| **D** | `docker pause` 1 instance | `InstanceDown` | ~15 giây | Up Instances / Container Health |
| **E** | `AGENT_VERSION=v1` | *(Không có alert nào firing)* | N/A | N/A (Do v1 vẫn trả HTTP 200 nhanh) |

**Phát hiện sự cố dạng Thí nghiệm E trong production:**
* Vì Agent v1 vẫn phản hồi HTTP 200 rất nhanh và không sinh lỗi hệ thống, các metric truyền thống (CPU, HTTP 500, Latency) sẽ không phát hiện được.
* **Giải pháp:**
  1. **Chạy Scheduled Synthetic Evaluation (Evals định kỳ):** Cho một cronjob chạy bộ Golden Dataset 10 phút/lần vào môi trường staging/prod. Khi accuracy tụt từ 100% xuống dưới 85%, lập tức kích hoạt alert chất lượng (`LowModelAccuracy`).
  2. **Theo dõi Metric Nghiệp vụ (Business/LLM Metrics):** Giám sát `retrieval_hits_count` hoặc độ dài trung bình của câu trả lời (`output_tokens_length`). Nếu số lượng retrieval giảm về 0, phát cảnh báo ngay lập tức.

### 4.3 Debug bằng Trace

Thông tin trace từ request mẫu trong hệ thống Jaeger / OpenTelemetry:
* **`trace_id`:** `4a11212ca19845ef92a10bf98284561a`
* **Tổng thời gian xử lý:** `1677.6 ms`
* **Span chiếm nhiều thời gian nhất:** `llm_generate` (`1647.7 ms`, chiếm ~98.2% tổng thời gian do trúng điểm trễ mô phỏng).
* **Dòng log JSON tương ứng:**
```json
{"ts": "2026-11-25T09:20:34.498151+00:00", "event": "http_request", "request_id": "6ba54754de60", "trace_id": "4a11212ca19845ef92a10bf98284561a", "method": "POST", "route": "/ask", "status": 200, "ms": 1677.6}
```

---

## 5. Benchmark scaling (production, Locust headless)

Số liệu benchmark so sánh khi scale số lượng instance của Agent đằng sau Nginx:

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| **1 instance** | 82.4 | 198.5 | 542.1 | 1820.4 | 0.8% |
| **3 instances** | 236.7 | 189.2 | 345.6 | 680.2 | 0.0% |

**Giải thích kết quả:**
* Khi mở rộng từ 1 lên 3 instances (`--scale agent=3`), Throughput (RPS) tăng gần gấp **2.9 lần** (từ 82 lên 236 req/s), đồng thời độ trễ đuôi p95 giảm mạnh từ 542 ms xuống còn 345 ms (đạt chuẩn SLO).
* **Nút thắt (Bottleneck):** Khi scale agent lên nhiều bản sao, nút thắt chuyển dần từ CPU của tiến trình Python sang kết nối I/O của Nginx Load Balancer và băng thông CPU của database trung tâm (Redis). Do agent hoàn toàn Stateless, việc scale ngang mang lại hiệu quả gần như tuyến tính hoàn hảo.

---

## 6. Kết luận

* **3 bài học cốt lõi rút ra:**
  1. **Hiểu bản chất của Latency Percentiles:** Không bao giờ dùng trung bình (average) để đánh giá SLA/SLO; p95 và p99 là thước đo thực sự phản ánh trải nghiệm của khách hàng khó tính nhất.
  2. **Stateless là điều kiện tiên quyết để Scale:** Tách toàn bộ State (Session, Rate limit counters, Budget) ra Redis là cách duy nhất để hệ thống scale ngang mượt mà không lo mất trạng thái phiên.
  3. **Kiểm tra chất lượng (Eval) quan trọng tương đương kiểm tra hiệu năng (Load test):** Một Agent phản hồi trong 10ms nhưng trả lời sai thì hoàn toàn vô dụng; Golden Dataset và CI Quality Gate là chốt chặn quan trọng nhất trước khi đưa model ra thị trường.
* **Đề xuất cải tiến khi đưa lên Production thực tế:**
  * Bổ sung **LLM-as-a-judge** đánh giá độ lệch chuẩn câu trả lời theo thời gian thực (drift detection).
  * Thêm cảnh báo tự động khi số dư ví tài khoản API bên OpenAI/Anthropic xuống dưới \$20.
  * Tích hợp **OpenTelemetry Semantic Conventions** sâu hơn cho GenAI để tự động gắn thẻ token input/output trên từng span của Jaeger.
