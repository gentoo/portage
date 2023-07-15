subdir('api')
subdir('fragment')

xmlto = find_program('xmlto', required : get_option('doc'))

if not xmlto.found()
    subdir_done()
endif

docbook_src = [
    version_doc_fragment,
    'config.docbook',
    'config/bashrc.docbook',
    'config/sets.docbook',
    'custom.xsl',
    'dependency_resolution.docbook',
    'dependency_resolution/decision_making.docbook',
    'dependency_resolution/package_modeling.docbook',
    'dependency_resolution/task_scheduling.docbook',
    'package.docbook',
    'package/ebuild.docbook',
    'package/ebuild/eapi/0.docbook',
    'package/ebuild/eapi/1.docbook',
    'package/ebuild/eapi/2.docbook',
    'package/ebuild/eapi/3.docbook',
    'package/ebuild/eapi/4.docbook',
    'package/ebuild/eapi/4-slot-abi.docbook',
    'package/ebuild/eapi/5.docbook',
    'package/ebuild/helper_functions.docbook',
    'package/ebuild/phases.docbook',
    'portage.docbook',
    'qa.docbook'
]

custom_target(
    'xhtml-nochunks',
    depend_files : docbook_src,
    output : ['portage.html'],
    command : ['xmlto', '-o', '@OUTDIR@', '--searchpath', '@OUTDIR@/fragment', '-m', '@CURRENT_SOURCE_DIR@/custom.xsl', 'xhtml-nochunks', '@CURRENT_SOURCE_DIR@/portage.docbook'],
    install : get_option('doc') and get_option('doc-formats').contains('xhtml-nochunks'),
    install_dir : docdir / 'html'
)

# xhtml generates a lot of files, and it would be awkward to keep a list
# updated. This workaround is slightly hacky as you're probably not supposed to
# set "output" to a directory. Note that it cannot include a /. Another
# alternative is to use install_subdir, but it's not much better as you still
# need to set "output" to a directory.

custom_target(
    'xhtml',
    depend_files : docbook_src,
    output : ['html'],
    command : ['xmlto', '-o', '@OUTDIR@/html', '--searchpath', '@OUTDIR@/fragment', '-m', '@CURRENT_SOURCE_DIR@/custom.xsl', 'xhtml', '@CURRENT_SOURCE_DIR@/portage.docbook'],
    install : get_option('doc') and get_option('doc-formats').contains('xhtml'),
    install_dir : docdir
)
