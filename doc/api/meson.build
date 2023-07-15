sphinx_apidoc = find_program('sphinx-apidoc', required : get_option('apidoc'))
sphinx_build = find_program('sphinx-build', required : get_option('apidoc'))

if not sphinx_apidoc.found() or not sphinx_build.found()
    subdir_done()
endif

api_symlinks = custom_target(
    'symlinks',
    input: ['conf.py', 'index.rst'],
    output : ['conf.py', 'index.rst'],
    command : ['ln', '-srnf', '@INPUT@', '@OUTDIR@/']
)

api_rst = custom_target(
    'rst',
    output : ['portage.rst'],
    command : [sphinx_apidoc, '-TPef', '-o', '@OUTDIR@', '@SOURCE_ROOT@/lib', '@SOURCE_ROOT@/lib/portage/tests'],
    env : {'SPHINX_APIDOC_OPTIONS' : 'members,private-members,undoc-members,show-inheritance,ignore-module-all,inherited-members'}
)

# sphinx-build generates a lot of files, and it would be awkward to keep a list
# updated. This workaround is slightly hacky as you're probably not supposed to
# set "output" to a directory. Note that it cannot include a /. We use
# install_subdir here, unlike in the parent directory, because it can use a
# different name for the destination and can exclude some files.

custom_target(
    'html',
    depends: [api_symlinks, api_rst],
    output : ['html'],
    command : [sphinx_build, '-M', 'html', '@OUTDIR@', '@OUTDIR@/html'],
    build_by_default : get_option('apidoc')
)

if get_option('apidoc')
    install_subdir(
        meson.current_build_dir() / 'html' / 'html',
        exclude_directories : ['_sources'],
        strip_directory : true,
        install_dir : docdir / 'html' / 'api'
    )
endif
