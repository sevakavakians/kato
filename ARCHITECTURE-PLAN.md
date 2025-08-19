
     Architecture Overview

     A centralized REST gateway that maintains sticky routing to ensure requests for a specific processor always go to the same KATO instance, preserving stateful sequence processing.

                         ┌─────────────────┐
                         │   REST Client   │
                         └────────┬────────┘
                                  │ HTTP/REST
                                  ▼ Port 8000
                     ┌────────────────────────────────┐
                     │    REST API Gateway            │
                     │   (Separate Container)         │
                     │                                │
                     │ • Processor Registry           │
                     │ • Sticky Routing (by ID)       │
                     │ • Connection Pool Management   │
                     │ • Health Monitoring            │
                     └───┬────────┬───────────────┬───┘
                         │        │               │
                   processor_id   processor_id    processor_id
                   "p46b6b076c"   "pd5d9e6c4c"   "p847675347"
                         │        │               │
                         ▼        ▼               ▼
                 ┌──────────┐ ┌──────────┐ ┌──────────┐
                 │  KATO    │ │  KATO    │ │  KATO    │
                 │Instance 1│ │Instance 2│ │Instance 3│
                 │gRPC:1441 │ │gRPC:1442 │ │gRPC:1443 │
                 └──────────┘ └──────────┘ └──────────┘

     Implementation Details

     1. Create Standalone REST Gateway Service

     File Structure:
     kato-gateway/
     ├── Dockerfile
     ├── requirements.txt
     ├── gateway/
     │   ├── __init__.py
     │   ├── main.py
     │   ├── config.py
     │   ├── router.py
     │   ├── handlers.py
     │   ├── grpc_client.py
     │   └── registry.py

     2. Processor Registry & Routing

     registry.py - Maintains processor-to-instance mapping:
     class ProcessorRegistry:
         def __init__(self):
             self.processors = {}  # processor_id -> gRPC endpoint
             self.connections = {}  # processor_id -> gRPC channel
             
         def register_processor(self, processor_id, grpc_endpoint):
             """Register a processor with its gRPC endpoint"""
             self.processors[processor_id] = grpc_endpoint
             
         def get_channel(self, processor_id):
             """Get or create gRPC channel for processor (sticky)"""
             if processor_id not in self.connections:
                 endpoint = self.processors.get(processor_id)
                 if endpoint:
                     self.connections[processor_id] = grpc.insecure_channel(endpoint)
             return self.connections.get(processor_id)

     3. Configuration Options

     Option A: Static Configuration (config.yaml)
     processors:
       - id: "p46b6b076c"
         name: "P1"
         grpc_endpoint: "kato-instance-1:1441"
         
       - id: "pd5d9e6c4c"
         name: "P2"  
         grpc_endpoint: "kato-instance-2:1441"
         
       - id: "p847675347"
         name: "P3"
         grpc_endpoint: "kato-instance-3:1441"

     Option B: Environment-Based Discovery
     # Discover from Docker/Kubernetes labels or environment
     KATO_PROCESSORS = {
         "p46b6b076c": "kato-1:1441",
         "pd5d9e6c4c": "kato-2:1441",
         "p847675347": "kato-3:1441"
     }

     4. REST Endpoint Handlers

     Complete endpoint mapping for all test requirements:

     # handlers.py
     class KatoRESTHandler:
         def __init__(self, registry):
             self.registry = registry
             
         # Working Memory Operations
         async def clear_working_memory(self, processor_id):
             channel = self.registry.get_channel(processor_id)
             stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
             response = stub.ClearWorkingMemory(Empty())
             return format_response(processor_id, "wm-cleared")
         
         async def get_working_memory(self, processor_id):
             channel = self.registry.get_channel(processor_id)
             stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
             response = stub.GetWorkingMemory(Empty())
             return format_response(processor_id, response.wm)
         
         # Predictions
         async def get_predictions(self, processor_id, unique_id=None):
             channel = self.registry.get_channel(processor_id)
             stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
             request = UniqueId(unique_id=unique_id) if unique_id else Empty()
             response = stub.GetPredictions(request)
             return format_predictions_response(processor_id, response)
         
         # Gene/Parameter Management
         async def get_gene(self, processor_id, gene_name):
             channel = self.registry.get_channel(processor_id)
             stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
             request = Gene(name=gene_name)
             response = stub.GetGene(request)
             return format_gene_response(processor_id, gene_name, response)
         
         async def update_genes(self, processor_id, gene_updates):
             channel = self.registry.get_channel(processor_id)
             stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
             request = GeneData(genes=gene_updates)
             response = stub.UpdateGenes(request)
             return format_response(processor_id, "genes-updated")
         
         async def increment_recall_threshold(self, processor_id, increment):
             channel = self.registry.get_channel(processor_id)
             stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
             request = Increment(increment=increment)
             response = stub.IncrementRecallThreshold(request)
             return format_response(processor_id, response.value)

     5. Routing Logic

     router.py - FastAPI implementation:
     from fastapi import FastAPI, HTTPException
     from fastapi.responses import JSONResponse

     app = FastAPI()
     handler = KatoRESTHandler(registry)

     @app.post("/{processor_id}/observe")
     async def observe(processor_id: str, data: dict):
         """Route observation to specific processor"""
         if not registry.has_processor(processor_id):
             raise HTTPException(404, f"Processor {processor_id} not found")
         return await handler.observe(processor_id, data)

     @app.post("/{processor_id}/working-memory/clear")
     async def clear_working_memory(processor_id: str):
         """Clear working memory for specific processor"""
         return await handler.clear_working_memory(processor_id)

     @app.get("/{processor_id}/working-memory")
     async def get_working_memory(processor_id: str):
         """Get working memory from specific processor"""
         return await handler.get_working_memory(processor_id)

     @app.post("/{processor_id}/predictions")
     async def get_predictions(processor_id: str, body: dict = None):
         """Get predictions from specific processor"""
         unique_id = body.get('unique_id') if body else None
         return await handler.get_predictions(processor_id, unique_id)

     @app.get("/{processor_id}/gene/{gene_name}")
     async def get_gene(processor_id: str, gene_name: str):
         """Get gene value from specific processor"""
         return await handler.get_gene(processor_id, gene_name)

     @app.post("/{processor_id}/genes/change")
     async def update_genes(processor_id: str, genes: dict):
         """Update genes for specific processor"""
         return await handler.update_genes(processor_id, genes)

     6. Docker Compose Configuration

     docker-compose.yml:
     version: '3.8'

     services:
       # REST Gateway - Single instance
       rest-gateway:
         build: ./kato-gateway
         container_name: kato-rest-gateway
         ports:
           - "8000:8000"
         environment:
           - LOG_LEVEL=INFO
           - KATO_P1=kato-p1:1441
           - KATO_P2=kato-p2:1441
           - KATO_P3=kato-p3:1441
         networks:
           - kato-network
         depends_on:
           - kato-p1
           - kato-p2
           - kato-p3

       # KATO Instance 1 (Processor P1)
       kato-p1:
         image: kato:latest
         container_name: kato-p1
         environment:
           - PORT=1441
           - MANIFEST={"id":"p46b6b076c","name":"P1",...}
           - MONGO_BASE_URL=mongodb://mongodb:27017
         networks:
           - kato-network
         depends_on:
           - mongodb

       # KATO Instance 2 (Processor P2)
       kato-p2:
         image: kato:latest
         container_name: kato-p2
         environment:
           - PORT=1441
           - MANIFEST={"id":"pd5d9e6c4c","name":"P2",...}
           - MONGO_BASE_URL=mongodb://mongodb:27017
         networks:
           - kato-network
         depends_on:
           - mongodb

       # KATO Instance 3 (Processor P3)
       kato-p3:
         image: kato:latest
         container_name: kato-p3
         environment:
           - PORT=1441
           - MANIFEST={"id":"p847675347","name":"P3",...}
           - MONGO_BASE_URL=mongodb://mongodb:27017
         networks:
           - kato-network
         depends_on:
           - mongodb

       mongodb:
         image: mongo:4.4
         container_name: mongo-kb
         networks:
           - kato-network

     networks:
       kato-network:
         driver: bridge

     7. Key Features

     1. Sticky Routing: Each processor_id always routes to the same KATO instance
     2. Connection Pooling: Reuse gRPC connections per processor
     3. Health Checks: Monitor KATO instance availability
     4. Error Handling: Graceful degradation if instance unavailable
     5. Metrics: Track request counts, latencies per processor
     6. Discovery: Support both static and dynamic processor registration

     8. Migration Steps

     1. Remove REST gateway from kato_engine.py
       - Keep only gRPC server in KATO instances
       - Remove REST_PORT configuration
     2. Create new gateway project
       - Implement all REST endpoints
       - Add processor registry
       - Implement sticky routing
     3. Update kato-manager.sh
       - Remove REST port mapping from KATO instances
       - Add gateway startup logic
       - Update health checks
     4. Update tests
       - Point all tests to gateway port 8000
       - No changes needed to test logic

     Benefits of This Architecture

     1. Preserves Statefulness: Each processor's sequence processing remains intact
     2. Single Entry Point: One REST port for all processors
     3. Scalable: Can add/remove KATO instances without changing client code
     4. Maintainable: REST logic separated from core KATO processing
     5. Flexible: Easy to add new endpoints or modify REST behavior
     6. Production Ready: Follows microservices best practices

     Testing Strategy

     1. Unit Tests: Test gateway routing logic
     2. Integration Tests: Test gateway-to-KATO communication
     3. End-to-End Tests: Run existing test suite through gateway
     4. Performance Tests: Verify no significant latency added

     This architecture maintains the stateful nature of KATO while providing a clean, scalable REST interface!
