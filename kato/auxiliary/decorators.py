import logging
import traceback
from functools import partial, wraps
from time import sleep
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union


def retry(
    ExceptionToCheck: Union[Type[Exception], Tuple[Type[Exception], ...]],
    tries: int = 4,
    delay: int = 3,
    backoff: int = 2,
    logger: Optional[logging.Logger] = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Retry calling the decorated function using an exponential backoff.
    
    Args:
        ExceptionToCheck: The exception(s) to check. May be a single exception
            class or a tuple of exception classes.
        tries: Number of times to try (not retry) before giving up.
        delay: Initial delay between retries in seconds.
        backoff: Backoff multiplier. E.g., value of 2 will double the delay
            each retry.
        logger: Logger to use for messages. If None, uses print.
        
    Returns:
        Decorator function that adds retry logic to the wrapped function.
        
    Example:
        >>> @retry(ConnectionError, tries=3, delay=1)
        ... def connect_to_db():
        ...     # Connection logic here
        ...     pass
    """
    def deco_retry(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def f_retry(*args: Any, **kwargs: Any) -> Any:
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck as e:
                    msg = "%s, Retrying in %d seconds..." % (str(e), mdelay)
                    if logger:
                        logger.warning(msg)
                    else:
                        import logging
                        logging.getLogger(__name__).warning(msg)
                    sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)
        return f_retry  # true decorator
    return deco_retry

class memoized:
    """Decorator that caches a function's return value each time it is called.
    
    If called later with the same arguments, the cached value is returned,
    and not re-evaluated. Useful for expensive computations.
    
    Attributes:
        func: The function being memoized.
        cache: Dictionary storing cached results.
    """

    def __init__(self, func: Callable[..., Any]) -> None:
        """Initialize the memoized decorator.
        
        Args:
            func: Function to be memoized.
        """
        self.func: Callable[..., Any] = func
        self.cache: Dict[Tuple[Any, ...], Any] = {}
    def __call__(self, *args: Any) -> Any:
        """Call the memoized function.
        
        Args:
            *args: Arguments to pass to the function.
            
        Returns:
            Cached result if available, otherwise computes and caches result.
        """
        try:
            return self.cache[args]
        except KeyError:
            value = self.func(*args)
            self.cache[args] = value
            return value
        except TypeError:
            # uncachable -- for instance, passing a list as an argument.
            # Better to not cache than to blow up entirely.
            return self.func(*args)
    def __repr__(self) -> str:
        """Return the function's docstring.
        
        Returns:
            The wrapped function's docstring or empty string.
        """
        return self.func.__doc__ or ""
    def __get__(self, obj: Any, _objtype: Optional[type] = None) -> Callable[..., Any]:
        """Support instance methods.
        
        Args:
            obj: Instance object.
            objtype: Type of the instance.
            
        Returns:
            Partial function bound to the instance.
        """
        return partial(self.__call__, obj)


class tracebackMessage:
    """Decorator that enhances exception messages with full traceback.
    
    Wraps a function to catch exceptions and re-raise them with detailed
    traceback information for better debugging.
    
    Attributes:
        func: The function being wrapped.
    """

    def __init__(self, func: Callable[..., Any]) -> None:
        """Initialize the traceback decorator.
        
        Args:
            func: Function to wrap with traceback handling.
        """
        self.func: Callable[..., Any] = func

    def __call__(self, *args: Any) -> Any:
        """Call the wrapped function with traceback handling.
        
        Args:
            *args: Arguments to pass to the function.
            
        Returns:
            Result of the wrapped function.
            
        Raises:
            Exception: Re-raises any exception with full traceback.
        """
        try:
            return self.func(*args)
        except:
            raise Exception(traceback.format_exc())



# First 430 prime numbers
primes: List[int] = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73,
            79, 83, 89, 97, 101, 103, 107, 109, 113, 127, 131, 137, 139, 149, 151, 157, 163,
            167, 173, 179, 181, 191, 193, 197, 199, 211, 223, 227, 229, 233, 239, 241, 251,
            257, 263, 269, 271, 277, 281, 283, 293, 307, 311, 313, 317, 331, 337, 347, 349,
            353, 359, 367, 373, 379, 383, 389, 397, 401, 409, 419, 421, 431, 433, 439, 443,
            449, 457, 461, 463, 467, 479, 487, 491, 499, 503, 509, 521, 523, 541, 547, 557,
            563, 569, 571, 577, 587, 593, 599, 601, 607, 613, 617, 619, 631, 641, 643, 647,
            653, 659, 661, 673, 677, 683, 691, 701, 709, 719, 727, 733, 739, 743, 751, 757,
            761, 769, 773, 787, 797, 809, 811, 821, 823, 827, 829, 839, 853, 857, 859, 863,
            877, 881, 883, 887, 907, 911, 919, 929, 937, 941, 947, 953, 967, 971, 977, 983,
            991, 997, 1009, 1013, 1019, 1021, 1031, 1033, 1039, 1049, 1051, 1061, 1063, 1069,
            1087, 1091, 1093, 1097, 1103, 1109, 1117, 1123, 1129, 1151, 1153, 1163, 1171, 1181,
            1187, 1193, 1201, 1213, 1217, 1223, 1229, 1231, 1237, 1249, 1259, 1277, 1279, 1283,
            1289, 1291, 1297, 1301, 1303, 1307, 1319, 1321, 1327, 1361, 1367, 1373, 1381, 1399,
            1409, 1423, 1427, 1429, 1433, 1439, 1447, 1451, 1453, 1459, 1471, 1481, 1483, 1487,
            1489, 1493, 1499, 1511, 1523, 1531, 1543, 1549, 1553, 1559, 1567, 1571, 1579, 1583,
            1597, 1601, 1607, 1609, 1613, 1619, 1621, 1627, 1637, 1657, 1663, 1667, 1669, 1693,
            1697, 1699, 1709, 1721, 1723, 1733, 1741, 1747, 1753, 1759, 1777, 1783, 1787, 1789,
            1801, 1811, 1823, 1831, 1847, 1861, 1867, 1871, 1873, 1877, 1879, 1889, 1901, 1907,
            1913, 1931, 1933, 1949, 1951, 1973, 1979, 1987, 1993, 1997, 1999, 2003, 2011, 2017,
            2027, 2029, 2039, 2053, 2063, 2069, 2081, 2083, 2087, 2089, 2099, 2111, 2113, 2129,
            2131, 2137, 2141, 2143, 2153, 2161, 2179, 2203, 2207, 2213, 2221, 2237, 2239, 2243,
            2251, 2267, 2269, 2273, 2281, 2287, 2293, 2297, 2309, 2311, 2333, 2339, 2341, 2347,
            2351, 2357, 2371, 2377, 2381, 2383, 2389, 2393, 2399, 2411, 2417, 2423, 2437, 2441,
            2447, 2459, 2467, 2473, 2477, 2503, 2521, 2531, 2539, 2543, 2549, 2551, 2557, 2579,
            2591, 2593, 2609, 2617, 2621, 2633, 2647, 2657, 2659, 2663, 2671, 2677, 2683, 2687,
            2689, 2693, 2699, 2707, 2711, 2713, 2719, 2729, 2731, 2741, 2749, 2753, 2767, 2777,
            2789, 2791,2797, 2801, 2803, 2819, 2833, 2837, 2843, 2851, 2857, 2861, 2879, 2887,
            2897, 2903, 2909, 2917, 2927, 2939, 2953, 2957, 2963, 2969, 2971, 2999]

special_primes: List[int] = [0] + primes[1:]
# Distances between special primes are such that the difference is never a summation of any previous special primes.

## The following companding laws are from pg.363 in The Scientists and Engineer's Guide to Digital Signal Processing, Steve W. Smith

# compandingFunction=lambda a,l:min(l,key=lambda x:abs(x-a))
# toCollection is like valueLock below, but finds the closest match, rather than the lower closest match.

def compandingFunction(target: Union[int, float], collection: List[Union[int, float]]) -> Union[int, float]:
    """Reduces the data rate of signals by making the quantization levels unequal.
    
    Given a target number and a collection of numbers, finds the closest match
    of the target to numbers in the collection. Helps create vectors that are
    canonical in their values by locking a range of values to a single value.
    
    Args:
        target: The target number to match.
        collection: List of numbers to match against.
        
    Returns:
        The closest number from the collection to the target.
        
    Example:
        >>> compandingFunction(10, [0, 3, 5, 7, 11])
        7
        >>> compandingFunction(9, [0, 3, 5, 7, 11])
        7
    """
    return min((abs(target - i), i) for i in collection)[1]
