const_py = configure_file(
    input : 'const.py',
    output : 'const.py',
    configuration : conf_data
)

installation_py = configure_file(
    input : 'installation.py',
    output : 'installation.py',
    configuration : conf_data
)

__init__py = configure_file(
    input : '__init__.py',
    output : '__init__.py',
    configuration : conf_data
)

py.install_sources(
    [
        'binpkg.py',
        'checksum.py',
        const_py,
        'cvstree.py',
        'data.py',
        'debug.py',
        'dispatch_conf.py',
        'eapi.py',
        'eclass_cache.py',
        'exception.py',
        'getbinpkg.py',
        'glsa.py',
        'gpg.py',
        'gpkg.py',
        installation_py,
        'localization.py',
        'locks.py',
        'mail.py',
        'manifest.py',
        'metadata.py',
        'module.py',
        'news.py',
        'output.py',
        'process.py',
        'progress.py',
        'update.py',
        'versions.py',
        'xpak.py',
        '_global_updates.py',
        '_legacy_globals.py',
        '_selinux.py',
        __init__py,
    ],
    subdir : 'portage',
    pure : not native_extensions
)

subdir('binrepo')
subdir('cache')
subdir('dbapi')
subdir('dep')
subdir('elog')
subdir('emaint')
subdir('env')
subdir('package')
subdir('proxy')
subdir('repository')
subdir('sync')
subdir('tests')
subdir('util')
subdir('xml')
subdir('_compat_upgrade')
subdir('_emirrordist')
subdir('_sets')
