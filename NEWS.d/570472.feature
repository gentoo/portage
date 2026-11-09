emerge: Unmerge packages in parallel with --jobs for --depclean, --prune,
--clean and AUTOCLEAN.

With --depclean, and --prune without --nodeps, a package is unmerged only
after the packages that depend on it.
