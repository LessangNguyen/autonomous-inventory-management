# Infrastructure

Thư mục này ghi chú phần triển khai ngoài Docker Compose. MVP chạy được bằng
`docker-compose.yml` ở gốc repo; các tệp dưới đây là hướng dẫn production hoá,
**chưa được kiểm thử** trên hạ tầng thật.

## Thành phần

| Thành phần | MVP | Production đề xuất |
| --- | --- | --- |
| Compute | Docker Compose trên 1 máy | Kubernetes/ECS, 2+ replica backend |
| Database | PostgreSQL 16 (container) | Managed PostgreSQL, PITR, replica đọc |
| Object storage | Volume `backend_uploads` | S3/GCS cho file import |
| Secrets | `.env` | Vault/SSM/Secrets Manager |
| Ingress | nginx trong frontend image | ALB/Nginx + TLS, rate limit, WAF |
| Observability | stdout logs | Grafana/Loki, Prometheus, Sentry |
| Backup | `pg_dump` thủ công | Tự động hằng ngày + kiểm tra phục hồi |

## Biến môi trường production tối thiểu

```env
ENVIRONMENT=production
SECRET_KEY=<32+ ký tự ngẫu nhiên>
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/inventory
CORS_ORIGINS=https://inventory.example.com
SEED_DEMO_DATA=false
ALLOW_REGISTRATION=true
LLM_API_KEY=            # để trống nếu dùng RuleRouter offline
```

## Lưu ý trước khi public

1. Bật HTTPS và không expose cổng 8000 trực tiếp.
2. Bật PostgreSQL RLS (mọi bảng đều có `tenant_id`).
3. Thêm Alembic migration thay cho `create_all`.
4. Chuyển dự báo sang background worker + hàng đợi.
5. Thêm rate limiting cho `/api/auth/*` và `/api/agent/chat`.
6. Cấu hình log tập trung và cảnh báo lỗi 5xx.
7. Thiết lập backup tự động và diễn tập phục hồi.

Chi tiết vận hành: [`../docs/RUNBOOK.md`](../docs/RUNBOOK.md).
