# KATO Security Guidelines

## Overview

Security best practices for developing, deploying, and maintaining KATO.

## Table of Contents
1. [Security Principles](#security-principles)
2. [Development Security](#development-security)
3. [Deployment Security](#deployment-security)
4. [Data Security](#data-security)
5. [Incident Response](#incident-response)

## Security Principles

### Defense in Depth

- Multiple security layers
- Input validation at all levels
- Least privilege access
- Fail securely
- Keep dependencies updated

### Security by Design

- Security considered from start
- Threat modeling for new features
- Security reviews in code review
- Regular security audits

## Development Security

### Secrets Management

❌ **Never do this:**
```python
# Hardcoded secrets (NEVER!)
CLICKHOUSE_HOST = "clickhouse"
CLICKHOUSE_PASSWORD = "password123"
API_KEY = "sk-abc123..."
```

✅ **Use environment variables:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    clickhouse_host: str
    clickhouse_password: str
    api_key: str

    class Config:
        env_file = ".env"

# .env file (never committed)
CLICKHOUSE_HOST=clickhouse
CLICKHOUSE_PASSWORD=secure_password
API_KEY=sk-...

# .gitignore
.env
secrets/
credentials.json
```

### Input Validation

```python
from pydantic import BaseModel, validator, Field

class ObservationRequest(BaseModel):
    strings: list[str] = Field(..., max_items=1000)
    vectors: list[list[float]] = Field(default_factory=list)
    emotives: dict[str, float] = Field(default_factory=dict)

    @validator("strings")
    def validate_strings(cls, v):
        if any(len(s) > 10000 for s in v):
            raise ValueError("String too long (max 10000 chars)")
        return v

    @validator("emotives")
    def validate_emotives(cls, v):
        for value in v.values():
            if not -1.0 <= value <= 1.0:
                raise ValueError("Emotive values must be in [-1, 1]")
        return v
```

### SQL Injection Prevention

```python
# ClickHouse (use parameterized queries)
# Good
patterns = clickhouse_client.query(
    "SELECT * FROM patterns_data WHERE kb_id = %(kb_id)s",
    {"kb_id": kb_id}
)

# Bad (string concatenation)
# query = f"SELECT * FROM patterns_data WHERE kb_id = '{kb_id}'"
```

### Authentication & Authorization

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )

@app.post("/sessions")
async def create_session(user=Depends(verify_token)):
    # user is authenticated
    ...
```

## Deployment Security

### Environment Configuration

```yaml
# docker-compose.yml
services:
  kato:
    image: ghcr.io/sevakavakians/kato:3.0.0
    environment:
      - CLICKHOUSE_HOST=${CLICKHOUSE_HOST}  # From environment
      - CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD}
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    secrets:
      - clickhouse_password
    # Don't expose unnecessary ports
    ports:
      - "127.0.0.1:8000:8000"  # Bind to localhost only

secrets:
  clickhouse_password:
    file: ./secrets/clickhouse_password.txt
```

### HTTPS/TLS

```nginx
server {
    listen 443 ssl http2;
    server_name kato.example.com;

    ssl_certificate /etc/ssl/certs/kato.crt;
    ssl_certificate_key /etc/ssl/private/kato.key;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://kato:8000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Network Security

```yaml
# Kubernetes NetworkPolicy
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: kato-network-policy
spec:
  podSelector:
    matchLabels:
      app: kato
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: api-gateway
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: clickhouse
    ports:
    - protocol: TCP
      port: 9000
```

## Data Security

### Encryption at Rest

```python
from cryptography.fernet import Fernet

class EncryptedStorage:
    def __init__(self, encryption_key: bytes):
        self.cipher = Fernet(encryption_key)

    def encrypt_pattern(self, pattern: dict) -> dict:
        """Encrypt sensitive pattern data."""
        sensitive_fields = ["metadata", "private_data"]
        encrypted = pattern.copy()

        for field in sensitive_fields:
            if field in encrypted:
                data = json.dumps(encrypted[field])
                encrypted[field] = self.cipher.encrypt(data.encode()).decode()

        return encrypted

    def decrypt_pattern(self, pattern: dict) -> dict:
        """Decrypt pattern data."""
        decrypted = pattern.copy()

        for field in ["metadata", "private_data"]:
            if field in decrypted:
                encrypted_data = decrypted[field].encode()
                data = self.cipher.decrypt(encrypted_data).decode()
                decrypted[field] = json.loads(data)

        return decrypted
```

### Data Access Control

```python
class DataAccessController:
    """Control access to sensitive data."""

    def can_access_pattern(self, user_id: str, pattern: dict) -> bool:
        """Check if user can access pattern."""
        # Node-based access control
        pattern_node_id = pattern["node_id"]

        if pattern_node_id.startswith(f"user:{user_id}"):
            return True

        # Team access
        if self.is_team_member(user_id, pattern_node_id):
            return True

        return False

    def filter_patterns(self, user_id: str, patterns: list) -> list:
        """Return only patterns user can access."""
        return [p for p in patterns if self.can_access_pattern(user_id, p)]
```

### PII Handling

```python
import hashlib

def anonymize_user_id(user_id: str) -> str:
    """Hash user ID for privacy."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:16]

def redact_pii(text: str) -> str:
    """Remove PII from text."""
    # Remove email addresses
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)

    # Remove phone numbers
    text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', text)

    return text
```

## Incident Response

### Security Incident Process

1. **Detect** - Monitor for security events
2. **Contain** - Isolate affected systems
3. **Investigate** - Determine scope and impact
4. **Remediate** - Fix vulnerability
5. **Document** - Record incident details
6. **Review** - Post-mortem and improvements

### Reporting Vulnerabilities

```markdown
# SECURITY.md

## Reporting Security Issues

**Do not report security vulnerabilities through public GitHub issues.**

Please report security vulnerabilities to: security@example.com

Include:
- Description of vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will respond within 48 hours.
```

### Incident Checklist

```markdown
- [ ] Incident detected and confirmed
- [ ] Team notified
- [ ] Affected systems identified
- [ ] Systems contained/isolated
- [ ] Root cause identified
- [ ] Fix developed and tested
- [ ] Fix deployed
- [ ] Users notified (if applicable)
- [ ] Documentation updated
- [ ] Post-mortem conducted
```

## Security Checklist

### Development

- [ ] No secrets in code
- [ ] Input validation on all endpoints
- [ ] Parameterized queries (no SQL injection)
- [ ] Authentication implemented
- [ ] Authorization checked
- [ ] Dependencies scanned
- [ ] Code reviewed for security

### Deployment

- [ ] HTTPS/TLS enabled
- [ ] Secrets in environment variables
- [ ] Minimal container images
- [ ] Network policies configured
- [ ] Logging enabled
- [ ] Monitoring configured
- [ ] Backups encrypted

### Operations

- [ ] Dependencies updated regularly
- [ ] Security patches applied
- [ ] Access logs reviewed
- [ ] Vulnerability scans run
- [ ] Incident response plan tested
- [ ] Team trained on security

## Tools

```bash
# Dependency scanning
pip-audit

# SAST (Static Analysis)
bandit -r kato/

# Secrets scanning
gitleaks detect

# Container scanning
trivy image ghcr.io/sevakavakians/kato:latest

# License compliance
pip-licenses
```

## Related Documentation

- [Vulnerability Management](vulnerability-management.md)
- [Dependency Management](dependency-management.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
