import asyncio


def run(callable, timeout, *args, **kwargs):
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(asyncio.wait_for(callable(*args, **kwargs), timeout=timeout))
    except asyncio.TimeoutError:
        print("Call to", callable, "timed out!!!")
        return False
    return True
    #loop.run_until_complete(callable(*args, **kwargs))
    #loop.close()
