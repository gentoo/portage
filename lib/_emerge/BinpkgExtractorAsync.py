# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging

from _emerge.SpawnProcess import SpawnProcess
import portage
from portage.util.compression_probe import (
    compression_probe,
    _compressors,
)
from portage.util.cpuinfo import makeopts_to_job_count
from portage.process import find_binary
from portage.util import (
    shlex_split,
    varexpand,
)
from portage.exception import InvalidBinaryPackageFormat
from portage.binpkg import get_binpkg_format
import signal
import subprocess
import tarfile
import textwrap


class BinpkgExtractorAsync(SpawnProcess):
    __slots__ = ("features", "image_dir", "pkg", "pkg_path")

    _shell_binary = portage.const.BASH_BINARY

    def _start(self):
        binpkg_format = get_binpkg_format(self.pkg_path)
        if binpkg_format == "xpak":
            self._xpak_start()
        else:
            raise InvalidBinaryPackageFormat(
                f"{self.pkg_path} is not a valid xpak binary package"
            )

    def _xpak_start(self):
        tar_options = ""
        if "xattr" in self.features:
            process = subprocess.Popen(
                ["tar", "--help"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            output = process.communicate()[0]
            if b"--xattrs" in output:
                tar_options = ["--xattrs", "--xattrs-include='*'"]
                for x in portage.util.shlex_split(
                    self.env.get("PORTAGE_XATTR_EXCLUDE", "")
                ):
                    tar_options.append(portage._shell_quote(f"--xattrs-exclude={x}"))
                tar_options = " ".join(tar_options)

        decomp = _compressors.get(compression_probe(self.pkg_path))
        if decomp is not None:
            decomp_cmd = decomp.get("decompress")
            decomp_cmd = decomp_cmd.replace(
                "{JOBS}", str(makeopts_to_job_count(self.env.get("MAKEOPTS", "1")))
            )
        elif tarfile.is_tarfile(
            portage._unicode_encode(
                self.pkg_path, encoding=portage._encodings["fs"], errors="strict"
            )
        ):
            decomp_cmd = "cat"
            decomp = {
                "compress": "cat",
                "package": "sys-apps/coreutils",
            }
        else:
            decomp_cmd = None
        if decomp_cmd is None:
            self.scheduler.output(
                f"!!! File compression header unrecognized: {self.pkg_path}\n",
                log_path=self.logfile,
                background=self.background,
                level=logging.ERROR,
            )
            self.returncode = 1
            self._async_wait()
            return

        try:
            decompression_binary = shlex_split(varexpand(decomp_cmd, mydict=self.env))[
                0
            ]
        except IndexError:
            decompression_binary = ""

        if find_binary(decompression_binary) is None:
            # Try alternative command if it exists
            if decomp.get("decompress_alt"):
                decomp_cmd = decomp.get("decompress_alt")
            try:
                decompression_binary = shlex_split(
                    varexpand(decomp_cmd, mydict=self.env)
                )[0]
            except IndexError:
                decompression_binary = ""

            if find_binary(decompression_binary) is None:
                missing_package = decomp.get("package")
                self.scheduler.output(
                    f"!!! File compression unsupported {self.pkg_path}.\n"
                    f" Command was: {varexpand(decomp_cmd, mydict=self.env)}.\n"
                    f" Missing package: {missing_package}\n",
                    log_path=self.logfile,
                    background=self.background,
                    level=logging.ERROR,
                )
                self.returncode = 1
                self._async_wait()
                return

        pkg_xpak = portage.xpak.tbz2(self.pkg_path)
        pkg_xpak.scan()

        # SIGPIPE handling (128 + SIGPIPE) should be compatible with
        # assert_sigpipe_ok() that's used by the ebuild unpack() helper.
        self.args = [
            self._shell_binary,
            "-c",
            textwrap.dedent(
                f"""
                    cmd0=(head -c {pkg_xpak.filestat.st_size - pkg_xpak.xpaksize} -- {portage._shell_quote(self.pkg_path)})
                    cmd1=({decomp_cmd})
                    cmd2=(tar -xp {tar_options} -C {portage._shell_quote(self.image_dir)} -f -);
                """
                """
                    "${cmd0[@]}" | "${cmd1[@]}" | "${cmd2[@]}";
                    p=(${PIPESTATUS[@]}) ; for i in {0..2}; do
                """
                f"""
                    if [[ ${{p[$i]}} != 0 && ${{p[$i]}} != {128 + signal.SIGPIPE} ]] ; then
                """
                """
                    echo command $(eval "echo \\"'\\${cmd$i[*]}'\\"") failed with status ${p[$i]} ;
                    exit ${p[$i]} ; fi ; done;
                    if [ ${p[$i]} != 0 ] ; then
                    echo command $(eval "echo \\"'\\${cmd$i[*]}'\\"") failed with status ${p[$i]} ;
                    exit ${p[$i]} ; fi ;
                    exit 0 ;
                """
            )
            .replace("\n", " ")
            .strip(),
        ]

        SpawnProcess._start(self)
