import asyncio
from logzero import logger

def run(callable, timeout: int, *args, **kwargs) -> bool:
    """
    Run an async function on the main asycio event loop

    :param callable: An async function pointer
    :type callable: ???
    :param timeout: Number of seconds the async function is allowed to execute
        before timing out.
    :type timeout: int
    :param *args: Expanded list of arguments to pass to the async function
    :type *args: Any
    :param **kwargs: Expanded keyword arguments to pass to the async function
    :type **kwargs: Any
    :return: bool
    """
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(asyncio.wait_for(callable(*args, **kwargs), timeout=timeout))
    except asyncio.TimeoutError:
        logger.error("Call to %s timed out!!!", callable)
        return False
    return True
    #loop.run_until_complete(callable(*args, **kwargs))
    #loop.close()
