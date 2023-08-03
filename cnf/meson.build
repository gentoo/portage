install_data(
    [
        'etc-update.conf',
        'dispatch-conf.conf'
    ],
    install_dir : sysconfdir
)

extra_features = []
make_globals = 'make.globals'
repos_conf = 'repos.conf'

if get_option('gentoo-dev')
    extra_features += [
        'ipc-sandbox',
        'network-sandbox',
        'strict-keepdir',
        'warn-on-large-env'
    ]
endif

if get_option('xattr') and host_machine.system() == 'linux'
    extra_features += [
        'xattr'
    ]
endif

if extra_features.length() > 0
    make_globals = configure_file(
        input : make_globals,
        output : 'make.globals#features',
        command : [sed, '$aFEATURES="${FEATURES} ' + ' '.join(extra_features) + '"', '@INPUT@'],
        capture : true
    )
endif

if not get_option('rsync-verify')
    repos_conf = configure_file(
        input : repos_conf,
        output : 'repos.conf#rsync-verify',
        command : [sed, '-r', 's:\\b(sync-rsync-verify-metamanifest|sync-webrsync-verify-signature)(\\s*=\\s*).*:\\1\\2no:', '@INPUT@'],
        capture : true
    )
endif

if eprefix != ''
    make_globals = configure_file(
        input : make_globals,
        output : 'make.globals#eprefix',
        command : hprefixify,
        capture : true
    )

    repos_conf = configure_file(
        input : repos_conf,
        output : 'repos.conf#eprefix',
        command : hprefixify,
        capture : true
    )
endif

arch = host_machine.cpu_family()

arch = {
    'aarch64' : 'arm64',
    'loongarch64' : 'loong',
    'mips64' : 'mips',
    'parisc' : 'hppa',
    'riscv32' : 'riscv',
    'riscv64' : 'riscv',
    's390x' : 's390',
    'sh4' : 'sh',
    'sparc64' : 'sparc',
    'x86_64' : 'amd64'
}.get(arch, arch)

if host_machine.system() == 'freebsd'
    arch += '-fbsd'
endif

make_conf_example = 'make.conf.example'
diff = make_conf_example + '.' + arch + '.diff'
fs = import('fs')

if fs.exists(diff)
    patch = find_program('patch', required : true)
    make_conf_example = configure_file(
        input : [make_conf_example, diff],
        output : 'make.conf.example',
        command : [patch, '-o', '@OUTPUT@', '@INPUT0@', '@INPUT1@']
    )
else
    warning('Portage does not have an arch-specific configuration for this arch. Please notify the arch maintainer about this issue. Using the generic configuration.')
endif

# TODO: Use fs.copyfile() when requiring Meson >=0.64.0.

make_globals = configure_file(
    input : make_globals,
    output : 'make.globals',
    copy : true
)

repos_conf = configure_file(
    input : repos_conf,
    output : 'repos.conf',
    copy : true
)

# TODO: Use preserve_path option when requiring Meson >=0.64.0.

install_data(
    [
        make_conf_example,
        make_globals,
        repos_conf,
    ],
    install_dir : portage_datadir / 'config'
)

install_data(
    [
        'repo.postsync.d/example'
    ],
    install_dir : portage_datadir / 'config' / 'repo.postsync.d'
)

install_data(
    [
        'sets/portage.conf'
    ],
    install_dir : portage_datadir / 'config' / 'sets'
)

if not system_wide
    subdir_done()
endif

install_data(
    [
        'logrotate.d/elog-save-summary'
    ],
    install_dir : sysconfdir / 'logrotate.d'
)
