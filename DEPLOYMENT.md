# Cloud Deployment Information — Day 14 Lab

> **Học viên:** Ngô Huy Hoàng  
> **MSSV:** 2A202603622  
> **Lớp:** K5-L3A  
> **Repository:** K5-L3A-DAY14-NgoHuyHoang-2A202603622-Deployment-Benchmark-Observability  

---

## 1. Trạng thái Deploy

* **Nền tảng mục tiêu:** Railway (`06-lab-complete/railway.toml`) hoặc Render (`06-lab-complete/render.yaml`)
* **Trạng thái hiện tại:** **Chưa deploy lên cloud** (đã chuẩn bị đầy đủ `Dockerfile`, `railway.toml`, `render.yaml` trong `06-lab-complete/`, nhưng chưa tạo service và Redis cloud để có Public URL chạy thật).
* **Public URL:** *(Chưa có — cần deploy thư mục `06-lab-complete/` lên Railway hoặc Render và điền URL vào đây)*

---

## 2. Cấu hình nền tảng & Biến môi trường cần thiết lập

Trong `06-lab-complete/railway.toml`:
* `builder = "DOCKERFILE"`, `healthcheckPath = "/health"`, `CMD` trong `Dockerfile` đọc `${PORT:-8000}`.

Trong `06-lab-complete/render.yaml`:
* `type: web`, `runtime: docker`, `plan: free`, `healthCheckPath: /health`.
* Secret `AGENT_API_KEY` dùng `generateValue: true`; `REDIS_URL` dùng `sync: false` (không ghi secret vào code).

| Tên biến môi trường | Giá trị mẫu / Nguồn | Mục đích |
| :--- | :--- | :--- |
| `PORT` | Do Railway/Render tự cấp (mặc định `8000`) | Cổng lắng nghe của `uvicorn` |
| `ENVIRONMENT` | `production` | Cấu hình môi trường chạy thật |
| `AGENT_API_KEY` | Tạo ngẫu nhiên / đặt trên dashboard | Xác thực header `X-API-Key` cho `POST /ask` |
| `REDIS_URL` | `redis://...` từ addon Redis trên cloud | Lưu state rate limit & cost guard (stateless) |
| `RATE_LIMIT_PER_MINUTE` | `10` | Giới hạn request mỗi phút / API key |
| `DAILY_BUDGET_USD` | `1.0` | Giới hạn ngân sách LLM theo ngày |

---

## 3. Lệnh triển khai & 4 lệnh tự kiểm sau khi deploy (CP6)

Sau khi deploy `06-lab-complete/` kèm Redis addon trên Railway/Render, đặt `BASE=<URL_PUBLIC>` và `AGENT_API_KEY=<KEY_DA_DAT>` rồi chạy:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # Mong đợi: 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # Mong đợi: 200 (khi có REDIS_URL đúng)
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # Mong đợi: 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # Mong đợi: 200
```

Và chạy kiểm tra cuối bằng script chấm:
```bash
cd 06-lab-complete
python check_production_ready.py --public-url "$BASE"
```
