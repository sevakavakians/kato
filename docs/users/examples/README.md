# KATO Examples

Practical examples demonstrating KATO usage patterns.

## Available Examples

### Basic Examples

1. **[Simple Chatbot](chatbot-simple.py)**: Basic conversational pattern learning
2. **[Workflow Predictor](workflow-predictor.py)**: Sequential workflow tracking
3. **[User Preferences](user-preferences.py)**: Non-temporal profile learning

### Intermediate Examples

4. **[Error Diagnosis](error-diagnosis.py)**: Error-solution pattern matching
5. **[Recommendation System](recommendations.py)**: Content recommendation
6. **[Session Auto-Reconnect](auto-reconnect.py)**: Resilient session management

### Advanced Examples

7. **[Multi-Modal Learning](multi-modal.py)**: Combining text, vectors, emotives
8. **[Streaming Analytics](streaming-analytics.py)**: Real-time pattern discovery
9. **[Batch Processing](batch-processing.py)**: Bulk operations

## Running Examples

### Prerequisites

```bash
# 1. Start KATO
./start.sh

# 2. Install Python dependencies
pip install requests numpy  # Add others as needed
```

### Run an Example

```bash
# Basic usage
python docs/users/examples/chatbot-simple.py

# With custom configuration
python docs/users/examples/workflow-predictor.py --node-id my_workflow

# Help
python docs/users/examples/error-diagnosis.py --help
```

## Example Structure

Each example includes:
- **Description**: What it demonstrates
- **Use Case**: Real-world application
- **Code**: Fully functional Python script
- **Output**: Expected results
- **Cleanup**: How to remove test data

## Contributing Examples

To add a new example:

1. Create `example-name.py` in this directory
2. Follow existing example structure
3. Add entry to this README
4. Test with clean KATO installation
5. Submit pull request

## Example Categories

### Pattern Types

- **Temporal sequences**: Time-ordered workflows
- **Non-temporal profiles**: Associations, preferences
- **Hybrid patterns**: Combined temporal + associative

### Integration Patterns

- **REST API**: Direct HTTP calls
- **Python client**: Using KATOClient wrapper
- **Async operations**: High-throughput processing
- **Error handling**: Resilient implementations

### Advanced Techniques

- **Auto-learning**: Automatic pattern discovery
- **Multi-session**: Shared knowledge bases
- **Custom metrics**: Application-specific ranking
- **Emotive tracking**: Emotional context

---

**Last Updated**: November 2025
**KATO Version**: 3.0+
