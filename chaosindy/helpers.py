import asyncio

def run(callable, *args, **kwargs):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(callable(*args, **kwargs))
    loop.close()
