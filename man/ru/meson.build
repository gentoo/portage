man_pages_out = []
man_pages_in = [
    'color.map.5',
    'dispatch-conf.1',
    'ebuild.1',
    'env-update.1',
    'etc-update.1',
    'fixpackages.1',
]

foreach man_page : man_pages_in
    man_pages_out += configure_file(
        input : man_page,
        output : man_page,
        configuration : conf_data
    )
endforeach

install_man(man_pages_out, locale : 'ru')
