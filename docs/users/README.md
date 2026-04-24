# KATO User Documentation

**Audience**: Application developers integrating KATO into their systems

Welcome to the KATO user documentation! This section helps you get started with KATO, understand how it works, and integrate it into your applications.

## 📚 Documentation Overview

### Getting Started
- **[Quick Start Guide](quick-start.md)** - Get KATO running in 5 minutes
- **[Installation Guide](installation.md)** - Detailed installation instructions
- **[Your First KATO Session](first-session.md)** - Step-by-step tutorial

### Core Documentation
- **[Core Concepts](concepts.md)** - Understanding KATO's behavior and principles
- **[API Reference](api-reference.md)** - Complete API endpoint documentation
- **[Database Persistence](database-persistence.md)** - How data persists across sessions
- **[Configuration Guide](configuration.md)** - All configuration options explained

### Practical Guides
- **[Python Client Library](python-client.md)** - Using KATO with Python
- **[Session Management](session-management.md)** - Managing sessions and state
- **[Pattern Learning](pattern-learning.md)** - How to train KATO effectively
- **[Working with Predictions](predictions.md)** - Understanding and using predictions
- **[Parallel Processing](parallel-processing.md)** - Multi-worker training and concurrent serving

### Reference
- **[Troubleshooting](troubleshooting.md)** - Common issues and solutions
- **[FAQ](faq.md)** - Frequently asked questions
- **[Examples](examples/)** - Code examples and use cases
- **[Migration Guides](migrations/)** - Upgrading between versions

## 🎯 Quick Navigation by Task

### I want to...
- **Get started quickly** → [Quick Start Guide](quick-start.md)
- **Understand how KATO works** → [Core Concepts](concepts.md)
- **Look up an API endpoint** → [API Reference](api-reference.md)
- **Integrate KATO into my app** → [Python Client Library](python-client.md)
- **Run training or serving in parallel** → [Parallel Processing](parallel-processing.md)
- **Understand data persistence** → [Database Persistence](database-persistence.md)
- **Fix a problem** → [Troubleshooting](troubleshooting.md)
- **See code examples** → [Examples](examples/)

## 💡 Key Concepts (Quick Reference)

**Sessions**: Temporary workspaces that expire (default: 1 hour)
- Create with `node_id` to connect to persistent patterns
- Each session has isolated short-term memory
- Sessions share long-term memory per `node_id`

**Observations**: Multi-modal inputs (strings, vectors, emotions)
- Strings are alphanumerically sorted within events
- Vectors are converted to hash-based names
- Emotives provide emotional context

**Patterns**: Learned sequences from observations
- Stored permanently
- Identified by SHA1 hash
- Include frequency, emotives, and metadata

**Predictions**: KATO's forecasts based on current observations
- Structured as past/present/future segments
- Include missing/extras for gap analysis
- Ranked by potential (default) or other metrics

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
