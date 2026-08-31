# Security Setup & Secret Rotation

## ⚠️ Important: Secret Rotation Performed

### Changes Applied
- **SECRET_KEY**: Rotated from weak default `django-insecure-napino-mes-secret-key-change-in-production` to a strong random key (50-char URL-safe random)
- **ALLOWED_HOSTS**: Changed from `*` (wildcard) to explicit `localhost,127.0.0.1`
- **DB_PASSWORD**: Kept original (rotated by admin if needed for production)

### How `.env` Is Protected
- `.env` is listed in `.gitignore` (line 125) — **not tracked by git**
- Only `.env.example` is tracked as a template (contains placeholder values only)
- Production secrets MUST be provided via environment variables or a secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault, Kubernetes Secrets)

### How to Generate a New Strong SECRET_KEY

```python
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### Production Deployment Checklist

1. **Set environment variables** (do NOT use a `.env` file in production):
   ```bash
   export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(50))")
   export DEBUG=False
   export ALLOWED_HOSTS=mes.yourdomain.com
   export DB_PASSWORD=<from-secrets-manager>
   ```

2. **Use a secrets manager** for sensitive values:
   - Database credentials
   - SECRET_KEY
   - API keys

3. **Set `DEBUG=False`** in production

4. **Use explicit `ALLOWED_HOSTS`** — never `*` in production

5. **Enable HTTPS** settings from `.env.example`:
   ```
   SECURE_SSL_REDIRECT=True
   SESSION_COOKIE_SECURE=True
   CSRF_COOKIE_SECURE=True
   SECURE_HSTS_SECONDS=31536000
   ```

6. **Rotate `MES_SEED_PASSWORD`** after initial admin account setup

### Audit Performed

- ✅ `.env` file is not in git history
- ✅ `.env.example` contains only placeholder values
- ✅ `.gitignore` properly excludes `.env`
- ✅ Strong SECRET_KEY generated and applied
- ✅ ALLOWED_HOSTS restricted to explicit local hosts
