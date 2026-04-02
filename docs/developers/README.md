# KATO Developer Documentation

**Audience**: Developers contributing to KATO's codebase

Welcome to the KATO developer documentation! This section provides everything you need to contribute to KATO effectively.

## 📚 Documentation Overview

### Getting Started
- **[Contributing Guide](contributing.md)** - How to contribute to KATO
- **[Development Setup](development-setup.md)** - Setting up your development environment
- **[Code Style Guide](code-style.md)** - Coding standards and conventions
- **[Git Workflow](git-workflow.md)** - Branching, commits, and pull requests

### Architecture & Design
- **[Architecture Overview](architecture.md)** - System design and component interaction
- **[Hybrid Architecture](hybrid-architecture.md)** - ClickHouse + Redis hybrid design
- **[KB ID Isolation](kb-id-isolation.md)** - Node isolation via `kb_id` partitioning
- **[Code Organization](code-organization.md)** - Where code lives and why
- **[Data Flow](data-flow.md)** - How data moves through the system
- **[Design Patterns](design-patterns.md)** - Patterns used in KATO

### Development Guides
- **[Testing Guide](testing.md)** - Running and writing tests
- **[Debugging Guide](debugging.md)** - Common debugging scenarios
- **[Logging Guide](logging-guide.md)** - Logging usage and conventions
- **[Performance Profiling](performance-profiling.md)** - Optimizing KATO
- **[Database Management](database-management.md)** - Working with ClickHouse, Redis, and Qdrant

### Projects
- **[GPU Optimization](gpu/)** - GPU acceleration project (Phase 1-2 complete, Phase 3 awaiting hardware)

## 🎯 Quick Navigation by Task

### I want to...
- **Start contributing** → [Contributing Guide](contributing.md)
- **Understand the architecture** → [Architecture Overview](architecture.md)
- **Find specific code** → [Code Organization](code-organization.md)
- **Run tests** → [Testing Guide](testing.md)
- **Debug an issue** → [Debugging Guide](debugging.md)
- **Add a new feature** → [Adding Endpoints](adding-endpoints.md)
- **Optimize performance** → [Performance Profiling](performance-profiling.md)

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
