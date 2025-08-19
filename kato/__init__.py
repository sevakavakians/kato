from concurrent import futures
import logging, sys
from os import environ
import grpc
from kato.workers.server import KatoEngineServicer

from kato import kato_proc_pb2, kato_proc_pb2_grpc


logger = logging.getLogger('kato')
logger.setLevel(getattr(logging, environ['LOG_LEVEL']))
logger.info('logging initiated')
formatter = '[%(asctime)s.%(msecs)06d] [%(relativeCreated)6d] [pid|%(process)d] [tid|%(thread)d] [%(levelname)s] [%(name)s] [%(filename)s] [%(funcName)s] [line|%(lineno)d] %(message)s'
logging.basicConfig(
        stream=sys.stderr,
        format=formatter,
        datefmt='%a %b %d %Y %H:%M:%S')

PORT = environ['PORT']
HOSTNAME = environ['HOSTNAME']

def serve(port, primitive):
    logger.info(f'Serving {HOSTNAME}:{PORT}')
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    kato_proc_pb2_grpc.add_KatoEngineServicer_to_server(
        KatoEngineServicer(primitive), server)
    server.add_insecure_port(f'{HOSTNAME}:{PORT}')
    server.start()
    server.wait_for_termination()