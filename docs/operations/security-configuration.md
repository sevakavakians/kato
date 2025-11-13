# Security Configuration Guide

Comprehensive guide to securing KATO deployments in production environments.

## Overview

Security is critical for production KATO deployments. This guide covers authentication, authorization, encryption, network security, and compliance requirements.

## Security Layers

```
┌─────────────────────────────────────────┐
│     External Layer (Internet)           │
│  - DDoS Protection (Cloudflare/AWS)     │
│  - Rate Limiting                         │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│     TLS Termination Layer               │
│  - HTTPS/TLS 1.3                        │
│  - Certificate Management               │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│     Application Layer (KATO)            │
│  - API Key Authentication               │
│  - CORS Configuration                   │
│  - Request Validation                   │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│     Internal Network Layer              │
│  - Network Policies                     │
│  - Firewall Rules                       │
│  - Service Isolation                    │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│     Data Layer                          │
│  - Database Authentication              │
│  - Encryption at Rest                   │
│  - Encryption in Transit                │
└─────────────────────────────────────────┘
```

## TLS/HTTPS Configuration

### Certificate Management

#### Using Let's Encrypt (Recommended)

**Docker with Nginx Proxy**:
```yaml
# docker-compose.yml
version: '3.8'

services:
  nginx-proxy:
    image: nginxproxy/nginx-proxy:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/tmp/docker.sock:ro
      - ./certs:/etc/nginx/certs:ro
      - ./vhost:/etc/nginx/vhost.d
      - ./html:/usr/share/nginx/html
    networks:
      - kato-network

  letsencrypt:
    image: nginxproxy/acme-companion:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./certs:/etc/nginx/certs
      - ./vhost:/etc/nginx/vhost.d
      - ./html:/usr/share/nginx/html
      - ./acme:/etc/acme.sh
    environment:
      - DEFAULT_EMAIL=admin@yourdomain.com
    depends_on:
      - nginx-proxy

  kato:
    image: ghcr.io/your-org/kato:latest
    environment:
      - VIRTUAL_HOST=kato.yourdomain.com
      - LETSENCRYPT_HOST=kato.yourdomain.com
      - LETSENCRYPT_EMAIL=admin@yourdomain.com
    networks:
      - kato-network
```

**Kubernetes with cert-manager**:
```yaml
# cert-manager installation
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# ClusterIssuer for Let's Encrypt
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@yourdomain.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
---
# Ingress with automatic TLS
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: kato-ingress
  namespace: kato
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - kato.yourdomain.com
    secretName: kato-tls
  rules:
  - host: kato.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: kato
            port:
              number: 80
```

#### Using Commercial Certificates

```bash
# Generate CSR
openssl req -new -newkey rsa:4096 -nodes \
  -keyout kato.key \
  -out kato.csr \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=kato.yourdomain.com"

# After receiving certificate from CA, create Kubernetes secret
kubectl create secret tls kato-tls \
  --cert=kato.crt \
  --key=kato.key \
  --namespace=kato
```

### TLS Configuration Best Practices

**Nginx Configuration** (`nginx.conf`):
```nginx
server {
    listen 443 ssl http2;
    server_name kato.yourdomain.com;

    # TLS Configuration
    ssl_certificate /etc/nginx/certs/kato.crt;
    ssl_certificate_key /etc/nginx/certs/kato.key;

    # TLS 1.3 only (most secure)
    ssl_protocols TLSv1.3;

    # Strong cipher suites
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers on;

    # OCSP Stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_trusted_certificate /etc/nginx/certs/chain.pem;

    # Session tickets
    ssl_session_tickets off;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Proxy to KATO
    location / {
        proxy_pass http://kato:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name kato.yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

### Test TLS Configuration

```bash
# Test SSL/TLS configuration (should get A+ rating)
curl -I https://kato.yourdomain.com

# Use SSL Labs for comprehensive testing
# Visit: https://www.ssllabs.com/ssltest/analyze.html?d=kato.yourdomain.com

# Test with openssl
openssl s_client -connect kato.yourdomain.com:443 -tls1_3

# Verify certificate chain
openssl s_client -connect kato.yourdomain.com:443 -showcerts
```

## API Authentication

### API Key Authentication

**Implementation** (`kato/api/middleware/auth.py`):
```python
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    """Verify API key from header."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key"
        )

    # Load valid API keys from environment or database
    valid_keys = os.getenv("API_KEYS", "").split(",")

    if api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )

    return api_key
```

**Apply to endpoints**:
```python
from kato.api.middleware.auth import verify_api_key

@app.post("/sessions")
async def create_session(
    request: CreateSessionRequest,
    api_key: str = Depends(verify_api_key)
):
    # Your endpoint logic
    pass
```

**Environment Configuration**:
```bash
# Generate secure API keys
API_KEYS=$(python -c "import secrets; print(','.join([secrets.token_urlsafe(32) for _ in range(5)]))")

# .env
API_KEYS=key1_abc123...,key2_def456...,key3_ghi789...
```

**Client Usage**:
```bash
curl -X POST https://kato.yourdomain.com/sessions \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{"node_id": "user123", "config": {}}'
```

### JWT Authentication

**Implementation** (`kato/api/middleware/jwt_auth.py`):
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta

security = HTTPBearer()

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_access_token(data: dict) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Verify JWT token from Authorization header."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
```

**Environment Configuration**:
```bash
# Generate secret key
JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")

# .env
JWT_SECRET_KEY=your_secret_key_here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=30
```

## CORS Configuration

### Production CORS Settings

**Environment Configuration**:
```bash
# .env.production
CORS_ENABLED=true
CORS_ORIGINS=https://app.yourdomain.com,https://admin.yourdomain.com
CORS_CREDENTIALS=true
CORS_METHODS=GET,POST,PUT,DELETE
CORS_HEADERS=Content-Type,Authorization,X-API-Key
```

**FastAPI Configuration** (`kato/api/main.py`):
```python
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Configure CORS
if os.getenv("CORS_ENABLED", "false").lower() == "true":
    origins = os.getenv("CORS_ORIGINS", "*").split(",")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
        max_age=3600,  # Cache preflight requests for 1 hour
    )
```

### CORS Security Best Practices

1. **Never use `*` in production**:
```bash
# BAD - allows all origins
CORS_ORIGINS=*

# GOOD - explicit origins only
CORS_ORIGINS=https://app.yourdomain.com,https://admin.yourdomain.com
```

2. **Limit methods to required only**:
```bash
CORS_METHODS=GET,POST  # Don't allow DELETE if not needed
```

3. **Use credentials carefully**:
```bash
CORS_CREDENTIALS=true  # Only if you need cookies/auth headers
```

## Database Security

### MongoDB Authentication

**Enable Authentication**:
```bash
# Create admin user
docker exec -it mongo-kb mongo admin
> db.createUser({
    user: "admin",
    pwd: "secure_password_here",
    roles: ["root"]
  })

# Create KATO user
> use kato
> db.createUser({
    user: "kato_user",
    pwd: "kato_password_here",
    roles: [
      { role: "readWrite", db: "kato" }
    ]
  })
```

**Docker Compose with Authentication**:
```yaml
services:
  mongo-kb:
    image: mongo:6.0
    environment:
      MONGO_INITDB_ROOT_USERNAME: admin
      MONGO_INITDB_ROOT_PASSWORD: secure_password_here
    command: --auth
    volumes:
      - ./mongo-init.js:/docker-entrypoint-initdb.d/mongo-init.js:ro

  kato:
    environment:
      MONGO_BASE_URL: mongodb://kato_user:kato_password_here@mongo-kb:27017/kato?authSource=kato
```

**Kubernetes Secret**:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mongodb-secret
  namespace: kato
type: Opaque
stringData:
  username: kato_user
  password: kato_password_here
  connection_string: mongodb://kato_user:kato_password_here@mongo-kb:27017/kato?authSource=kato
```

### MongoDB Encryption at Rest

**Enable Encryption** (MongoDB Enterprise):
```yaml
# docker-compose.yml
services:
  mongo-kb:
    command: >
      --enableEncryption
      --encryptionKeyFile /data/keyfile
      --auth
    volumes:
      - ./mongodb-keyfile:/data/keyfile:ro
```

**Generate Key File**:
```bash
openssl rand -base64 32 > mongodb-keyfile
chmod 600 mongodb-keyfile
```

### Redis Security

**Enable Authentication**:
```yaml
# docker-compose.yml
services:
  redis-kb:
    command: redis-server --requirepass secure_redis_password_here --appendonly yes
```

**Update KATO Configuration**:
```bash
REDIS_URL=redis://:secure_redis_password_here@redis-kb:6379/0
```

**Redis ACL** (Redis 6+):
```bash
# Create ACL user
docker exec -it redis-kb redis-cli
> ACL SETUSER kato_user on >kato_password ~* +@all
> ACL SAVE

# Update connection string
REDIS_URL=redis://kato_user:kato_password@redis-kb:6379/0
```

### Qdrant Security

**Enable API Key**:
```yaml
# docker-compose.yml
services:
  qdrant-kb:
    environment:
      QDRANT__SERVICE__API_KEY: secure_qdrant_api_key_here
```

**Update KATO Configuration**:
```python
# kato/storage/qdrant_manager.py
from qdrant_client import QdrantClient

client = QdrantClient(
    host=os.getenv("QDRANT_HOST"),
    port=os.getenv("QDRANT_PORT"),
    api_key=os.getenv("QDRANT_API_KEY")
)
```

## Network Security

### Docker Network Policies

```yaml
# docker-compose.yml
version: '3.8'

networks:
  kato-backend:
    driver: bridge
    internal: true  # No external access
  kato-frontend:
    driver: bridge

services:
  kato:
    networks:
      - kato-frontend
      - kato-backend

  mongo-kb:
    networks:
      - kato-backend  # Only accessible by KATO

  qdrant-kb:
    networks:
      - kato-backend

  redis-kb:
    networks:
      - kato-backend

  nginx:
    networks:
      - kato-frontend
    ports:
      - "443:443"
```

### Kubernetes Network Policies

**Deny All Traffic by Default**:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: kato
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
```

**Allow KATO to Databases**:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: kato-to-databases
  namespace: kato
spec:
  podSelector:
    matchLabels:
      app: kato
  policyTypes:
  - Egress
  egress:
  # Allow DNS
  - to:
    - namespaceSelector:
        matchLabels:
          name: kube-system
    ports:
    - protocol: UDP
      port: 53
  # Allow MongoDB
  - to:
    - podSelector:
        matchLabels:
          app: mongo-kb
    ports:
    - protocol: TCP
      port: 27017
  # Allow Qdrant
  - to:
    - podSelector:
        matchLabels:
          app: qdrant-kb
    ports:
    - protocol: TCP
      port: 6333
  # Allow Redis
  - to:
    - podSelector:
        matchLabels:
          app: redis-kb
    ports:
    - protocol: TCP
      port: 6379
```

**Allow Ingress to KATO**:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingress-to-kato
  namespace: kato
spec:
  podSelector:
    matchLabels:
      app: kato
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 8000
```

## Secrets Management

### Kubernetes Secrets

```yaml
# secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: kato-secrets
  namespace: kato
type: Opaque
stringData:
  MONGO_USERNAME: kato_user
  MONGO_PASSWORD: secure_mongo_password
  REDIS_PASSWORD: secure_redis_password
  QDRANT_API_KEY: secure_qdrant_key
  API_KEYS: key1,key2,key3
  JWT_SECRET_KEY: secure_jwt_secret
```

**Apply secrets**:
```bash
kubectl apply -f secrets.yaml
```

**Reference in deployment**:
```yaml
spec:
  containers:
  - name: kato
    envFrom:
    - secretRef:
        name: kato-secrets
```

### HashiCorp Vault

**Install Vault Agent**:
```yaml
# vault-agent-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: vault-agent-config
  namespace: kato
data:
  vault-agent-config.hcl: |
    vault {
      address = "https://vault.yourdomain.com"
    }

    auto_auth {
      method {
        type = "kubernetes"
        config = {
          role = "kato"
        }
      }
    }

    template {
      source      = "/vault/configs/kato-config.tpl"
      destination = "/vault/secrets/kato-config"
    }
```

### AWS Secrets Manager

**Python Integration**:
```python
import boto3
import json

def get_secret(secret_name: str) -> dict:
    """Retrieve secret from AWS Secrets Manager."""
    client = boto3.client('secretsmanager', region_name='us-east-1')
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

# Load secrets at startup
secrets = get_secret('kato/production/credentials')
os.environ['MONGO_PASSWORD'] = secrets['mongo_password']
os.environ['API_KEYS'] = secrets['api_keys']
```

## Rate Limiting

### Nginx Rate Limiting

```nginx
# Define rate limit zones
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/m;
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=5r/m;

server {
    listen 443 ssl http2;

    # API endpoints - 100 requests per minute
    location /sessions {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://kato:8000;
    }

    # Authentication endpoints - 5 requests per minute
    location /auth {
        limit_req zone=auth_limit burst=3 nodelay;
        proxy_pass http://kato:8000;
    }
}
```

### FastAPI Rate Limiting

**Install slowapi**:
```bash
pip install slowapi
```

**Implementation**:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/sessions")
@limiter.limit("100/minute")
async def create_session(request: Request):
    # Your endpoint logic
    pass
```

## Security Auditing

### Enable Audit Logging

**MongoDB Audit Log** (Enterprise):
```yaml
services:
  mongo-kb:
    command: >
      --auditDestination file
      --auditFormat JSON
      --auditPath /var/log/mongodb/audit.json
      --auditFilter '{"atype": {"$in": ["authenticate", "authCheck"]}}'
```

**KATO Audit Logging**:
```python
# kato/api/middleware/audit.py
import logging

audit_logger = logging.getLogger("audit")

@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    """Log all API requests for audit trail."""
    start_time = time.time()

    response = await call_next(request)

    duration = time.time() - start_time
    audit_logger.info({
        "timestamp": datetime.utcnow().isoformat(),
        "client_ip": request.client.host,
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration * 1000,
        "user_agent": request.headers.get("user-agent"),
        "api_key": request.headers.get("x-api-key", "anonymous")[:10] + "..."
    })

    return response
```

### Vulnerability Scanning

```bash
# Scan Docker images
trivy image ghcr.io/your-org/kato:latest

# Scan Python dependencies
pip install safety
safety check -r requirements.txt

# Scan for secrets in code
pip install detect-secrets
detect-secrets scan --all-files
```

## Compliance

### GDPR Compliance

**Data Retention Policy**:
```python
# kato/workers/data_retention.py
from datetime import datetime, timedelta

async def cleanup_old_data(processor_id: str, retention_days: int = 90):
    """Delete data older than retention period."""
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    # Delete old patterns
    await kb.patterns.delete_many({
        "processor_id": processor_id,
        "created_at": {"$lt": cutoff_date}
    })

    # Delete old sessions
    await redis.delete(*[
        key for key in await redis.keys(f"session:{processor_id}:*")
        if await redis.ttl(key) < 0
    ])
```

**Data Export** (Right to Data Portability):
```python
@app.get("/users/{user_id}/export")
async def export_user_data(user_id: str):
    """Export all user data in machine-readable format."""
    data = {
        "patterns": await kb.get_patterns(user_id),
        "sessions": await session_manager.get_user_sessions(user_id),
        "metadata": await kb.get_user_metadata(user_id)
    }
    return JSONResponse(content=data)
```

**Data Deletion** (Right to be Forgotten):
```python
@app.delete("/users/{user_id}")
async def delete_user_data(user_id: str):
    """Permanently delete all user data."""
    await kb.delete_user_patterns(user_id)
    await session_manager.delete_user_sessions(user_id)
    await redis.delete(f"user:{user_id}:*")
    return {"status": "deleted"}
```

## Security Checklist

### Infrastructure
- [ ] TLS 1.3 enabled with strong cipher suites
- [ ] A+ rating on SSL Labs
- [ ] HSTS header configured
- [ ] DDoS protection enabled
- [ ] Rate limiting configured
- [ ] Firewall rules restrictive (whitelist only)

### Authentication & Authorization
- [ ] API key authentication enabled
- [ ] Strong API keys generated (32+ characters)
- [ ] API keys rotated regularly (90 days)
- [ ] Database authentication enabled
- [ ] Secrets stored in vault (not environment files)

### Data Protection
- [ ] Encryption at rest enabled
- [ ] Encryption in transit (TLS) enforced
- [ ] Backup encryption enabled
- [ ] Sensitive data masked in logs
- [ ] Data retention policy enforced

### Network Security
- [ ] Network policies configured
- [ ] Internal services not exposed externally
- [ ] Service-to-service authentication
- [ ] Network segmentation implemented

### Monitoring & Auditing
- [ ] Audit logging enabled
- [ ] Security alerts configured
- [ ] Failed authentication monitoring
- [ ] Anomaly detection active
- [ ] Regular security scans scheduled

### Compliance
- [ ] GDPR compliance verified (if applicable)
- [ ] Data processing agreements signed
- [ ] Privacy policy published
- [ ] Terms of service published
- [ ] Incident response plan documented

## Related Documentation

- [Production Checklist](production-checklist.md)
- [Environment Variables](environment-variables.md)
- [Monitoring](monitoring.md)
- [Docker Deployment](docker-deployment.md)
- [Kubernetes Deployment](kubernetes-deployment.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
