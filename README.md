# KATO
**Knowledge Abstraction for Traceable Outcomes**

> *Transparent memory and abstraction for agentic AI systems — deterministic, explainable, and emotive-aware.*

Because in AI, memory without traceability or understanding is just confusion.

![alt text](assets/kato-graphic.png "KATO crystal")
---

## 🚀 Overview
**KATO** is a specialized AI module designed to provide **deterministic memory, abstraction, and recall** for modern agentic AI systems.  
It combines:

- **Knowledge Abstraction** – Converts raw inputs into structured, higher-level representations.
- **Traceable Outcomes** – Every result is fully explainable and linked back to its source.
- **Emotive Awareness** – Captures and processes emotional context (“emotives”) alongside factual knowledge.

KATO is derived from the heritage of the **GAIuS** framework, retaining its most valuable core — a **transparent, symbolic, and physics-informed learning process** — while focusing on a single critical component:  
a **rote memorizer and abstracter** that excels at clarity, precision, and accountability.

Like GAIuS before it, KATO adheres to [ExCITE AI](https://medium.com/@sevakavakians/what-is-excite-ai-712afd372af4) principles.

---

## ✨ Features
- **Deterministic Learning** – No randomness; same inputs always yield the same outputs.
- **Full Transparency** – All internal states and transformations are inspectable.
- **Multi-Modal Support** – Works with text, vision, sensor data, and more.
- **Emotive Processing** – Associates data with emotional context when relevant.
- **Explainable Outputs** – Every abstraction and decision is linked to traceable input sequences.
- **Temporal Sequence Modeling** – Sophisticated past/present/future segmentation in predictions.
- **Alphanumeric Event Sorting** – Consistent ordering within events while preserving sequence order.

## 🧪 Testing

KATO includes a comprehensive test suite with 76+ tests covering unit, integration, and API functionality.

### Running Tests

```bash
# Navigate to test directory
cd kato-tests

# Run all tests
./run_tests.sh

# Run specific test categories
./run_tests.sh --unit          # Unit tests only
./run_tests.sh --integration   # Integration tests only
./run_tests.sh --api           # API tests only

# Run with options
./run_tests.sh --verbose       # Verbose output
./run_tests.sh --parallel      # Run tests in parallel
```

### Test Coverage

- **Unit Tests**: Observations, memory management, model hashing, predictions, sorting behavior
- **Integration Tests**: End-to-end sequence learning, recall, and complex scenarios
- **API Tests**: REST endpoints, error handling, and protocol compliance

### Key Test Features

- **Deterministic Hash Verification**: Validates MODEL| and VECTOR| prefix consistency
- **Sorting Behavior**: Tests KATO's alphanumeric sorting within events
- **Stateful Testing**: Captures KATO's sequence learning and memory persistence
- **Multi-modal Support**: Tests strings, vectors, and emotives processing

For detailed test documentation, see [TEST_DOCUMENTATION.md](TEST_DOCUMENTATION.md).

### Core Behaviors

#### Sequence Processing
- **Event Structure**: Observations are organized as events containing multiple symbols/strings
- **Alphanumeric Sorting**: Strings within each event are sorted alphanumerically
- **Sequence Preservation**: The order of events in a sequence is always preserved
- **Empty Events**: Empty observations are ignored and don't change state

#### Prediction Structure
KATO's predictions use sophisticated temporal segmentation:
- **Past**: Events before the current matching state
- **Present**: All contiguous events identified by matching symbols (partial matches supported)
- **Future**: Events after the present state
- **Missing**: Symbols expected in present events but not observed
- **Extras**: Symbols observed but not expected in present events

For detailed behavior documentation, see [KATO_BEHAVIOR_DOCUMENTATION.md](kato-tests-v2/KATO_BEHAVIOR_DOCUMENTATION.md).

# Architecture Summary

## High-Level Summary

Kato is a framework for building and running artificially intelligent agents. It is based on a distributed, message-passing architecture where multiple "kato processors" can be networked together to form a larger kato system. The system is designed to be deployed in Docker containers.

## Core Components

*   **Kato Processor (`KatoProcessor` class):** This is the main program of the system. Each kato processor is an independent agent with its own "genome" that defines its characteristics and behavior. It can perceive its environment, learn from experience, and make predictions.

*   **gRPC Server (`KatoEngineServicer`):** Each kato processor runs a gRPC server that exposes the `KatoEngine` service. This service provides a well-defined API for interacting with the kato processor, allowing other components to send it observations, issue commands, and inspect its internal state.

*   **Modeler (`Modeler` class):** This is the core of the kato processor's learning and prediction capabilities. It maintains a working memory of recent events, learns new models from this memory, and uses these models to generate predictions about future events.

*   **Classifier (`Classifier` class):** This component is responsible for processing raw input data (specifically, vectors) and classifying it into a set of known symbols. This is a form of feature extraction that simplifies the input for the `Modeler`.

*   **Knowledge Base:** The system uses a knowledge base (likely MongoDB, as suggested by the `README.md`) to store learned models and other persistent data. The `Modeler` interacts with the knowledge base to save and retrieve information.

*   **NodeClient:** This is a gRPC client that allows kato processors to communicate with each other. This enables the creation of complex, multi-agent systems where processors can collaborate and exchange information.

## Architectural Patterns

*   **Microservices-like Architecture:** The system is composed of small, independent services (the kato processors) that communicate over a network using a well-defined API (gRPC). This allows for scalability and flexibility.

*   **Message-Passing:** The kato processors communicate by passing messages to each other. This is a common pattern in distributed systems and allows for loose coupling between components.

*   **Event-Driven Architecture:** The kato processors are driven by events, which can be observations from the environment or messages from other processors. The `observe` method is the primary event handler.

*   **Component-Based Design:** The `KatoProcessor` is composed of several smaller, more specialized components (the `Modeler`, `Classifier`, etc.). This makes the system easier to understand, maintain, and extend.

## Data Flow

1.  **Observation:** An external entity or another kato processor sends an observation to a kato processor's gRPC server via the `Observe` RPC.
2.  **Processing Pipeline:** The observation may be passed through a pipeline of operations before being processed by the target kato processor. This is defined by `InputPipeline` and can include LLMs, SLMs, neural network or GPT processes.
3.  **Symbolization:** The `Classifier` processes the raw data in the observation and converts it into a set of symbols.
4.  **Modeling and Prediction:** The `Modeler` receives the symbols, updates its working memory, and generates predictions based on its learned models.
5.  **Action/Communication:** The kato processor can then take action based on the predictions, which may involve sending messages to other kato processors via the `NodeClient`.

## Deployment

The system is designed to be deployed in Docker containers. The `Dockerfile` defines the container image, and `supervisord` is used to manage the `cp-engine` process within the container. This makes it easy to deploy and manage the system in a variety of environments.

---
