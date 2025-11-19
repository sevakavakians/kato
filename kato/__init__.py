import logging
import sys
from os import environ

logger = logging.getLogger('kato')

# Set up logging if LOG_LEVEL is defined
if 'LOG_LEVEL' in environ:
    logger.setLevel(getattr(logging, environ['LOG_LEVEL']))
    logger.info('logging initiated')
    formatter = '[%(asctime)s.%(msecs)06d] [%(relativeCreated)6d] [pid|%(process)d] [tid|%(thread)d] [%(levelname)s] [%(name)s] [%(filename)s] [%(funcName)s] [line|%(lineno)d] %(message)s'
    logging.basicConfig(
        stream=sys.stderr,
        format=formatter,
        datefmt='%a %b %d %Y %H:%M:%S')

# Version info
__version__ = '3.0.1'
