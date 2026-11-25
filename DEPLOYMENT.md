# Cloud Deployment Information — Day 14 Lab

> **Học viên:** Ngô Huy Hoàng  
> **MSSV:** 2A202603622  
> **Lớp:** K5-L3A  
> **Repository:** K5-L3A-DAY14-NgoHuyHoang-2A202603622-Deployment-Benchmark-Observability  

---

## 1. Thông tin Deploy

* **Nền tảng triển khai:** Railway (hoặc Render)
* **URL Public của Agent:** `https://k5-l3a-day14-ngohuyhoang.up.railway.app`
* **Cấu hình builder:** `DOCKERFILE` qua file `railway.toml`

---

## 2. Các biến môi trường đã thiết lập trên Dashboard Cloud

| Tên biến môi trường | Giá trị thiết lập | Mô tả mục đích |
| :--- | :--- | :--- |
| `PORT` | `8000` | Cổng dịch vụ lắng nghe (nền tảng tự động cấp) |
| `ENVIRONMENT` | `production` | Môi trường triển khai thực tế |
| `AGENT_API_KEY` | `secret-prod-vinuni-2026` | API Key bảo vệ endpoint `/ask` |
| `REDIS_URL` | `redis://...` | Kết nối tới instance Redis được cấp trên cloud |
| `RATE_LIMIT_PER_MINUTE` | `10` | Giới hạn tối đa 10 request/phút |
| `DAILY_BUDGET_USD` | `1.0` | Ngân sách giới hạn chi phí LLM trong ngày |

---

## 3. Lệnh kiểm tra xác thực (Test Commands)

### 1. Kiểm tra Liveness (Trả về 200 OK):
```bash
curl -i https://k5-l3a-day14-ngohuyhoang.up.railway.app/health
```

### 2. Kiểm tra Readiness (Trả về 200 OK khi Redis kết nối):
```bash
curl -i https://k5-l3a-day14-ngohuyhoang.up.railway.app/ready
```

### 3. Kiểm tra từ chối khi không có API Key (Trả về 401 Unauthorized):
```bash
curl -i -X POST https://k5-l3a-day14-ngohuyhoang.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is deployment?"}'
```

### 4. Kiểm tra thành công khi có API Key (Trả về 200 OK):
```bash
curl -i -X POST https://k5-l3a-day14-ngohuyhoang.up.railway.app/ask \
  -H "X-API-Key: secret-prod-vinuni-2026" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is deployment?"}'
```
