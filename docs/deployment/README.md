# KATO Deployment Documentation

This directory contains guides for deploying KATO in various environments.

## Available Guides

### Current Deployment

- **[Docker Deployment Guide](DOCKER.md)** - Complete guide for Docker-based deployment
  - Quick start with docker compose
  - Container management
  - Multi-instance deployment
  - Health checks and monitoring
  - Troubleshooting

- **[Architecture Guide](ARCHITECTURE.md)** - Deployment architecture overview
  - System components
  - Network topology
  - Resource requirements
  - Scalability considerations

- **[Configuration Guide](CONFIGURATION.md)** - Environment and configuration management
  - Environment variables
  - Configuration files
  - Security settings
  - Performance tuning

### Future Planning

- **[Production Scale Migration Plan (PSMP)](PRODUCTION_SCALE_MIGRATION_PLAN.md)** - Future scaling strategy
  - **Status**: Planning document, not yet implemented
  - **Purpose**: Production-scale deployment with Gunicorn + Uvicorn or Kubernetes
  - **When to use**: Traffic exceeds 100 req/sec or multi-user production deployment needed
  - **Phases**:
    - Phase 0: Quick fix (increase request limit) - 1 day
    - Phase 1: Gunicorn + Uvicorn multi-worker - 2 weeks
    - Phase 2: Nginx reverse proxy + SSL - 4 weeks
    - Phase 3: Monitoring & observability - 1 month
    - Phase 4: Kubernetes migration - 3+ months

## Quick Start

### Development

```bash
# Start KATO with default configuration
./start.sh

# Access API
curl http://localhost:8000/health
```

### Production (Current)

```bash
# Build production image
docker compose build --no-cache

# Start all services
docker compose up -d

# Check status
docker compose ps
```

### Production (Future - PSMP)

When you're ready to scale to production with multi-worker support, see the [Production Scale Migration Plan (PSMP)](PRODUCTION_SCALE_MIGRATION_PLAN.md).

## Deployment Options Comparison

| Approach | Use Case | Complexity | Scalability | Current Status |
|----------|----------|------------|-------------|----------------|
| **Docker Compose** | Development, Testing, Small deployments | Low | Manual | ✅ Implemented |
| **Gunicorn + Uvicorn** | Production on VMs, Medium traffic | Medium | Manual horizontal | 📋 Planned (PSMP Phase 1) |
| **Kubernetes** | Cloud-native, High scale, Auto-scaling | High | Automatic horizontal | 📋 Planned (PSMP Phase 4) |

## When to Upgrade

Consider upgrading your deployment approach when:

- **Phase 0 (Quick Fix)**: Training sessions interrupted by worker restarts
- **Phase 1 (Multi-Worker)**: Single CPU core can't handle request load
- **Phase 2 (Nginx + SSL)**: Need SSL/TLS, rate limiting, or load balancing
- **Phase 3 (Monitoring)**: Need production observability and metrics
- **Phase 4 (Kubernetes)**: Need auto-scaling, high availability, cloud-native features

## Related Documentation

- [Multi-Instance Guide](../MULTI_INSTANCE_GUIDE.md) - Running multiple KATO instances
- [Configuration Management](../CONFIGURATION_MANAGEMENT.md) - Advanced configuration
- [Performance Optimization](../technical/PERFORMANCE.md) - Performance tuning
- [Troubleshooting Guide](../technical/TROUBLESHOOTING.md) - Common issues and solutions

## Support

For deployment questions:
- Check the [Troubleshooting Guide](../technical/TROUBLESHOOTING.md)
- Review [Technical Documentation](../technical/)
- Open an issue on GitHub
