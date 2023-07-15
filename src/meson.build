# We create symlinks to the native extensions in the source tree for the tests
# and for development. Meson does not allow you to build in-place and Python
# cannot create a single namespace from two identically-named paths.

libc_ext = py.extension_module(
    'libc',
    'portage_util_libc.c',
    dependencies : py.dependency(),
    subdir : 'portage' / 'util',
    install : true
)

whirlpool_ext = py.extension_module(
    '_whirlpool',
    'portage_util__whirlpool.c',
    dependencies : py.dependency(),
    subdir : 'portage' / 'util',
    install : true
)

run_command(
    [
        'ln', '-srnf',
        libc_ext.full_path(),
        whirlpool_ext.full_path(),
        meson.project_source_root() / 'lib' / 'portage' / 'util/'
    ],
    capture : false,
    check : true
)

if host_machine.system() == 'linux'
    reflink_ext = py.extension_module(
        'reflink_linux',
        'portage_util_file_copy_reflink_linux.c',
        dependencies : py.dependency(),
        subdir : 'portage' / 'util' / 'file_copy',
        install : true
    )

    run_command(
        [
            'ln', '-srnf',
            reflink_ext.full_path(),
            meson.project_source_root() / 'lib' / 'portage' / 'util' / 'file_copy/'
        ],
        capture : false,
        check : true
    )
endif
