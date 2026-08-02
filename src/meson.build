# We create symlinks to the native extensions in the source tree for the tests
# and for development. Meson does not allow you to build in-place and Python
# cannot create a single namespace from two identically-named paths.

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
        whirlpool_ext.full_path(),
        meson.project_source_root() / 'lib' / 'portage' / 'util/'
    ],
    capture : false,
    check : true
)

dep_parser_ext = py.extension_module(
    '_parser',
    'dep_parser_core.c',
    'dep_parser.c',
    include_directories : include_directories('.'),
    dependencies : py.dependency(),
    subdir : 'portage' / 'dep',
    install : true,
)

run_command(
    [
        'ln', '-srnf',
        dep_parser_ext.full_path(),
        meson.project_source_root() / 'lib' / 'portage' / 'dep/'
    ],
    capture : false,
    check : true
)

test_parser = executable(
    'test_parser',
    'dep_parser_core.c',
    'test_parser.c',
    include_directories : include_directories('.'),
)

test('parser', test_parser)

if get_option('fuzzing')
    fuzz_parser = executable(
        'fuzz_parser',
        'dep_parser_core.c',
        'fuzz_parser.c',
        include_directories : include_directories('.'),
        c_args : ['-fsanitize=fuzzer'],
        link_args : ['-fsanitize=fuzzer'],
        build_by_default : false,
    )
endif
