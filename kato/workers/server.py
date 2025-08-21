"""This module contains the code that implements the gRPC server stub."""
import time
import traceback
from ast import literal_eval
from itertools import chain
from os import environ

from google.protobuf import json_format
from google.protobuf.internal.well_known_types import ListValue
from google.protobuf.struct_pb2 import Struct
from kato.kato_proc_pb2 import ModelObject

from kato import kato_proc_pb2_grpc, kato_proc_pb2

import logging

logger = logging.getLogger('kato.server')
logger.setLevel(getattr(logging, environ['LOG_LEVEL']))
logger.info('logging initiated')


# noinspection PyBroadException
class KatoEngineServicer(kato_proc_pb2_grpc.KatoEngineServicer):
    def __init__(self, primitive):
        self.primitive = primitive

    def GetName(self, request, context):
        logger.debug(f'request={request} context={context}')
        return kato_proc_pb2.StandardResponse(
            status=kato_proc_pb2.StandardResponse.OKAY,
            id=self.primitive.id,
            interval=self.primitive.time,
            time_stamp=time.time(),
            message=self.primitive.name,
        )

    def Instruct(self, request, context):
        "Do not use"
        return
    
    def Observe(self, request, context):
        """Get observations from Agent-API (percepts/models/strings, utilities, actions)."""
        logger.debug(f'request={request} context={context}')
        try:
            # Use the correct parameter name for protobuf 6.x
            data = json_format.MessageToDict(request, preserving_proto_field_name=True, always_print_fields_with_no_presence=True)
            # data['vectors'] = [list(v.values()) for v in data['vectors']]
            logger.info(f"Observe data after conversion: {data}")
            logger.debug(data)
            unique_id = self.primitive.observe(data)
            logger.info(f"After observe - WM contents: {self.primitive.modeler.WM}")

            m = "observed"
            return kato_proc_pb2.ObservationResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=m,
                unique_id=unique_id,
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def Mobserve(self, request, context):
        """Get observations from Manipulatives (percepts/models/strings, utilities, actions)."""
        logger.debug(f'request={request} context={context}')
        try:
            vectors = [list(v.items()) for v in request.vectors]
            data = json_format.MessageToDict(request, preserving_proto_field_name=True)
            data['vectors'] = vectors
            if 'strings' not in data:
                data['strings'] = []
            if 'emotives' not in data:
                data['emotives'] = {}
            ## TODO: unique_id must always go to a manipulative and come through this end!
            if 'unique_id' not in data:
                data['unique_id'] = 'fixme'
            unique_id = data['unique_id']
            self.primitive.mobserve(data)
            m = "observed"
            return kato_proc_pb2.CognitionResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=m
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def Ping(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message='okay',
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )


    def ShowStatus(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            m = {
                "name": self.primitive.name,
                "time": self.primitive.time,
                "SLEEPING": self.primitive.SLEEP,
                "PREDICT": self.primitive.modeler.predict,
                "emotives": self.primitive.current_emotives,
                "target": self.primitive.modeler.target_class,
                "size_WM": len(list(chain(*self.primitive.modeler.WM))),
                "vectors_kb": "{KB| objects: %s}" % (self.primitive.knowledge.vectors_kb.count_documents({})),
                "models_kb": "{KB| objects: %s}" % (self.primitive.knowledge.models_kb.count_documents({})),
                "last_command": self.primitive.last_command,
                "last_learned_model_name": self.primitive.modeler.last_learned_model_name,
            }
            response = Struct()
            response.update({'data': m})
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                response=response,
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def Learn(self, request, context):
        """Learn whatever is in memory now."""
        logger.debug(f'request={request} context={context}')
        try:
            m = str(self.primitive.learn())
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=str(m),
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def StartSleeping(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            self.primitive.clear_wm()
            self.primitive.SLEEP = True
            m = "asleep"
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=str(m),
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def StopSleeping(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            self.primitive.SLEEP = False
            m = "awake"
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=str(m),
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def StartPredicting(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            self.primitive.modeler.predict = True
            m = "activated-predictions"
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=str(m),
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def StopPredicting(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            self.primitive.modeler.predict = False
            m = "deactivated-predictions"
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=str(m),
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def UpdateGenes(self, request, context):
        """Change one of the CP's gene parameters."""
        logger.debug(f'request={request} context={context}')
        try:
            data = json_format.MessageToDict(request)['genes']
            m = self.primitive.update_genes(data)
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=str(m),
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def IncrementRecallThreshold(self, request, context):
        """Inrement or decrement recall_threshold.  Use + or - values."""
        logger.debug(f'request={request} context={context}')
        try:
            if not (1 >= self.primitive.modeler.recall_threshold + request.value > 0):
                return kato_proc_pb2.StandardResponse(
                    status=kato_proc_pb2.StandardResponse.FAILED,
                    id=self.primitive.id,
                    interval=self.primitive.time,
                    time_stamp=time.time(),
                    message="recall threshold must be between 0 > and <= 1",
                )

            self.primitive.modeler.recall_threshold = round(self.primitive.modeler.recall_threshold + request.value, 1)
            self.primitive.modeler.models_searcher.recall_threshold = self.primitive.modeler.recall_threshold
            m = self.primitive.modeler.recall_threshold
            response = Struct()
            response.update({'data': m})
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                response=response,
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def GetGene(self, request, context):
        """Return one of the CP's gene parameter values."""
        logger.debug(f'request={request} context={context}')
        try:
            m = self.primitive.getGene(request.gene)
            response = Struct()
            response.update({'data': m})
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                response=response,
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def GetTime(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            m = self.primitive.time
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=str(m),
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def GetPerceptData(self, request, context):
        """Returns all input manipulative processed data as seen by the CP."""
        logger.debug(f'request={request} context={context}')
        try:
            m = self.primitive.get_percept_data()
            response = Struct()
            response.update({'data': m})
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                response=response,
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def GetCognitionData(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            # Get cognition data from primitive
            cog_data = self.primitive.cognition_data
            
            # Create CognitionObject and populate fields
            response = kato_proc_pb2.CognitionObject()
            
            # Handle predictions (list of Prediction objects)
            if 'predictions' in cog_data and cog_data['predictions']:
                for pred in cog_data['predictions']:
                    # Create Prediction message and add to response
                    pred_msg = kato_proc_pb2.Prediction()
                    # Use MessageToDict/ParseDict for complex nested structures
                    from google.protobuf import json_format
                    json_format.ParseDict(pred, pred_msg)
                    response.predictions.append(pred_msg)
            
            # Handle emotives (map)
            if 'emotives' in cog_data:
                for k, v in cog_data['emotives'].items():
                    response.emotives[k] = float(v)
            
            # Handle simple fields
            if 'symbols' in cog_data:
                response.symbols.extend(cog_data['symbols'])
            if 'command' in cog_data:
                response.command = cog_data['command']
            if 'metadata' in cog_data:
                for k, v in cog_data['metadata'].items():
                    response.metadata[k] = str(v)
            if 'path' in cog_data:
                response.path.extend(cog_data['path'])
            if 'strings' in cog_data:
                response.strings.extend(cog_data['strings'])
            
            # Handle vectors (list of lists -> ListValue)
            if 'vectors' in cog_data:
                from google.protobuf.struct_pb2 import ListValue
                for vector in cog_data['vectors']:
                    list_val = ListValue()
                    list_val.extend(vector)
                    response.vectors.append(list_val)
            
            # Handle working_memory (list of lists -> ListValue)
            if 'working_memory' in cog_data:
                from google.protobuf.struct_pb2 import ListValue
                for wm_item in cog_data['working_memory']:
                    list_val = ListValue()
                    list_val.extend(wm_item)
                    response.working_memory.append(list_val)
            
            return kato_proc_pb2.CognitionResponse(
                status=kato_proc_pb2.CognitionResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                response=response,
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def GetModel(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            m = self.primitive.get_model(request.name.replace('MODEL|', ''))
            # logger.debug(m)
            # # m['emotives'] = Struct(**{'emotives': m['emotives']}) ## failed: KeyError: 'emotives'
            # # m['emotives'] = Struct(**{'data': m['emotives']}) ## failed: KeyError: 'emotives'
            # # m['emotives'] = Struct({'emotives': m['emotives']}) ## failed: KeyError: 'emotives'
            # # m['emotives'] = Struct(**{'data': m['emotives']}) ## failed: ValueError: Protocol message Struct has no "data" field.
            # # m['emotives'] = Struct(**{'emotives': m['emotives']}) ## failed: ValueError: Protocol message Struct has no "emotives" field
            
            # # m['emotives'] = Struct().update(m['emotives']) ## failed: AttributeError: 'list' object has no attribute 'items'
            # m['emotives'] = Struct()
            # m['emotives'].update(m['emotives']) ## Works!

            # # m['sequence'] = ListValue().append(m['sequence']) ## failed: AttributeError: 'ListValue' object has no attribute 'values'
            # # m['sequence'] = ListValue()
            # # m['sequence'].append(m['sequence']) ## failed: AttributeError: 'ListValue' object has no attribute 'values'
            # # m['sequence'].extend(m['sequence']) ## failed: AttributeError: 'ListValue' object has no attribute 'values'
            
            # # n = {'data': [literal_eval(str(x)) for x in m['sequence']]}
            # # m['sequence'] = Struct()
            # # m['sequence'].update(n)  ## Works!
            # # m['sequence'] = Struct().update(n) ## Works!
            # # m['sequence'] = Struct().update({'data': [literal_eval(str(x)) for x in m['sequence']]}) ## Works!
            # m['sequence'] = Struct().update({'data': m['sequence']})

            # logger.debug(m)
            # response = ModelObject(**m)
            response = Struct()
            response.update({'data': m})
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                response=response,
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def DeleteModel(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            m = self.primitive.delete_model(request.name.replace('MODEL|', ''))
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=str(m),
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def UpdateModel(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            name = request.name.replace('MODEL|', '')
            frequency = request.frequency
            emotives = request.emotives
            m = self.primitive.update_model(name, frequency, emotives)
            if not m:
                m = 'model-not-found'
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=str(m),
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def GetVector(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            m = self.primitive.get_vector(request.name)
            response = Struct()
            response.update({'data': m})
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                response=response,
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def GetWorkingMemory(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            wm_list = list(self.primitive.modeler.WM)
            logger.info(f"Working memory raw: {self.primitive.modeler.WM}")
            logger.info(f"Working memory as list: {wm_list}")
            
            # Convert working memory to JSON string as message instead of using Struct
            import json
            wm_json = json.dumps(wm_list)
            logger.info(f"Working memory as JSON: {wm_json}")
            
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=wm_json,
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def ClearWorkingMemory(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            self.primitive.clear_wm()
            m = "wm-cleared"
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=str(m),
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def ClearAllMemory(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            self.primitive.clear_all_memory()
            m = "all-cleared"
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=str(m),
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def GetAllPredictions(self, request, context):
        """Get all current predictions."""
        logger.debug(f'request={request} context={context}')
        try:
            m = {'data': self.primitive.get_predictions({})}
            response = Struct()
            response.update(m)
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                response=response,
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def GetPredictions(self, request, context):
        """Given an event queue, return predictions."""
        logger.debug(f'request={request} context={context}')
        try:
            m = {'data': self.primitive.get_predictions(request)}
            response = Struct()
            response.update(m)
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                response=response,
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )


    def TargetClass(self, request, context):
        logger.debug(f'request={request} context={context}')
        try:
            self.primitive.set_target_class(request.target_class)
            m = f"target class set '{request.target_class}'"
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=str(m),
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )

    def TargetClear(self, request, context):
        """Clears target selection."""
        logger.debug(f'request={request} context={context}')
        try:
            self.primitive.clear_target_class()
            m = "target class cleared"
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.OKAY,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=str(m),
            )
        except BaseException:
            logger.error(f'{traceback.format_exc()}')
            return kato_proc_pb2.StandardResponse(
                status=kato_proc_pb2.StandardResponse.FAILED,
                id=self.primitive.id,
                interval=self.primitive.time,
                time_stamp=time.time(),
                message=traceback.format_exc(),
            )
