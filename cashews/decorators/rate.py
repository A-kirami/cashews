import logging
from functools import wraps
from typing import Callable, Optional

from cashews.backends.interface import Backend
from cashews.key import get_cache_key, get_cache_key_template, register_template
from cashews.typing import FuncArgsType

logger = logging.getLogger(__name__)


class RateLimitException(Exception):
    pass


def _default_action(*args, **kwargs):
    raise RateLimitException()


def rate_limit(
    backend: Backend,
    limit: int,
    period: int,
    ttl: int = None,
    func_args: FuncArgsType = None,
    action: Optional[Callable] = None,
    prefix="rate_limit",
):  # pylint: disable=too-many-arguments
    """
    Rate limit for function call. Do not call function if rate limit is reached, and call given action

    :param backend: cache backend
    :param limit: number of calls
    :param period: Period
    :param ttl: time ban, default == period
    :param func_args: arguments that will be used in key
    :param action: call when rate limit reached, default raise RateLimitException
    :param prefix: custom prefix for key, default 'rate_limit'
    """
    action = _default_action if action is None else action

    def decorator(func):
        _key_template = f"{prefix}:{get_cache_key_template(func, func_args=func_args)}"
        register_template(func, _key_template)

        @wraps(func)
        async def wrapped_func(*args, **kwargs):
            _cache_key = get_cache_key(func, _key_template, args, kwargs, func_args)

            requests_count = await backend.incr(key=_cache_key)  # set 1 if not exists
            if requests_count and requests_count > limit:
                if ttl and requests_count == limit + 1:
                    await backend.expire(key=_cache_key, timeout=ttl)
                logger.info("Rate limit reach for %s", _cache_key)
                action(*args, **kwargs)

            if requests_count == 1:
                await backend.expire(key=_cache_key, timeout=period)

            return await func(*args, **kwargs)

        return wrapped_func

    return decorator
