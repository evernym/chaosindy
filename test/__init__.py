from contextlib import contextmanager


@contextmanager
def patch(owner, attr, value):
    """Monkey patch context manager.

    with patch(os, 'open', myopen):
        ...
    """
    old = getattr(owner, attr)
    setattr(owner, attr, value)
    try:
        yield getattr(owner, attr)
    finally:
        setattr(owner, attr, old)
