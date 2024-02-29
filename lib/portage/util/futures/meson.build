py.install_sources(
    [
        'extendedfutures.py',
        'futures.py',
        'iter_completed.py',
        'retry.py',
        'unix_events.py',
        '_sync_decorator.py',
        '__init__.py',
    ],
    subdir : 'portage/util/futures',
    pure : not native_extensions
)

subdir('executor')
subdir('_asyncio')
