unmerge: Skip the pkg_prerm and pkg_postrm spawns when neither the package
nor any bashrc or ebuild hook file defines them.

Top-level bashrc code therefore no longer runs for those phases of such
packages.
