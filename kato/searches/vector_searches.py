import heapq
from itertools import groupby
from multiprocessing import Pool
from operator import attrgetter, itemgetter

from numpy.linalg import norm

from kato.auxiliary.decorators import *
from kato.searches.aima.search import iterative_deepening_search, Problem

import logging
from os import environ

logger = logging.getLogger('kato.searches.classification')
logger.setLevel(getattr(logging, environ['LOG_LEVEL']))
logger.info('logging initiated')



#### For CVC ##############################################
def calculate_diff_lengths(data):
        ## Calculate the length of the differences between current and all known vectors.
        state, vec = data
        return [vec, norm(state - vec)]

class CVCSearcher:
    def __init__(self, procs_for_searches, vectors_kb):
        self.procs = procs_for_searches
        self.datasubset = list(vectors_kb.values())

    def assignNewlyLearnedToWorkers(self, new_vectors):
        "Assigning newly learned to workers so that we don't re-assign from scratch every time."
        self.datasubset += new_vectors

    def findNearestPoints(self, state): #_kb):
        "Where state (point) is a VectorObject and returned is the nearest VectorObject."
        # If there are no vectors in the knowledge base yet, return empty list
        if not self.datasubset or len(self.datasubset) == 0:
            return []
        
        # If we have only one processor or few data points, skip multiprocessing
        if self.procs == 1 or len(self.datasubset) < 3:
            results = []
            for element in self.datasubset:
                results.append(calculate_diff_lengths((state, element)))
        else:
            work_list = [(state, element) for element in self.datasubset]
            with Pool(processes=self.procs) as pool:
                results = pool.map(calculate_diff_lengths, work_list)
        
        return [i.name for i, v in heapq.nsmallest(3,[x for x in results],key=itemgetter(1))]

    def clearModelsFromRAM(self):
        self.datasubset = []


#### For DVC ##############################################
def mostCommon(L):
    """
    Returns the most common element from a list.
    Alex Martelli"s solution from
    http://stackoverflow.com/questions/1518522/python-most-common-element-in-a-list
    """
    # get an iterable of (item, iterable) pairs
    SL = sorted((x, i) for i, x in enumerate(L))
    groups = groupby(SL, key=itemgetter(0))
    def _auxfun(g):
        item, iterable = g
        count = 0
        min_index = len(L)
        for _, where in iterable:
            count += 1
            min_index = min(min_index, where)
        return count, -min_index
    # pick the highest-count/earliest item
    return max(groups, key=_auxfun)[0]

class CVPProblem(Problem):
    """
    Using the heuristic lists, subtract known vectors from the test_vector until the null_vector is found.
    This should be a unique solution if proper rich-contexting techniques have been implemented.
    The path used to get to the null_vector consists of the perceived component objects.
    """
    def __init__(self, test_vector, known_vectors, primers=None):
        Problem.__init__(self, test_vector, goal=0)
        self.known_vectors = known_vectors
        self.heuristic = generateHeuristic(test_vector, known_vectors)

    def successor(self, state):
        graph = {}
        subgraph = {}
        for vector in self.heuristic: # compare against replacing self.heuristic with self.known_vectors
            if not vector.isNull():
                difference_vector = state - vector
                if not difference_vector.isLessThanZero():
                    subgraph.setdefault(hash, difference_vector)
        graph.setdefault(state.name, subgraph)
        return [(B, subgraph[B]) for B in list(graph.get(state.name).keys())]

    def goal_test(self, state):
        return state.vector_length == self.goal

@memoized
def canonicalVectorPursuitSearch(test_vector, known_vectors, cut_off, primers=None):
    problem = CVPProblem(test_vector, known_vectors, primers)
    path = []
    s = iterative_deepening_search(problem, cut_off)
    for node in s.path():
        path.append(node.state)
    component_vectors =  extractSolutionFromPath(path) # Solution
    return component_vectors

def extractSolutionFromPath(path):
    """
    Return a new list of vectors from recursively subtracting the given list of vectors.
    ex.  if E = A + B + C
         and
         path = [E, E-C, E-C-B] (result from BFS through known vectors)
    then returns [A, B, C]
    """
    solution = []
    bigger_vector = path.pop()
    while len(path) >= 1:
        smaller_vector = path.pop()
        difference_vector = bigger_vector - smaller_vector
        solution.append(difference_vector)
        bigger_vector = smaller_vector
#    solution.append(bigger_vector) # Don't add last vector popped.  This was the original composite.
    return solution

def generateHeuristic(test_vector, known_vectors):
    "Returns a list of vectors in descending order by vector length.  Creating the heuristic list is critical for PCA/canonicalVectorPursuit."
    heuristic = sorted(known_vectors, key=attrgetter("vector_length"), reverse=True) # Sort by vector_length
    return [vector for vector in heuristic if vector.vector_length <= test_vector.vector_length] # Filter to less than test_vector.vector_length

def vectorSubtractionBFS(test_vector, known_vectors, cut_off, primers=None):  #Algorithm works, expanded list has too many items.  Extra vectors are imaginary + true unknown.
    """
    Returns a list.

    Breadth-First Search by subtracting known vectors from the test_vector and
    using vector length heuristic to keep the search space small.
    Looking for any known vectors that make up the compound test_vector.
    Anything left over is a new object vector.  If this object vector is also
    a compound vector, over time with large sample sets, this search will reveal
    the sub-vectors that compose even this compound vector.

    BFS is appropriate here because looking for the smallest number of vectors
    that add up to the test_vector.  (FIFO)
    """
    nodes = []
    expanded = []
    nodes.append(test_vector)
    depth = 0
    while len(nodes) != 0:
        if depth == cut_off:
            return [test_vector]
        depth += 1
        parent_vector = nodes.pop(0)
        expanded.append(parent_vector)
        heuristic = generateHeuristic(test_vector, known_vectors) # Revise the heuristic as we go.
        if len(heuristic) == 0:
            continue
        for vector in heuristic:
            if vector.isNull():
                continue
            difference_vector = parent_vector - vector
            if difference_vector.isNull(): # Goal!
                expanded.append(vector)
                return expanded
            elif difference_vector.isLessThanZero():
                continue
            else:
                nodes.append(difference_vector)
    if len(expanded) == 0:
        return [test_vector]
    else:
        return expanded

def canonicalVectorDiscovery(test_vector, known_vectors, cut_off, primers):
    imagined_vectors = vectorSubtractionBFS(test_vector, known_vectors, cut_off, primers)
    if len(imagined_vectors) > 1:
        imagined_vectors.remove(test_vector)
    unknown_vector = mostCommon(imagined_vectors)  #because the correct component vector will be reached via more paths.
    return unknown_vector

def vectorSearch(test_vector, known_vectors, cut_off, primers):
    """
    Returns a tuple of a ([v1,v2,...], v_new) of recognized objects and a newly discovered object, if any.  Otherwise, returns None, None.
    Also updates the known_vectors KB with newly discovered objects as part of its search algorithm.  (No need to update elsewhere.)
    """
    recognized_objects = None
    discovered_object = None
    try:
        if test_vector in known_vectors:
            known_vectors.pop(test_vector)
        
        try:
            recognized_objects = canonicalVectorPursuitSearch(test_vector, known_vectors, cut_off, primers)
        except Exception as e:
            raise Exception("\n>>>>>>>>CVP ERROR: %s \n %s" %(e, traceback.format_exc()))
        # recognized_objects = canonicalVectorPursuitSearch(test_vector, known_vectors, cut_off, primers)
    except:
        last_discovered = canonicalVectorDiscovery(test_vector, known_vectors, cut_off, primers)
        while True:
            discovered_object = canonicalVectorDiscovery(last_discovered, known_vectors, cut_off, primers)
            if discovered_object == last_discovered:
                break
            else:
                last_discovered = discovered_object
        known_vectors += (discovered_object,)
        try:
            recognized_objects = canonicalVectorPursuitSearch(test_vector, known_vectors, cut_off, primers)
        except:
            pass
    return recognized_objects, discovered_object

