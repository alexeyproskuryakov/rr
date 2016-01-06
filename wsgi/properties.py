import logging
import os
import sys

__author__ = 'alesha'



def module_path():
    if hasattr(sys, "frozen"):
        return os.path.dirname(
            sys.executable
        )
    return os.path.dirname(__file__)


log_file = os.path.join(module_path(), 'result.log')
cacert_file = os.path.join(module_path(), 'cacert.pem')

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(log_file)
ch = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s[%(levelname)s]%(name)s|%(processName)s(%(process)d): %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
logger.addHandler(fh)
logger.addHandler(ch)

SRC_SEARCH = "search"
SRC_OBSERV = "observation"

mongo_uri = "mongodb://alesha:sederfes100500@ds035674.mongolab.com:35674/rr"
default_time_min = "PT0H1M30S"

min_update_period = 3600*24
min_time_step = 10
max_time_step = 3600*5

step_time_after_trying = 60
tryings_count = 10

time_step_less_iteration_power = 0.85