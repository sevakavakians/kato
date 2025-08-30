import math
import statistics
import tempfile
import traceback
from collections import Counter, OrderedDict
from functools import reduce
from itertools import chain
from math import ceil, log, log10
from operator import mul, add, attrgetter
from os import environ
import logging

logger = logging.getLogger('kato.informatics.metrics')
logger.setLevel(getattr(logging, environ['LOG_LEVEL']))
logger.info('logging initiated')


def average_emotives(record):
    '''Average the list of emotive dicts throughout these sequence's observations.
    Averages the emotives in a list (e.g. predictions ensemble or percepts).
    The emotives in the record are of type: [{'e1': 4, 'e2': 5}, {'e2': 6}, {'e1': 5 'e3': -4}]
    Average it instead of sum it because we expect the emotive states to persist
    throughout event updates that shouldn't increase/decrease the perceived emotives.
    '''
    logger.debug(f'average_emotives record: {record}')
    new_dict = {}
    for bunch in record:
        logger.debug(bunch)
        for e,v in bunch.items():
            if e not in new_dict:
                new_dict[e] = [v]
            else:
                new_dict[e].append(v)
    avg_dict = {}
    for e,v in new_dict.items():
        avg_dict[e] = float(sum(v)/len(v))
    return avg_dict

def compandingFunction(target, collection):
    """
    Reduces the data rate of signals by making the quantization levels unequal.
    Given a target number and a collection of numbers as a list,
    find the lower closest match of the target to numbers in the collection
    Helps to create vectors that are canonical in their values by
    locking a range of values to a single value in the collection.

    ex:
        compandingFunction(10, [0, 3, 5, 7, 11])
        7
        where the lowest closest match for 9 is 7.
    """
    return min((abs(target - i), i) for i in collection)[1]


def classic_expectation(p):
    "The information expectation function for a state."
    if p > 0:
        return -(p * log(p, 2))
    else:
        return 0


def expectation(p, num_symbols):
    "The information expectation function for a state."
    try:
        if p > 0 and num_symbols > 1:
            return - p * log(p, num_symbols)
        else:
            return 0
    except Exception as e:
        print("expectation ERROR! p = %s, num_symbols = %s, error = %s" % (p, num_symbols, e))


def grand_hamiltonian(state, symbol_probabilities, total_symbols):
    symbols = set(state)
    return sum(
        [expectation(symbol_probabilities.get(symbol, 0), total_symbols) for
         symbol in symbols])


def hamiltonian(state, total_symbols):
    return sum([expectation(state.count(symbol) / len(state), total_symbols) for symbol in state])


####### confluence = probability of sequence occurring in observations * ( 1 - probability of sequence occurring randomly)
def confluence(state, symbols_kb, P1=None):
    '''
    Confluence of a Model is the probability of that model occurring randomly taking into
    consideration the probabilities of each symbol within the model appearing.
    P1 = probability of sequence occurring in observations
    i.e.:
        confluence = probability of sequence occurring in observations * ( 1 - probability of sequence occurring randomly)
    '''
    if state:
        return conditionalProbability(state, symbols_kb)
    else:
        raise


def conditionalProbability(state, symbol_probabilities):
    # Handle missing symbols by using a small default probability
    probs = []
    for symbol in state:
        prob = symbol_probabilities.get(symbol, 1e-10)  # Small default probability
        if prob > 0:
            probs.append(log10(prob))
        else:
            probs.append(log10(1e-10))  # Avoid log(0)
    return 10**reduce(add, probs) if probs else 0


def filterRange(x, range_floor, range_ceil):
    if x is not None:
        if x[0] >= range_floor and x[0] <= range_ceil:
            return x

