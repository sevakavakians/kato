# KATO Network Topology Patterns Guide

## Overview

KATO instances are independent services that users can connect in various network topologies through custom orchestration code. **KATO itself does not manage these connections** - users implement the routing, data flow, and coordination logic in their applications.

This guide provides patterns and examples for building orchestration layers that connect multiple KATO instances in different network topologies.

## Prerequisites

Before implementing network topologies, ensure you understand:
- [Multi-Instance Management](MULTI_INSTANCE_GUIDE.md) - How to run multiple KATO instances
- [API Reference](../users/api-reference.md) - KATO's HTTP API endpoints
- [Core Concepts](CONCEPTS.md) - KATO's behavior and data structures

## KATO Instance Independence

Each KATO instance operates as an isolated processor with its own:
- **HTTP API endpoint** (e.g., `http://localhost:8001`, `http://localhost:8002`)
- **Independent short-term memory** and learned patterns
- **Separate session management** with isolated state
- **Individual configuration** (recall threshold, max predictions, etc.)

Users build orchestration layers that connect these instances by:
- Writing routing logic to direct observations to appropriate instances
- Aggregating predictions from multiple instances
- Managing data flow between instances
- Implementing coordination protocols

## Common Topology Patterns

### 1. Linear Pipeline (Sequential Processing)

**Description**: Simple chain where each instance processes data and passes results to the next.

**Topology Diagram**:
```
node_input → node_validate → node_process → node_output
```

**Use Case**: Multi-stage data processing with validation and transformation steps.

**Implementation Example**:
```python
import requests

# Define your pipeline nodes
nodes = [
    "http://localhost:8001",  # Input processor
    "http://localhost:8002",  # Validation processor
    "http://localhost:8003",  # Processing processor
    "http://localhost:8004"   # Output processor
]

def pipeline_process(initial_observation):
    """Process observation through linear pipeline"""
    current_data = initial_observation

    for node_url in nodes:
        # Send observation to current node
        response = requests.post(
            f"{node_url}/observe",
            json=current_data
        )

        # Get predictions to pass to next node
        predictions = requests.get(f"{node_url}/predictions").json()

        # Transform predictions into next observation
        if predictions:
            current_data = {
                "strings": predictions[0]["future"][0] if predictions[0]["future"] else [],
                "vectors": [],
                "emotives": predictions[0].get("emotives", {})
            }

    return current_data

# Usage
result = pipeline_process({
    "strings": ["initial_input"],
    "vectors": [],
    "emotives": {}
})
```

---

### 2. Branching/Tree Structure (Parallel Processing)

**Description**: One instance feeds multiple downstream instances for parallel processing paths.

**Topology Diagram**:
```
node_sensor_input → node_parser →┬→ node_temperature_analysis → node_alert
                                 ├→ node_humidity_analysis → node_control
                                 └→ node_pressure_analysis → node_forecast
```

**Use Case**: Distribute sensor data to specialized analysis pipelines.

**Implementation Example**:
```python
def branch_processing(observation, parser_url, branches):
    """Send data to parser, then branch to multiple processors"""
    # Parse input
    parser_response = requests.post(f"{parser_url}/observe", json=observation)
    predictions = requests.get(f"{parser_url}/predictions").json()

    # Branch to multiple processors in parallel
    results = {}
    for branch_name, branch_url in branches.items():
        branch_data = {
            "strings": predictions[0]["future"][0] if predictions else [],
            "vectors": [],
            "emotives": {}
        }
        response = requests.post(f"{branch_url}/observe", json=branch_data)
        results[branch_name] = requests.get(f"{branch_url}/predictions").json()

    return results

# Usage
branches = {
    "temperature": "http://localhost:8002",
    "humidity": "http://localhost:8003",
    "pressure": "http://localhost:8004"
}

results = branch_processing(
    observation={"strings": ["sensor_data"], "vectors": [], "emotives": {}},
    parser_url="http://localhost:8001",
    branches=branches
)
```

---

### 3. Merging/Convergence (Aggregation)

**Description**: Multiple instances feed into a single aggregator instance.

**Topology Diagram**:
```
node_weather_data →┐
node_traffic_data →┼→ node_aggregator → node_decision
node_event_data   →┘
```

**Use Case**: Combine insights from multiple data sources for unified decision-making.

**Implementation Example**:
```python
def merge_processing(source_nodes, aggregator_url):
    """Collect predictions from multiple sources and aggregate"""
    all_predictions = []

    # Gather predictions from all source nodes
    for source_name, source_url in source_nodes.items():
        predictions = requests.get(f"{source_url}/predictions").json()
        all_predictions.extend(predictions)

    # Create aggregated observation
    aggregated_strings = []
    for pred in all_predictions:
        if pred.get("future"):
            aggregated_strings.extend(pred["future"][0])

    # Send to aggregator
    aggregated_observation = {
        "strings": list(set(aggregated_strings)),  # Unique strings
        "vectors": [],
        "emotives": {}
    }

    response = requests.post(
        f"{aggregator_url}/observe",
        json=aggregated_observation
    )

    return requests.get(f"{aggregator_url}/predictions").json()

# Usage
sources = {
    "weather": "http://localhost:8001",
    "traffic": "http://localhost:8002",
    "events": "http://localhost:8003"
}

final_decision = merge_processing(sources, "http://localhost:8004")
```

---

### 4. Mesh Network (Flexible Connectivity)

**Description**: Instances can communicate with multiple other instances non-hierarchically.

**Topology Diagram**:
```
Each node can query or send data to any other node as needed
```

**Use Case**: Dynamic routing based on prediction content or confidence levels.

**Implementation Example**:
```python
class MeshNetwork:
    def __init__(self, nodes):
        """Initialize mesh with node URLs"""
        self.nodes = {name: url for name, url in nodes.items()}

    def route_observation(self, observation, source_node):
        """Route observation based on predictions from source"""
        source_url = self.nodes[source_node]

        # Process at source
        requests.post(f"{source_url}/observe", json=observation)
        predictions = requests.get(f"{source_url}/predictions").json()

        if not predictions:
            return None

        # Determine routing based on prediction confidence
        best_pred = max(predictions, key=lambda p: p.get("confidence", 0))

        # Route to specialized nodes based on content
        if "temperature" in str(best_pred.get("future", [])):
            target = "temp_specialist"
        elif "pressure" in str(best_pred.get("future", [])):
            target = "pressure_specialist"
        else:
            target = "general_processor"

        # Send to target node
        target_url = self.nodes[target]
        target_observation = {
            "strings": best_pred["future"][0] if best_pred.get("future") else [],
            "vectors": [],
            "emotives": best_pred.get("emotives", {})
        }

        requests.post(f"{target_url}/observe", json=target_observation)
        return requests.get(f"{target_url}/predictions").json()

# Usage
mesh = MeshNetwork({
    "input": "http://localhost:8001",
    "temp_specialist": "http://localhost:8002",
    "pressure_specialist": "http://localhost:8003",
    "general_processor": "http://localhost:8004"
})

result = mesh.route_observation(
    {"strings": ["sensor_reading"], "vectors": [], "emotives": {}},
    "input"
)
```

---

### 5. Hub and Spoke (Centralized Coordination)

**Description**: Central hub coordinates multiple peripheral instances.

**Topology Diagram**:
```
node_sensor_1 →┐
node_sensor_2 →┼→ node_central_hub →┬→ node_actuator_1
node_sensor_3 →┘                    └→ node_actuator_2
```

**Use Case**: Central coordinator aggregates sensor inputs and dispatches to actuators.

**Implementation Example**:
```python
class HubAndSpoke:
    def __init__(self, hub_url, sensors, actuators):
        self.hub_url = hub_url
        self.sensors = sensors  # Dict of sensor name -> URL
        self.actuators = actuators  # Dict of actuator name -> URL

    def process_cycle(self):
        """Gather from sensors, process at hub, dispatch to actuators"""
        # Collect from sensors
        sensor_data = []
        for sensor_name, sensor_url in self.sensors.items():
            predictions = requests.get(f"{sensor_url}/predictions").json()
            sensor_data.extend(predictions)

        # Aggregate at hub
        hub_strings = []
        for pred in sensor_data:
            if pred.get("future"):
                hub_strings.extend(pred["future"][0])

        hub_observation = {
            "strings": list(set(hub_strings)),
            "vectors": [],
            "emotives": {}
        }

        requests.post(f"{self.hub_url}/observe", json=hub_observation)
        hub_predictions = requests.get(f"{self.hub_url}/predictions").json()

        # Dispatch to actuators
        results = {}
        for actuator_name, actuator_url in self.actuators.items():
            if hub_predictions:
                actuator_observation = {
                    "strings": hub_predictions[0].get("future", [[]])[0],
                    "vectors": [],
                    "emotives": hub_predictions[0].get("emotives", {})
                }
                requests.post(f"{actuator_url}/observe", json=actuator_observation)
                results[actuator_name] = requests.get(f"{actuator_url}/predictions").json()

        return results

# Usage
hub_spoke = HubAndSpoke(
    hub_url="http://localhost:8001",
    sensors={
        "sensor1": "http://localhost:8002",
        "sensor2": "http://localhost:8003",
        "sensor3": "http://localhost:8004"
    },
    actuators={
        "actuator1": "http://localhost:8005",
        "actuator2": "http://localhost:8006"
    }
)

actuator_results = hub_spoke.process_cycle()
```

---

### 6. Cyclic/Feedback Loops (Iterative Refinement)

**Description**: Instances form cycles for iterative processing and continuous learning.

**Topology Diagram**:
```
node_predictor → node_evaluator → node_adjuster → (back to) node_predictor
```

**Use Case**: Reinforcement learning loops where output quality is evaluated and fed back for improvement.

**Implementation Example**:
```python
def feedback_loop(initial_observation, nodes, max_iterations=5, threshold=0.9):
    """Iteratively process through feedback loop until threshold met"""
    current_data = initial_observation
    iteration = 0

    while iteration < max_iterations:
        # Predictor
        requests.post(f"{nodes['predictor']}/observe", json=current_data)
        predictions = requests.get(f"{nodes['predictor']}/predictions").json()

        if not predictions:
            break

        # Evaluator
        eval_observation = {
            "strings": predictions[0].get("future", [[]])[0],
            "vectors": [],
            "emotives": predictions[0].get("emotives", {})
        }
        requests.post(f"{nodes['evaluator']}/observe", json=eval_observation)
        eval_predictions = requests.get(f"{nodes['evaluator']}/predictions").json()

        # Check if quality threshold met
        if eval_predictions and eval_predictions[0].get("confidence", 0) >= threshold:
            return eval_predictions[0]

        # Adjuster - prepare feedback for next iteration
        adjust_observation = {
            "strings": eval_predictions[0].get("future", [[]])[0] if eval_predictions else [],
            "vectors": [],
            "emotives": {"adjustment": -0.5}  # Negative emotive for correction
        }
        requests.post(f"{nodes['adjuster']}/observe", json=adjust_observation)
        adjust_predictions = requests.get(f"{nodes['adjuster']}/predictions").json()

        # Feed back to predictor
        if adjust_predictions:
            current_data = {
                "strings": adjust_predictions[0].get("future", [[]])[0],
                "vectors": [],
                "emotives": {}
            }

        iteration += 1

    return None  # Failed to converge

# Usage
nodes = {
    "predictor": "http://localhost:8001",
    "evaluator": "http://localhost:8002",
    "adjuster": "http://localhost:8003"
}

result = feedback_loop(
    initial_observation={"strings": ["initial_input"], "vectors": [], "emotives": {}},
    nodes=nodes,
    max_iterations=5,
    threshold=0.9
)
```

---

### 7. Hierarchical/Layered (Abstraction Layers)

**Description**: Instances organized in layers of abstraction, with higher layers processing outputs from lower layers.

**Topology Diagram**:
```
Layer 3: node_decision_maker
Layer 2: node_pattern_analyzer_1, node_pattern_analyzer_2
Layer 1: node_feature_extractor_1, node_feature_extractor_2, node_feature_extractor_3
Layer 0: node_raw_input_1, node_raw_input_2
```

**Use Case**: Complex data processing pipelines with feature extraction, pattern analysis, and high-level decision making.

**Implementation Example**:
```python
class HierarchicalProcessor:
    def __init__(self, layers):
        """Initialize hierarchical processor with layer definitions"""
        self.layers = layers  # Dict of layer_name -> list of node URLs

    def process_hierarchical(self, initial_observations):
        """Process through all layers from bottom to top"""
        current_layer_data = initial_observations

        for layer_name in sorted(self.layers.keys()):
            layer_nodes = self.layers[layer_name]
            next_layer_data = []

            # Process each node in current layer
            for node_url in layer_nodes:
                # Distribute observations across layer nodes
                for observation in current_layer_data:
                    requests.post(f"{node_url}/observe", json=observation)

                # Collect predictions from this node
                predictions = requests.get(f"{node_url}/predictions").json()

                # Transform predictions into observations for next layer
                for pred in predictions:
                    if pred.get("future"):
                        next_layer_data.append({
                            "strings": pred["future"][0],
                            "vectors": [],
                            "emotives": pred.get("emotives", {})
                        })

            # Move to next layer
            current_layer_data = next_layer_data

        return current_layer_data

# Usage
hierarchy = HierarchicalProcessor({
    "layer_0_input": [
        "http://localhost:8001",
        "http://localhost:8002"
    ],
    "layer_1_features": [
        "http://localhost:8003",
        "http://localhost:8004",
        "http://localhost:8005"
    ],
    "layer_2_patterns": [
        "http://localhost:8006",
        "http://localhost:8007"
    ],
    "layer_3_decision": [
        "http://localhost:8008"
    ]
})

initial_data = [
    {"strings": ["raw_input_1"], "vectors": [], "emotives": {}},
    {"strings": ["raw_input_2"], "vectors": [], "emotives": {}}
]

final_decisions = hierarchy.process_hierarchical(initial_data)
```

---

## Complete Orchestration Framework

For more complex topologies, use a generic orchestration framework:

```python
import requests
import logging
from typing import Dict, List, Callable

class KatoOrchestrator:
    """Generic orchestrator for KATO instance topologies"""

    def __init__(self, nodes: Dict[str, str]):
        """
        Initialize orchestrator with node definitions.

        Args:
            nodes: Dict mapping node names to their API URLs
        """
        self.nodes = nodes
        self.logger = logging.getLogger(__name__)

    def send_observation(self, node_name: str, observation: dict) -> dict:
        """Send observation to specific node"""
        try:
            url = self.nodes[node_name]
            response = requests.post(f"{url}/observe", json=observation, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Error sending to {node_name}: {e}")
            return {}

    def get_predictions(self, node_name: str) -> List[dict]:
        """Get predictions from specific node"""
        try:
            url = self.nodes[node_name]
            response = requests.get(f"{url}/predictions", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Error getting predictions from {node_name}: {e}")
            return []

    def learn_pattern(self, node_name: str) -> dict:
        """Trigger learning on specific node"""
        try:
            url = self.nodes[node_name]
            response = requests.post(f"{url}/learn", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Error triggering learn on {node_name}: {e}")
            return {}

    def clear_stm(self, node_name: str) -> dict:
        """Clear short-term memory on specific node"""
        try:
            url = self.nodes[node_name]
            response = requests.post(f"{url}/clear-stm", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Error clearing STM on {node_name}: {e}")
            return {}

    def execute_topology(self,
                        initial_data: dict,
                        topology_func: Callable) -> dict:
        """
        Execute custom topology function.

        Args:
            initial_data: Starting observation
            topology_func: User-defined function implementing topology logic

        Returns:
            Final result from topology execution
        """
        return topology_func(self, initial_data)

# Usage example
def my_custom_topology(orchestrator, data):
    """User-defined topology logic"""
    # Step 1: Send to input processor
    orchestrator.send_observation("node1", data)
    predictions = orchestrator.get_predictions("node1")

    # Step 2: Route to specialized processor
    if predictions and predictions[0].get("confidence", 0) > 0.7:
        next_data = {
            "strings": predictions[0]["future"][0] if predictions[0].get("future") else [],
            "vectors": [],
            "emotives": {}
        }
        orchestrator.send_observation("node2", next_data)
        return orchestrator.get_predictions("node2")

    return predictions

orchestrator = KatoOrchestrator({
    "node1": "http://localhost:8001",
    "node2": "http://localhost:8002",
    "node3": "http://localhost:8003"
})

result = orchestrator.execute_topology(
    initial_data={"strings": ["start"], "vectors": [], "emotives": {}},
    topology_func=my_custom_topology
)
```

## Implementation Considerations

When building topology orchestration layers, consider these important factors:

### 1. Error Handling
Implement robust retry logic and fallback mechanisms:
```python
def resilient_request(url, data, max_retries=3):
    """Request with retry logic"""
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=data, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff
```

### 2. Monitoring
Track node health, response times, and data flow:
```python
import time

def monitored_send(node_url, observation):
    """Send with performance monitoring"""
    start_time = time.time()
    response = requests.post(f"{node_url}/observe", json=observation)
    latency = time.time() - start_time

    logger.info(f"Node {node_url} responded in {latency:.3f}s")
    return response.json()
```

### 3. Load Balancing
Distribute load across multiple instances handling the same role:
```python
from itertools import cycle

class LoadBalancer:
    def __init__(self, node_pool):
        self.pool = cycle(node_pool)

    def get_next_node(self):
        return next(self.pool)
```

### 4. Session Management
Decide on session strategy:
- **Separate sessions per node**: Complete isolation
- **Shared sessions across nodes**: Maintain context across topology

### 5. Data Validation
Validate data formats between nodes:
```python
def validate_observation(data):
    """Ensure observation has required fields"""
    required = ["strings", "vectors", "emotives"]
    return all(key in data for key in required)
```

### 6. Logging
Implement comprehensive logging for tracing data flow:
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger('topology')
logger.info(f"Routing observation from node1 to node2")
```

### 7. Configuration
Externalize node URLs and routing rules:
```yaml
# topology_config.yaml
nodes:
  input_processor: http://localhost:8001
  validator: http://localhost:8002
  analyzer: http://localhost:8003

routing_rules:
  high_confidence_threshold: 0.8
  max_retries: 3
  timeout_seconds: 5
```

## Best Practices

### Design Principles

1. **Keep Nodes Stateless**: Each KATO instance should be independently restartable without affecting the topology

2. **Use Sessions Appropriately**:
   - Create sessions per user/context, not per topology node
   - Share session IDs across nodes when maintaining context is important

3. **Implement Health Checks**:
   ```python
   def check_node_health(node_url):
       try:
           response = requests.get(f"{node_url}/health", timeout=2)
           return response.status_code == 200
       except:
           return False
   ```

4. **Handle Partial Failures**: Design topologies to gracefully handle node failures
   ```python
   def resilient_branch(nodes, observation):
       results = {}
       for name, url in nodes.items():
           try:
               results[name] = send_observation(url, observation)
           except Exception as e:
               logger.warning(f"Node {name} failed: {e}")
               results[name] = None  # Continue with other nodes
       return results
   ```

5. **Monitor Data Flow**: Log data transformations at each topology stage

6. **Test Individually**: Test each node in isolation before connecting in topologies

7. **Document Routing Logic**: Clearly document how data flows through your topology
   ```python
   """
   Topology: Weather Alert System

   Flow:
   1. sensor_nodes -> data_aggregator (merge)
   2. data_aggregator -> pattern_analyzer (process)
   3. pattern_analyzer -> alert_dispatcher (branch)
      - High severity -> immediate_alert
      - Medium severity -> scheduled_alert
      - Low severity -> log_only
   """
   ```

### Performance Optimization

1. **Use Async/Await for Parallel Operations**:
   ```python
   import asyncio
   import aiohttp

   async def parallel_send(nodes, observation):
       async with aiohttp.ClientSession() as session:
           tasks = [
               session.post(f"{url}/observe", json=observation)
               for url in nodes
           ]
           return await asyncio.gather(*tasks)
   ```

2. **Batch Operations When Possible**: Use `/observe-sequence` for bulk operations

3. **Cache Node Configurations**: Avoid repeated configuration queries

4. **Monitor Bottlenecks**: Identify slow nodes and optimize or replicate them

### Security Considerations

1. **Validate Node URLs**: Ensure URLs point to trusted KATO instances
2. **Use HTTPS in Production**: Encrypt data in transit
3. **Implement Authentication**: Use API keys or tokens if exposing publicly
4. **Rate Limiting**: Prevent overwhelming nodes with requests

## Troubleshooting

### Common Issues

**Problem**: Node becomes unresponsive
```python
# Solution: Implement circuit breaker pattern
class CircuitBreaker:
    def __init__(self, failure_threshold=3):
        self.failure_count = 0
        self.threshold = failure_threshold
        self.is_open = False

    def call(self, func):
        if self.is_open:
            raise Exception("Circuit breaker is open")

        try:
            result = func()
            self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            if self.failure_count >= self.threshold:
                self.is_open = True
            raise
```

**Problem**: Data format mismatch between nodes
```python
# Solution: Use standardized data schemas
from pydantic import BaseModel

class KatoObservation(BaseModel):
    strings: List[str]
    vectors: List[List[float]]
    emotives: Dict[str, float]
```

**Problem**: Topology becomes too complex to debug
```python
# Solution: Add topology visualization
def visualize_topology(orchestrator):
    """Print topology graph"""
    print("Topology Map:")
    for node_name, url in orchestrator.nodes.items():
        health = "✓" if check_node_health(url) else "✗"
        print(f"  {health} {node_name}: {url}")
```

## Example: Complete Multi-Stage System

Here's a complete example combining multiple patterns:

```python
import requests
import logging
from typing import Dict, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MultiStageSystem:
    """Complete multi-stage KATO topology"""

    def __init__(self, config: Dict):
        self.nodes = config["nodes"]
        self.thresholds = config["thresholds"]

    def process(self, raw_data: Dict) -> Dict:
        """Process through complete pipeline"""

        # Stage 1: Input validation (Linear)
        logger.info("Stage 1: Validation")
        validated = self._validate(raw_data)

        # Stage 2: Parallel feature extraction (Branching)
        logger.info("Stage 2: Feature extraction")
        features = self._extract_features(validated)

        # Stage 3: Aggregation (Merging)
        logger.info("Stage 3: Aggregation")
        aggregated = self._aggregate(features)

        # Stage 4: Decision making (Hub)
        logger.info("Stage 4: Decision")
        decision = self._decide(aggregated)

        return decision

    def _validate(self, data: Dict) -> Dict:
        """Validation stage"""
        url = self.nodes["validator"]
        requests.post(f"{url}/observe", json=data)
        return requests.get(f"{url}/predictions").json()

    def _extract_features(self, data: Dict) -> Dict[str, List]:
        """Parallel feature extraction"""
        extractors = ["feature_1", "feature_2", "feature_3"]
        results = {}

        for extractor in extractors:
            url = self.nodes[extractor]
            requests.post(f"{url}/observe", json=data)
            results[extractor] = requests.get(f"{url}/predictions").json()

        return results

    def _aggregate(self, features: Dict[str, List]) -> Dict:
        """Aggregate features"""
        all_strings = []
        for feature_predictions in features.values():
            for pred in feature_predictions:
                if pred.get("future"):
                    all_strings.extend(pred["future"][0])

        aggregated = {
            "strings": list(set(all_strings)),
            "vectors": [],
            "emotives": {}
        }

        url = self.nodes["aggregator"]
        requests.post(f"{url}/observe", json=aggregated)
        return requests.get(f"{url}/predictions").json()

    def _decide(self, aggregated: List) -> Dict:
        """Make final decision"""
        url = self.nodes["decision"]

        if aggregated:
            decision_data = {
                "strings": aggregated[0].get("future", [[]])[0],
                "vectors": [],
                "emotives": aggregated[0].get("emotives", {})
            }
        else:
            decision_data = {"strings": [], "vectors": [], "emotives": {}}

        requests.post(f"{url}/observe", json=decision_data)
        return requests.get(f"{url}/predictions").json()

# Configuration
config = {
    "nodes": {
        "validator": "http://localhost:8001",
        "feature_1": "http://localhost:8002",
        "feature_2": "http://localhost:8003",
        "feature_3": "http://localhost:8004",
        "aggregator": "http://localhost:8005",
        "decision": "http://localhost:8006"
    },
    "thresholds": {
        "confidence": 0.7,
        "max_retries": 3
    }
}

# Usage
system = MultiStageSystem(config)
result = system.process({
    "strings": ["input_data"],
    "vectors": [],
    "emotives": {}
})

logger.info(f"Final result: {result}")
```

## Next Steps

- Review [Multi-Instance Guide](MULTI_INSTANCE_GUIDE.md) for managing KATO instances
- See [API Reference](../users/api-reference.md) for complete endpoint documentation
- Read [Core Concepts](CONCEPTS.md) to understand KATO's behavior
- Check [Performance Guide](technical/PERFORMANCE.md) for optimization strategies

---

*For questions or feedback on topology patterns, see the [main KATO documentation](../README.md).*
