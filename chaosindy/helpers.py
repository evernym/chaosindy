import asyncio
from logzero import logger


def run(callable, timeout, *args, **kwargs):
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(asyncio.wait_for(callable(*args, **kwargs), timeout=timeout))
    except asyncio.TimeoutError:
        logger.error("Call to %s timed out!!!", callable)
        return False
    return True
    #loop.run_until_complete(callable(*args, **kwargs))
    #loop.close()
