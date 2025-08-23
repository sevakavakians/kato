"""
gRPC client for communicating with KATO instances
"""

import logging
import time
from typing import Dict, List, Any, Optional
import grpc
from google.protobuf import empty_pb2, json_format
from google.protobuf.struct_pb2 import ListValue

logger = logging.getLogger(__name__)

# Import KATO protobuf definitions
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
try:
    import kato_proc_pb2
    import kato_proc_pb2_grpc
except ImportError as e:
    logger.error(f"Failed to import protobuf definitions: {e}")
    # Fallback for development
    kato_proc_pb2 = None
    kato_proc_pb2_grpc = None


class KatoGrpcClient:
    """
    gRPC client for communicating with KATO instances.
    Handles all gRPC calls and response formatting.
    """
    
    def __init__(self, registry):
        self.registry = registry
        
    async def ping(self, processor_id: str) -> Dict[str, Any]:
        """Ping a specific processor"""
        channel = self.registry.get_channel(processor_id)
        if not channel:
            raise ValueError(f"Processor {processor_id} not available")
        
        stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
        request = empty_pb2.Empty()
        
        try:
            response = stub.GetName(request)
            return {
                "id": processor_id,
                "interval": response.interval,
                "time_stamp": response.time_stamp,
                "status": "okay",
                "message": "okay"
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error for ping {processor_id}: {e}")
            raise
    
    async def observe(self, processor_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send observation to a processor"""
        channel = self.registry.get_channel(processor_id)
        if not channel:
            raise ValueError(f"Processor {processor_id} not available")
        
        stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
        
        # Create observation request
        request = kato_proc_pb2.Observation()
        request.unique_id = data.get('unique_id', f'rest-{int(time.time() * 1000000)}')
        
        # Add strings
        if 'strings' in data:
            request.strings.extend(data['strings'])
        
        # Add vectors
        if 'vectors' in data:
            for vector in data['vectors']:
                if isinstance(vector, list):
                    list_value = ListValue()
                    for v in vector:
                        list_value.values.add().number_value = float(v)
                    request.vectors.append(list_value)
        
        # Add emotives
        if 'emotives' in data:
            for key, value in data['emotives'].items():
                request.emotives[key] = float(value)
        
        try:
            response = stub.Observe(request, timeout=30)
            return {
                "id": processor_id,
                "interval": response.interval,
                "time_stamp": response.time_stamp,
                "status": "okay",
                "message": {
                    "status": "observed",
                    "auto_learned_model": response.auto_learned_model if hasattr(response, 'auto_learned_model') else ""
                },
                "unique_id": response.unique_id
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error for observe {processor_id}: {e}")
            raise
    
    async def clear_all_memory(self, processor_id: str) -> Dict[str, Any]:
        """Clear all memory for a processor"""
        channel = self.registry.get_channel(processor_id)
        if not channel:
            raise ValueError(f"Processor {processor_id} not available")
        
        stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
        request = empty_pb2.Empty()
        
        try:
            response = stub.ClearAllMemory(request)
            return {
                "id": processor_id,
                "interval": response.interval if hasattr(response, 'interval') else 0,
                "time_stamp": time.time(),
                "status": "okay",
                "message": "all-cleared"
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error for clear_all_memory {processor_id}: {e}")
            raise
    
    async def clear_working_memory(self, processor_id: str) -> Dict[str, Any]:
        """Clear working memory for a processor"""
        channel = self.registry.get_channel(processor_id)
        if not channel:
            raise ValueError(f"Processor {processor_id} not available")
        
        stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
        request = empty_pb2.Empty()
        
        try:
            response = stub.ClearWorkingMemory(request)
            return {
                "id": processor_id,
                "interval": response.interval if hasattr(response, 'interval') else 0,
                "time_stamp": time.time(),
                "status": "okay",
                "message": "wm-cleared"
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error for clear_working_memory {processor_id}: {e}")
            raise
    
    async def get_working_memory(self, processor_id: str) -> Dict[str, Any]:
        """Get working memory from a processor"""
        channel = self.registry.get_channel(processor_id)
        if not channel:
            raise ValueError(f"Processor {processor_id} not available")
        
        stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
        request = empty_pb2.Empty()
        
        try:
            response = stub.GetWorkingMemory(request)
            # Extract working memory from the Struct response
            wm_data = []
            if hasattr(response, 'response') and response.response:
                # Convert the Struct to a dictionary using protobuf's json_format
                struct_dict = json_format.MessageToDict(response.response,
                                                        always_print_fields_with_no_presence=True)
                wm_data = struct_dict.get('data', [])
            return {
                "id": processor_id,
                "interval": response.interval if hasattr(response, 'interval') else 0,
                "time_stamp": time.time(),
                "status": "okay",
                "message": wm_data
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error for get_working_memory {processor_id}: {e}")
            raise
    
    async def learn(self, processor_id: str) -> Dict[str, Any]:
        """Trigger learning for a processor"""
        channel = self.registry.get_channel(processor_id)
        if not channel:
            raise ValueError(f"Processor {processor_id} not available")
        
        stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
        request = empty_pb2.Empty()
        
        try:
            response = stub.Learn(request)
            return {
                "id": processor_id,
                "interval": response.interval if hasattr(response, 'interval') else 0,
                "time_stamp": time.time(),
                "status": "okay",
                "message": response.message
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error for learn {processor_id}: {e}")
            raise
    
    async def get_predictions(self, processor_id: str, unique_id: Optional[str] = None) -> Dict[str, Any]:
        """Get predictions from a processor"""
        channel = self.registry.get_channel(processor_id)
        if not channel:
            raise ValueError(f"Processor {processor_id} not available")
        
        stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
        
        if unique_id:
            request = kato_proc_pb2.UniqueId(unique_id=unique_id)
        else:
            request = empty_pb2.Empty()
        
        try:
            response = stub.GetPredictions(request)
            
            # Format predictions
            predictions = []
            for pred in response.predictions:
                prediction_dict = {
                    "name": pred.name,
                    "confidence": pred.confidence,
                    "evidence": pred.evidence,
                    "frequency": pred.frequency,
                    "potential": pred.potential,
                    "confluence": pred.confluence,
                    "entropy": pred.entropy,
                    "fragmentation": pred.fragmentation,
                    "hamiltonian": pred.hamiltonian,
                    "grand_hamiltonian": pred.grand_hamiltonian,
                    "itfdf_similarity": pred.itfdf_similarity,
                    "similarity": pred.similarity,
                    "snr": pred.snr,
                    "matches": list(pred.matches),
                    "extras": list(pred.extras)
                }
                predictions.append(prediction_dict)
            
            return {
                "id": processor_id,
                "interval": response.interval if hasattr(response, 'interval') else 0,
                "time_stamp": time.time(),
                "status": "okay",
                "message": predictions
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error for get_predictions {processor_id}: {e}")
            raise
    
    async def get_gene(self, processor_id: str, gene_name: str) -> Dict[str, Any]:
        """Get a gene value from a processor"""
        channel = self.registry.get_channel(processor_id)
        if not channel:
            raise ValueError(f"Processor {processor_id} not available")
        
        stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
        request = kato_proc_pb2.Gene(name=gene_name)
        
        try:
            response = stub.GetGene(request)
            return {
                "id": processor_id,
                "interval": 0,
                "time_stamp": time.time(),
                "status": "okay",
                "message": response.value
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error for get_gene {processor_id}/{gene_name}: {e}")
            raise
    
    async def update_genes(self, processor_id: str, genes: Dict[str, Any]) -> Dict[str, Any]:
        """Update genes for a processor"""
        channel = self.registry.get_channel(processor_id)
        if not channel:
            raise ValueError(f"Processor {processor_id} not available")
        
        stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
        request = kato_proc_pb2.GeneData(genes=genes)
        
        try:
            response = stub.UpdateGenes(request)
            return {
                "id": processor_id,
                "interval": 0,
                "time_stamp": time.time(),
                "status": "okay",
                "message": "genes-updated"
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error for update_genes {processor_id}: {e}")
            raise
    
    async def increment_recall_threshold(self, processor_id: str, increment: float = 0.01) -> Dict[str, Any]:
        """Increment recall threshold for a processor"""
        channel = self.registry.get_channel(processor_id)
        if not channel:
            raise ValueError(f"Processor {processor_id} not available")
        
        stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
        request = kato_proc_pb2.Increment(increment=increment)
        
        try:
            response = stub.IncrementRecallThreshold(request)
            return {
                "id": processor_id,
                "interval": 0,
                "time_stamp": time.time(),
                "status": "okay",
                "message": response.value
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error for increment_recall_threshold {processor_id}: {e}")
            raise
    
    async def get_status(self, processor_id: str) -> Dict[str, Any]:
        """Get status of a processor"""
        channel = self.registry.get_channel(processor_id)
        if not channel:
            raise ValueError(f"Processor {processor_id} not available")
        
        stub = kato_proc_pb2_grpc.KatoEngineStub(channel)
        request = empty_pb2.Empty()
        
        try:
            response = stub.ShowStatus(request)
            
            # Convert the Struct response to a dictionary
            status_dict = {}
            if hasattr(response, 'response') and response.response:
                status_dict = json_format.MessageToDict(response.response,
                                                        always_print_fields_with_no_presence=True)
            
            return {
                "id": processor_id,
                "interval": response.interval if hasattr(response, 'interval') else 0,
                "time_stamp": time.time(),
                "status": "okay",
                "message": status_dict
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error for get_status {processor_id}: {e}")
            raise