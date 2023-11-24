py_bins = [
    'ebuild',
    'egencache',
    'emerge',
    'emirrordist',
    'glsa-check',
    'gpkg-sign',
    'portageq',
    'quickpkg'
]

other_bins = [
    'emerge-webrsync'
]

py_sbins = [
    'archive-conf',
    'dispatch-conf',
    'emaint',
    'env-update',
    'fixpackages',
    'regenworld'
]

etc_update = 'etc-update'

if eprefix != ''
    etc_update = configure_file(
        input : etc_update,
        output : 'etc-update',
        command : hprefixify,
        capture : true
    )
endif

# It might seem sensible to use py.install_sources() to install the Python
# scripts, but it's really just a wrapper around install_data that forces the
# install_dir. Meson 1.2.0 and later also optimize to bytecode, but Gentoo does
# this in the ebuild.

install_data(
    py_bins,
    install_dir : system_wide ? get_option('bindir') : portage_bindir,
    install_mode : 'rwxr-xr-x',
)

install_data(
    other_bins,
    install_dir : get_option('bindir'),
    install_mode : 'rwxr-xr-x',
)

install_data(
    py_sbins,
    install_dir : system_wide ? get_option('sbindir') : portage_bindir,
    install_mode : 'rwxr-xr-x',
)

install_data(
    [etc_update],
    install_dir : system_wide ? get_option('sbindir') : get_option('bindir'),
    install_mode : 'rwxr-xr-x',
)

# Note that exclude_files is currently broken in meson-python, but it should
# work soon. Having duplicates here isn't that bad in the meantime.
# https://github.com/mesonbuild/meson-python/issues/317

install_subdir(
    '.',
    exclude_files : py_bins + other_bins + py_sbins + ['etc-update', 'meson.build'],
    install_dir : portage_bindir
)
