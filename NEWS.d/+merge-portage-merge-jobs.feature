merge: Add PORTAGE_MERGE_JOBS, which sets the number of threads that merge
the files of a single package from the image directory into ${ROOT}. The
default of 1 merges the files sequentially, like before. If set to "auto",
then the -j value in MAKEOPTS is used, falling back to the number of CPUs.
