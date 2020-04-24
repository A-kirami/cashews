import time
from collections import deque
from functools import wraps
from statistics import mean
from typing import Callable, Iterable, Optional

from cashews.backends.interface import Backend
from cashews.key import get_cache_key, get_cache_key_template
from cashews.typing import FuncArgsType


def _default_perf_condition(current: float, previous: Iterable[float]) -> bool:
    return mean(previous) * 2 < current


class PerfDegradationException(Exception):
    pass


def perf(
    backend: Backend,
    ttl: int,
    func_args: FuncArgsType = None,
    key: Optional[str] = None,
    trace_size: int = 10,
    perf_condition: Optional[Callable[[float, Iterable[float]], bool]] = None,
    prefix: str = "perf",
):
    """
    Trace time execution of target and throw exception if it downgrade to given condition
    :param backend: cache backend
    :param ttl: duration in seconds to lock
    :param func_args: arguments that will be used in key
    :param key: custom cache key, may contain alias to args or kwargs passed to a call
    :param trace_size: the number of calls that are involved
    :param perf_condition: callable object that determines whether the result will be cached,
           default if doubled mean value of time execution less then current
    :param prefix: custom prefix for key, default 'perf'

    """
    perf_condition = _default_perf_condition if perf_condition is None else perf_condition
    call_results = deque([], maxlen=trace_size)

    def _decor(func):
        _key_template = key
        if key is None:
            _key_template = f"{prefix}:{get_cache_key_template(func, func_args=func_args, key=key)}:{ttl}"

        @wraps(func)
        async def _wrap(*args, **kwargs):
            _cache_key = get_cache_key(func, _key_template, args, kwargs, func_args)
            if await backend.is_locked(_cache_key + ":lock"):
                raise PerfDegradationException()
            start = time.perf_counter()
            result = await func(*args, **kwargs)
            takes = time.perf_counter() - start
            if len(call_results) == trace_size and perf_condition(takes, call_results):
                await backend.set_lock(_cache_key + ":lock", value=takes, expire=ttl)
                call_results.clear()
            else:
                call_results.append(takes)
            return result

        return _wrap

    return _decor
