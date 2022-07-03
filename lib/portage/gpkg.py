# Copyright 2001-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import tarfile
import io
import threading
import subprocess
import errno
import pwd
import grp
import stat
import sys
import tempfile
from copy import copy
from datetime import datetime

from portage import checksum
from portage import os
from portage import shutil
from portage import normalize_path
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.exception import (
    FileNotFound,
    InvalidBinaryPackageFormat,
    InvalidCompressionMethod,
    CompressorNotFound,
    CompressorOperationFailed,
    CommandNotFound,
    GPGException,
    DigestException,
    MissingSignature,
    InvalidSignature,
)
from portage.output import colorize
from portage.util._urlopen import urlopen
from portage.util import writemsg
from portage.util import shlex_split, varexpand
from portage.util.compression_probe import _compressors
from portage.process import find_binary
from portage.const import MANIFEST2_HASH_DEFAULTS, HASHING_BLOCKSIZE


class tar_stream_writer:
    """
    One-pass helper function that return a file-like object
    for create a file inside of a tar container.

    This helper allowed streaming add a new file to tar
    without prior knows the file size.

    With optional call and pipe data through external program,
    the helper can transparently save compressed data.

    With optional checksum helper, this helper can create
    corresponding checksum and GPG signature.

    Example:

    writer = tar_stream_writer(
            file_tarinfo,            # the file tarinfo that need to be added
            container,               # the outer container tarfile object
            tarfile.USTAR_FORMAT,    # the outer container format
            ["gzip"],                # compression command
            checksum_helper          # checksum helper
    )

    writer.write(data)
    writer.close()
    """

    def __init__(
        self,
        tarinfo,
        container,
        tar_format,
        cmd=None,
        checksum_helper=None,
        uid=None,
        gid=None,
    ):
        """
        tarinfo          # the file tarinfo that need to be added
        container        # the outer container tarfile object
        tar_format       # the outer container format for create the tar header
        cmd              # subprocess.Popen format compression command
        checksum_helper  # checksum helper
        uid              # drop root user to uid
        gid              # drop root group to gid
        """
        self.checksum_helper = checksum_helper
        self.closed = False
        self.container = container
        self.killed = False
        self.tar_format = tar_format
        self.tarinfo = tarinfo
        self.uid = uid
        self.gid = gid

        # Record container end position
        self.container.fileobj.seek(0, io.SEEK_END)
        self.begin_position = self.container.fileobj.tell()
        self.end_position = 0
        self.file_size = 0

        # Write tar header without size
        tar_header = self.tarinfo.tobuf(
            self.tar_format, self.container.encoding, self.container.errors
        )
        self.header_size = len(tar_header)
        self.container.fileobj.write(tar_header)
        self.container.fileobj.flush()
        self.container.offset += self.header_size

        # Start external compressor if needed
        if cmd is None:
            self.proc = None
        else:
            if sys.hexversion >= 0x03090000:
                self.proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    user=self.uid,
                    group=self.gid,
                )
            else:
                self.proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=self._drop_privileges,
                )

            self.read_thread = threading.Thread(
                target=self._cmd_read_thread, name="tar_stream_cmd_read", daemon=True
            )
            self.read_thread.start()

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _drop_privileges(self):
        if self.uid:
            try:
                os.setuid(self.uid)
            except PermissionError:
                writemsg(
                    colorize(
                        "BAD", f"!!! Drop root privileges to user {self.uid} failed."
                    )
                )
                raise

        if self.gid:
            try:
                os.setgid(self.gid)
            except PermissionError:
                writemsg(
                    colorize(
                        "BAD", f"!!! Drop root privileges to group {self.gid} failed."
                    )
                )
                raise

    def kill(self):
        """
        kill external program if any error happened in python
        """
        if self.proc is not None:
            self.killed = True
            self.proc.kill()
            self.proc.stdin.close()
            self.close()

    def _cmd_read_thread(self):
        """
        Use thread to avoid block.
        Read stdout from external compressor, then write to the file
        in container, and to checksum helper if needed.
        """
        while True:
            try:
                buffer = self.proc.stdout.read(HASHING_BLOCKSIZE)
                if not buffer:
                    self.proc.stdout.close()
                    self.proc.stderr.close()
                    return
            except BrokenPipeError:
                self.proc.stdout.close()
                if not self.killed:
                    # Do not raise error if killed by portage
                    raise CompressorOperationFailed("PIPE broken")

            self.container.fileobj.write(buffer)
            if self.checksum_helper:
                self.checksum_helper.update(buffer)

    def write(self, data):
        """
        Write data to tarfile or external compressor stdin
        """
        if self.closed:
            raise OSError("writer closed")

        if self.proc:
            # Write to external program
            self.proc.stdin.write(data)
        else:
            # Write to container
            self.container.fileobj.write(data)
            if self.checksum_helper:
                self.checksum_helper.update(data)

    def close(self):
        """
        Update the new file tar header when close
        """
        if self.closed:
            return

        # Wait compressor exit
        if self.proc is not None:
            self.proc.stdin.close()
            if self.proc.wait() != os.EX_OK:
                raise CompressorOperationFailed("compression failed")
            if self.read_thread.is_alive():
                self.read_thread.join()

        # Get container end position and calculate file size
        self.container.fileobj.seek(0, io.SEEK_END)
        self.end_position = self.container.fileobj.tell()
        self.file_size = self.end_position - self.begin_position - self.header_size
        self.tarinfo.size = self.file_size

        # Tar block is 512, need padding \0
        _, remainder = divmod(self.file_size, 512)
        if remainder > 0:
            padding_size = 512 - remainder
            self.container.fileobj.write(b"\0" * padding_size)
            self.container.offset += padding_size
            self.container.fileobj.flush()

        # Update tar header
        tar_header = self.tarinfo.tobuf(
            self.tar_format, self.container.encoding, self.container.errors
        )
        self.container.fileobj.seek(self.begin_position)
        self.container.fileobj.write(tar_header)
        self.container.fileobj.seek(0, io.SEEK_END)
        self.container.fileobj.flush()
        self.container.offset = self.container.fileobj.tell()
        self.closed = True

        # Add tarinfo to tarfile
        self.container.members.append(self.tarinfo)

        if self.checksum_helper:
            self.checksum_helper.finish()

        self.closed = True


class tar_stream_reader:
    """
    helper function that return a file-like object
    for read a file inside of a tar container.

    This helper allowed transparently streaming read a compressed
    file in tar.

    With optional call and pipe compressed data through external
    program, and return the uncompressed data.

    reader = tar_stream_reader(
            fileobj,             # the fileobj from tarfile.extractfile(f)
            ["gzip", "-d"],      # decompression command
    )

    reader.read()
    reader.close()
    """

    def __init__(self, fileobj, cmd=None, uid=None, gid=None):
        """
        fileobj should be a file-like object that have read().
        cmd is optional external decompressor command.
        """
        self.closed = False
        self.cmd = cmd
        self.fileobj = fileobj
        self.killed = False
        self.uid = uid
        self.gid = gid

        if cmd is None:
            self.read_io = fileobj
            self.proc = None
        else:
            # Start external decompressor
            if sys.hexversion >= 0x03090000:
                self.proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    user=self.uid,
                    group=self.gid,
                )
            else:
                self.proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=self._drop_privileges,
                )
            self.read_io = self.proc.stdout
            # Start stdin block writing thread
            self.thread = threading.Thread(
                target=self._write_thread, name="tar_stream_stdin_writer", daemon=True
            )
            self.thread.start()

    def __del__(self):
        try:
            self.close()
        except CompressorOperationFailed:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.close()
        except CompressorOperationFailed:
            pass

    def _write_thread(self):
        """
        writing thread to avoid full buffer blocking
        """
        try:
            while True:
                buffer = self.fileobj.read(HASHING_BLOCKSIZE)
                if buffer:
                    try:
                        self.proc.stdin.write(buffer)
                    except ValueError:
                        if self.killed:
                            return
                        else:
                            raise
                else:
                    self.proc.stdin.flush()
                    self.proc.stdin.close()
                    break
        except BrokenPipeError:
            if self.killed is False:
                raise CompressorOperationFailed("PIPE broken")

    def _drop_privileges(self):
        if self.uid:
            try:
                os.setuid(self.uid)
            except PermissionError:
                writemsg(
                    colorize(
                        "BAD", f"!!! Drop root privileges to user {self.uid} failed."
                    )
                )
                raise

        if self.gid:
            try:
                os.setgid(self.gid)
            except PermissionError:
                writemsg(
                    colorize(
                        "BAD", f"!!! Drop root privileges to group {self.gid} failed."
                    )
                )
                raise

    def kill(self):
        """
        kill external program if any error happened in python
        """
        if self.proc is not None:
            self.killed = True
            self.proc.kill()
            self.proc.stdin.close()
            self.close()

    def read(self, bufsize=-1):
        """
        return decompressor stdout data
        """
        if self.closed:
            raise OSError("writer closed")
        else:
            return self.read_io.read(bufsize)

    def close(self):
        """
        wait external program complete and do clean up
        """
        if self.closed:
            return

        self.closed = True

        if self.proc is not None:
            self.thread.join()
            try:
                if self.proc.wait() != os.EX_OK:
                    if not self.proc.stderr.closed:
                        stderr = self.proc.stderr.read().decode()
                    if not self.killed:
                        writemsg(colorize("BAD", f"!!!\n{stderr}"))
                        raise CompressorOperationFailed("decompression failed")
            finally:
                self.proc.stdout.close()
                self.proc.stderr.close()


class checksum_helper:
    """
    Do checksum generation and GPG Signature generation and verification
    """

    SIGNING = 0
    VERIFY = 1

    def __init__(self, settings, gpg_operation=None, detached=True, signature=None):
        """
        settings         # portage settings
        gpg_operation    # either SIGNING or VERIFY
        signature        # GPG signature string used for GPG verify only
        """
        self.settings = settings
        self.gpg_operation = gpg_operation
        self.gpg_proc = None
        self.gpg_result = None
        self.gpg_output = None
        self.finished = False
        self.sign_file_path = None

        if (gpg_operation == checksum_helper.VERIFY) and (os.getuid() == 0):
            try:
                drop_user = self.settings.get("GPG_VERIFY_USER_DROP", "nobody")
                if drop_user == "":
                    self.uid = None
                else:
                    self.uid = pwd.getpwnam(drop_user).pw_uid
            except KeyError:
                writemsg(colorize("BAD", f"!!! Failed to find user {drop_user}."))
                raise

            try:
                drop_group = self.settings.get("GPG_VERIFY_GROUP_DROP", "nogroup")
                if drop_group == "":
                    self.gid = None
                else:
                    self.gid = grp.getgrnam(drop_group).gr_gid
            except KeyError:
                writemsg(colorize("BAD", f"!!! Failed to find group {drop_group}."))
                raise
        else:
            self.uid = None
            self.gid = None

        # Initialize the hash libs
        self.libs = {}
        for hash_name in MANIFEST2_HASH_DEFAULTS:
            self.libs[hash_name] = checksum.hashfunc_map[hash_name]._hashobject()

        # GPG
        env = self.settings.environ()
        if self.gpg_operation == checksum_helper.SIGNING:
            gpg_signing_base_command = self.settings.get(
                "BINPKG_GPG_SIGNING_BASE_COMMAND"
            )
            digest_algo = self.settings.get("BINPKG_GPG_SIGNING_DIGEST")
            gpg_home = self.settings.get("BINPKG_GPG_SIGNING_GPG_HOME")
            gpg_key = self.settings.get("BINPKG_GPG_SIGNING_KEY")

            if detached:
                gpg_detached = "--detach-sig"
            else:
                gpg_detached = "--clear-sign"

            if gpg_signing_base_command:
                gpg_signing_command = gpg_signing_base_command.replace(
                    "[PORTAGE_CONFIG]",
                    f"--homedir {gpg_home} "
                    f"--digest-algo {digest_algo} "
                    f"--local-user {gpg_key} "
                    f"{gpg_detached} "
                    "--batch --no-tty",
                )

                gpg_signing_command = shlex_split(
                    varexpand(gpg_signing_command, mydict=self.settings)
                )
                gpg_signing_command = [x for x in gpg_signing_command if x != ""]
                try:
                    env["GPG_TTY"] = os.ttyname(sys.stdout.fileno())
                except OSError:
                    pass
            else:
                raise CommandNotFound("GPG signing command is not set")

            self.gpg_proc = subprocess.Popen(
                gpg_signing_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

        elif self.gpg_operation == checksum_helper.VERIFY:
            if (signature is None) and (detached == True):
                raise MissingSignature("No signature provided")

            gpg_verify_base_command = self.settings.get(
                "BINPKG_GPG_VERIFY_BASE_COMMAND"
            )
            gpg_home = self.settings.get("BINPKG_GPG_VERIFY_GPG_HOME")

            if not gpg_verify_base_command:
                raise CommandNotFound("GPG verify command is not set")

            gpg_verify_command = gpg_verify_base_command.replace(
                "[PORTAGE_CONFIG]", f"--homedir {gpg_home} "
            )

            if detached:
                self.sign_file_fd, self.sign_file_path = tempfile.mkstemp(
                    ".sig", "portage-sign-"
                )

                gpg_verify_command = gpg_verify_command.replace(
                    "[SIGNATURE]", f"{self.sign_file_path} -"
                )

                # Create signature file and allow everyone read
                with open(self.sign_file_fd, "wb") as sign:
                    sign.write(signature)
                os.chmod(self.sign_file_path, 0o644)
            else:
                gpg_verify_command = gpg_verify_command.replace(
                    "[SIGNATURE]", "--output - -"
                )

            gpg_verify_command = shlex_split(
                varexpand(gpg_verify_command, mydict=self.settings)
            )
            gpg_verify_command = [x for x in gpg_verify_command if x != ""]

            if sys.hexversion >= 0x03090000:
                self.gpg_proc = subprocess.Popen(
                    gpg_verify_command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    user=self.uid,
                    group=self.gid,
                )

            else:
                self.gpg_proc = subprocess.Popen(
                    gpg_verify_command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    preexec_fn=self._drop_privileges,
                )

    def __del__(self):
        self.finish()

    def _check_gpg_status(self, gpg_status):
        """
        Check GPG status log for extra info.
        GPG will return OK even if the signature owner is not trusted.
        """
        good_signature = False
        trust_signature = False

        for l in gpg_status.splitlines():
            if l.startswith("[GNUPG:] GOODSIG"):
                good_signature = True

            if l.startswith("[GNUPG:] TRUST_ULTIMATE") or l.startswith(
                "[GNUPG:] TRUST_FULLY"
            ):
                trust_signature = True

        if (not good_signature) or (not trust_signature):
            writemsg(colorize("BAD", f"!!!\n{self.gpg_result.decode()}"))
            raise InvalidSignature("GPG verify failed")

    def _drop_privileges(self):
        if self.uid:
            try:
                os.setuid(self.uid)
            except PermissionError:
                writemsg(
                    colorize(
                        "BAD", f"!!! Drop root privileges to user {self.uid} failed."
                    )
                )
                raise

        if self.gid:
            try:
                os.setgid(self.gid)
            except PermissionError:
                writemsg(
                    colorize(
                        "BAD", f"!!! Drop root privileges to group {self.gid} failed."
                    )
                )
                raise

    def update(self, data):
        """
        Write data to hash libs and GPG stdin.
        """
        for c in self.libs:
            self.libs[c].update(data)

        if self.gpg_proc is not None:
            self.gpg_proc.stdin.write(data)

    def finish(self):
        """
        Tell GPG file is EOF, and get results, then do clean up.
        """
        if self.finished:
            return

        if self.gpg_proc is not None:
            # Tell GPG EOF
            self.gpg_proc.stdin.close()

            return_code = self.gpg_proc.wait()

            if self.sign_file_path:
                os.remove(self.sign_file_path)

            self.finished = True

            self.gpg_result = self.gpg_proc.stderr.read()
            self.gpg_output = self.gpg_proc.stdout.read()
            self.gpg_proc.stdout.close()
            self.gpg_proc.stderr.close()

            if return_code == os.EX_OK:
                if self.gpg_operation == checksum_helper.VERIFY:
                    self._check_gpg_status(self.gpg_result.decode())
            else:
                writemsg(colorize("BAD", f"!!!\n{self.gpg_result.decode()}"))
                if self.gpg_operation == checksum_helper.SIGNING:
                    writemsg(colorize("BAD", self.gpg_output.decode()))
                    raise GPGException("GPG signing failed")
                elif self.gpg_operation == checksum_helper.VERIFY:
                    raise InvalidSignature("GPG verify failed")


class tar_safe_extract:
    """
    A safer version of tar extractall that doing sanity check.
    Note that this does not solve all security problems.
    """

    def __init__(self, tar: tarfile.TarFile, prefix: str = ""):
        """
        tar: an opened TarFile that ready to be read.
        prefix: a optional prefix for an inner directory should be considered
        as the root directory. e.g. "metadata" and "image".
        """
        self.tar = tar
        self.prefix = prefix
        self.closed = False
        self.file_list = []

    def extractall(self, dest_dir: str):
        """
        Extract all files to a temporary directory in the dest_dir, and move
        them to the dest_dir after sanity check.
        """
        if self.closed:
            raise IOError("Tar file is closed.")
        temp_dir = tempfile.TemporaryDirectory(dir=dest_dir)
        try:
            while True:
                member = self.tar.next()
                if member is None:
                    break
                if (member.name in self.file_list) or (
                    os.path.join(".", member.name) in self.file_list
                ):
                    writemsg(
                        colorize(
                            "BAD", f"Danger: duplicate files detected: {member.name}"
                        )
                    )
                    raise ValueError("Duplicate files detected.")
                if member.name.startswith("/"):
                    writemsg(
                        colorize(
                            "BAD", f"Danger: absolute path detected: {member.name}"
                        )
                    )
                    raise ValueError("Absolute path detected.")
                if member.name.startswith("../") or ("/../" in member.name):
                    writemsg(
                        colorize(
                            "BAD", f"Danger: path traversal detected: {member.name}"
                        )
                    )
                    raise ValueError("Path traversal detected.")
                if member.isdev():
                    writemsg(
                        colorize("BAD", f"Danger: device file detected: {member.name}")
                    )
                    raise ValueError("Device file detected.")
                if member.islnk() and (member.linkname not in self.file_list):
                    writemsg(
                        colorize(
                            "BAD", f"Danger: hardlink escape detected: {member.name}"
                        )
                    )
                    raise ValueError("Hardlink escape detected.")

                self.file_list.append(member.name)
                self.tar.extract(member, path=temp_dir.name)

            data_dir = os.path.join(temp_dir.name, self.prefix)
            for file in os.listdir(data_dir):
                shutil.move(os.path.join(data_dir, file), os.path.join(dest_dir, file))
        finally:
            temp_dir.cleanup()
            self.closed = True


class gpkg:
    """
    Gentoo binary package
    https://www.gentoo.org/glep/glep-0078.html
    """

    def __init__(self, settings, base_name=None, gpkg_file=None):
        """
        gpkg class handle all gpkg operations for one package.
        base_name is the package basename.
        gpkg_file should be exists file path for read or will create.
        """
        if sys.version_info.major < 3:
            raise InvalidBinaryPackageFormat("GPKG not support Python 2")
        self.settings = settings
        self.gpkg_version = "gpkg-1"
        if gpkg_file is None:
            self.gpkg_file = None
        else:
            self.gpkg_file = _unicode_decode(
                gpkg_file, encoding=_encodings["fs"], errors="strict"
            )
        self.base_name = base_name
        self.checksums = []
        self.manifest_old = []

        # Compression is the compression algorithm, if set to None will
        # not use compression.
        self.compression = self.settings.get("BINPKG_COMPRESS", None)
        if self.compression in ["", "none"]:
            self.compression = None

        # The create_signature is whether create signature for the package or not.
        if "binpkg-signing" in self.settings.features:
            self.create_signature = True
        else:
            self.create_signature = False

        # The request_signature is whether signature files are mandatory.
        # If set true, any missing signature file will cause reject processing.
        if "binpkg-request-signature" in self.settings.features:
            self.request_signature = True
        else:
            self.request_signature = False

        # The verify_signature is whether verify package signature or not.
        # In rare case user may want to ignore signature,
        # E.g. package with expired signature.
        if "binpkg-ignore-signature" in self.settings.features:
            self.verify_signature = False
        else:
            self.verify_signature = True

        self.ext_list = {
            "gzip": ".gz",
            "bzip2": ".bz2",
            "lz4": ".lz4",
            "lzip": ".lz",
            "lzop": ".lzo",
            "xz": ".xz",
            "zstd": ".zst",
        }

    def unpack_metadata(self, dest_dir=None):
        """
        Unpack metadata to dest_dir.
        If dest_dir is None, return files and values in dict.
        The dict key will be UTF-8, not bytes.
        """
        self._verify_binpkg(metadata_only=True)

        with tarfile.open(self.gpkg_file, "r") as container:
            metadata_tarinfo, metadata_comp = self._get_inner_tarinfo(
                container, "metadata"
            )

            with tar_stream_reader(
                container.extractfile(metadata_tarinfo),
                self._get_decompression_cmd(metadata_comp),
            ) as metadata_reader:
                metadata_tar = io.BytesIO(metadata_reader.read())

            with tarfile.open(mode="r:", fileobj=metadata_tar) as metadata:
                if dest_dir is None:
                    metadata_ = {
                        os.path.relpath(k.name, "metadata"): metadata.extractfile(
                            k
                        ).read()
                        for k in metadata.getmembers()
                    }
                else:
                    metadata_safe = tar_safe_extract(metadata, "metadata")
                    metadata_safe.extractall(dest_dir)
                    metadata_ = True
            metadata_tar.close()
        return metadata_

    def get_metadata(self, want=None):
        """
        get package metadata.
        if want is list, return all want key-values in dict
        if want is str, return the want key value
        """
        if want is None:
            return self.unpack_metadata()
        elif isinstance(want, str):
            metadata = self.unpack_metadata()
            metadata_want = metadata.get(want, None)
            return metadata_want
        else:
            metadata = self.unpack_metadata()
            metadata_want = {k: metadata.get(k, None) for k in want}
            return metadata_want

    def get_metadata_url(self, url, want=None):
        """
        Return the requested metadata from url gpkg.
        Default return all meta data.
        Use 'want' to get specific name from metadata.
        This method only support the correct package format.
        Wrong files order or incorrect basename will be considered invalid
        to reduce potential attacks.
        Only signature will be check if the signature file is the next file.
        Manifest will be ignored since it will be at the end of package.
        """
        # The init download file head size
        init_size = 51200

        # Load remote container
        container_file = io.BytesIO(
            urlopen(url, headers={"Range": "bytes=0-" + str(init_size)}).read()
        )

        # Check gpkg and metadata
        with tarfile.open(mode="r", fileobj=container_file) as container:
            if self.gpkg_version not in container.getnames():
                raise InvalidBinaryPackageFormat("Invalid gpkg file.")

            metadata_tarinfo, metadata_comp = self._get_inner_tarinfo(
                container, "metadata"
            )

            # Extra 10240 bytes for signature
            end_size = metadata_tarinfo.offset_data + metadata_tarinfo.size + 10240
            _, remainder = divmod(end_size, 512)
            end_size += 512 - remainder

            # If need more data
            if end_size > 10000000:
                raise InvalidBinaryPackageFormat("metadata too large " + str(end_size))
            if end_size > init_size:
                container_file.seek(0, io.SEEK_END)
                container_file.write(
                    urlopen(
                        url,
                        headers={"Range": f"bytes={init_size + 1}-{end_size}"},
                    ).read()
                )

        container_file.seek(0)

        # Reload and process full metadata
        with tarfile.open(mode="r", fileobj=container_file) as container:
            metadata_tarinfo, metadata_comp = self._get_inner_tarinfo(
                container, "metadata"
            )

            # Verify metadata file signature if needed
            # binpkg-ignore-signature can override this.
            signature_filename = metadata_tarinfo.name + ".sig"
            if signature_filename in container.getnames():
                if self.request_signature and self.verify_signature:
                    metadata_signature = container.extractfile(
                        signature_filename
                    ).read()
                    checksum_info = checksum_helper(
                        self.settings,
                        gpg_operation=checksum_helper.VERIFY,
                        signature=metadata_signature,
                    )
                    checksum_info.update(container.extractfile(metadata_tarinfo).read())
                    checksum_info.finish()

            # Load metadata
            with tar_stream_reader(
                container.extractfile(metadata_tarinfo),
                self._get_decompression_cmd(metadata_comp),
            ) as metadata_reader:
                metadata_file = io.BytesIO(metadata_reader.read())

            with tarfile.open(mode="r:", fileobj=metadata_file) as metadata:
                if want is None:
                    metadata_ = {
                        os.path.relpath(k.name, "metadata"): metadata.extractfile(
                            k
                        ).read()
                        for k in metadata.getmembers()
                    }
                else:
                    metadata_ = {
                        os.path.relpath(k.name, "metadata"): metadata.extractfile(
                            k
                        ).read()
                        for k in metadata.getmembers()
                        if k in want
                    }
            metadata_file.close()
        container_file.close()
        return metadata_

    def compress(self, root_dir, metadata, clean=False):
        """
        Use initialized configuation create new gpkg file from root_dir.
        Will overwrite any exists file.
        metadata is a dict, the key will be file name, the value will be
        the file contents.
        """

        root_dir = normalize_path(
            _unicode_decode(root_dir, encoding=_encodings["fs"], errors="strict")
        )

        # Get pre image info
        container_tar_format, image_tar_format = self._get_tar_format_from_stats(
            *self._check_pre_image_files(root_dir)
        )

        # Long CPV
        if len(self.base_name) >= 154:
            container_tar_format = tarfile.GNU_FORMAT

        # gpkg container
        container = tarfile.TarFile(
            name=self.gpkg_file, mode="w", format=container_tar_format
        )

        # gpkg version
        gpkg_version_file = tarfile.TarInfo(self.gpkg_version)
        gpkg_version_file.mtime = datetime.utcnow().timestamp()
        container.addfile(gpkg_version_file)

        compression_cmd = self._get_compression_cmd()

        # metadata
        self._add_metadata(container, metadata, compression_cmd)

        # image
        if self.create_signature:
            checksum_info = checksum_helper(
                self.settings, gpg_operation=checksum_helper.SIGNING
            )
        else:
            checksum_info = checksum_helper(self.settings)

        image_tarinfo = self._create_tarinfo("image")
        image_tarinfo.mtime = datetime.utcnow().timestamp()
        with tar_stream_writer(
            image_tarinfo, container, image_tar_format, compression_cmd, checksum_info
        ) as image_writer:
            with tarfile.open(
                mode="w|", fileobj=image_writer, format=image_tar_format
            ) as image_tar:
                image_tar.add(root_dir, "image", recursive=True)

        image_tarinfo = container.getmember(image_tarinfo.name)
        self._record_checksum(checksum_info, image_tarinfo)

        if self.create_signature:
            self._add_signature(checksum_info, image_tarinfo, container)

        self._add_manifest(container)
        container.close()

    def decompress(self, decompress_dir):
        """
        decompress current gpkg to decompress_dir
        """
        decompress_dir = normalize_path(
            _unicode_decode(decompress_dir, encoding=_encodings["fs"], errors="strict")
        )

        self._verify_binpkg()
        os.makedirs(decompress_dir, mode=0o755, exist_ok=True)

        with tarfile.open(self.gpkg_file, "r") as container:
            image_tarinfo, image_comp = self._get_inner_tarinfo(container, "image")

            with tar_stream_reader(
                container.extractfile(image_tarinfo),
                self._get_decompression_cmd(image_comp),
            ) as image_tar:

                with tarfile.open(mode="r|", fileobj=image_tar) as image:
                    try:
                        image_safe = tar_safe_extract(image, "image")
                        image_safe.extractall(decompress_dir)
                    except Exception as ex:
                        writemsg(colorize("BAD", "!!!Extract failed."))
                        raise
                    finally:
                        image_tar.kill()

    def update_metadata(self, metadata, newcpv=None):
        """
        Update metadata in the gpkg file.
        """
        self._verify_binpkg()
        self.checksums = []
        oldcpv = None

        if newcpv:
            oldcpv = self.base_name

        with open(self.gpkg_file, "rb") as container:
            container_tar_format = self._get_tar_format(container)
            if container_tar_format is None:
                raise InvalidBinaryPackageFormat("Cannot identify tar format")

        # container
        tmp_gpkg_file_name = f"{self.gpkg_file}.{os.getpid()}"
        with tarfile.TarFile(
            name=tmp_gpkg_file_name, mode="w", format=container_tar_format
        ) as container:
            # gpkg version
            gpkg_version_file = tarfile.TarInfo(self.gpkg_version)
            gpkg_version_file.mtime = datetime.utcnow().timestamp()
            container.addfile(gpkg_version_file)

            compression_cmd = self._get_compression_cmd()

            # metadata
            if newcpv:
                self.base_name = newcpv
                self._add_metadata(container, metadata, compression_cmd)
                self.base_name = oldcpv
            else:
                self._add_metadata(container, metadata, compression_cmd)

            # reuse other stuffs
            with tarfile.open(self.gpkg_file, "r") as container_old:
                manifest_old = self.manifest_old.copy()

                for m in manifest_old:
                    file_name_old = m[1]
                    if os.path.basename(file_name_old).startswith("metadata"):
                        continue
                    old_data_tarinfo = container_old.getmember(file_name_old)
                    new_data_tarinfo = copy(old_data_tarinfo)
                    if newcpv:
                        m[1] = m[1].replace(oldcpv, newcpv, 1)
                        new_data_tarinfo.name = new_data_tarinfo.name.replace(
                            oldcpv, newcpv, 1
                        )
                    container.addfile(
                        new_data_tarinfo, container_old.extractfile(old_data_tarinfo)
                    )
                    self.checksums.append(m)

            self._add_manifest(container)

        shutil.move(tmp_gpkg_file_name, self.gpkg_file)

    def _add_metadata(self, container, metadata, compression_cmd):
        """
        add metadata to container
        """
        if metadata is None:
            metadata = {}
        metadata_tarinfo = self._create_tarinfo("metadata")
        metadata_tarinfo.mtime = datetime.utcnow().timestamp()

        if self.create_signature:
            checksum_info = checksum_helper(
                self.settings, gpg_operation=checksum_helper.SIGNING
            )
        else:
            checksum_info = checksum_helper(self.settings)

        with tar_stream_writer(
            metadata_tarinfo,
            container,
            tarfile.USTAR_FORMAT,
            compression_cmd,
            checksum_info,
        ) as metadata_writer:
            with tarfile.open(
                mode="w|", fileobj=metadata_writer, format=tarfile.USTAR_FORMAT
            ) as metadata_tar:

                for m in metadata:
                    m_info = tarfile.TarInfo(os.path.join("metadata", m))
                    m_info.mtime = datetime.utcnow().timestamp()

                    if isinstance(metadata[m], bytes):
                        m_data = io.BytesIO(metadata[m])
                    else:
                        m_data = io.BytesIO(metadata[m].encode("UTF-8"))

                    m_data.seek(0, io.SEEK_END)
                    m_info.size = m_data.tell()
                    m_data.seek(0)
                    metadata_tar.addfile(m_info, m_data)
                    m_data.close()

        metadata_tarinfo = container.getmember(metadata_tarinfo.name)
        self._record_checksum(checksum_info, metadata_tarinfo)

        if self.create_signature:
            self._add_signature(checksum_info, metadata_tarinfo, container)

    def _quickpkg(self, contents, metadata, root_dir, protect=None):
        """
        Similar to compress, but for quickpkg.
        Will compress the given files to image with root,
        ignoring all other files.
        """

        protect_file = io.BytesIO(
            b"# empty file because --include-config=n when `quickpkg` was used\n"
        )
        protect_file.seek(0, io.SEEK_END)
        protect_file_size = protect_file.tell()

        root_dir = normalize_path(
            _unicode_decode(root_dir, encoding=_encodings["fs"], errors="strict")
        )

        # Get pre image info
        container_tar_format, image_tar_format = self._get_tar_format_from_stats(
            *self._check_pre_quickpkg_files(contents, root_dir)
        )

        # Long CPV
        if len(self.base_name) >= 154:
            container_tar_format = tarfile.GNU_FORMAT

        # GPKG container
        container = tarfile.TarFile(
            name=self.gpkg_file, mode="w", format=container_tar_format
        )

        # GPKG version
        gpkg_version_file = tarfile.TarInfo(self.gpkg_version)
        gpkg_version_file.mtime = datetime.utcnow().timestamp()
        container.addfile(gpkg_version_file)

        compression_cmd = self._get_compression_cmd()
        # Metadata
        self._add_metadata(container, metadata, compression_cmd)

        # Image
        if self.create_signature:
            checksum_info = checksum_helper(
                self.settings, gpg_operation=checksum_helper.SIGNING
            )
        else:
            checksum_info = checksum_helper(self.settings)

        paths = list(contents)
        paths.sort()
        image_tarinfo = self._create_tarinfo("image")
        image_tarinfo.mtime = datetime.utcnow().timestamp()
        with tar_stream_writer(
            image_tarinfo, container, image_tar_format, compression_cmd, checksum_info
        ) as image_writer:
            with tarfile.open(
                mode="w|", fileobj=image_writer, format=image_tar_format
            ) as image_tar:
                if len(paths) == 0:
                    tarinfo = image_tar.tarinfo("image")
                    tarinfo.type = tarfile.DIRTYPE
                    tarinfo.size = 0
                    tarinfo.mode = 0o755
                    image_tar.addfile(tarinfo)

                for path in paths:
                    try:
                        lst = os.lstat(path)
                    except OSError as e:
                        if e.errno != errno.ENOENT:
                            raise
                        del e
                        continue
                    contents_type = contents[path][0]
                    if path.startswith(root_dir):
                        arcname = "image/" + path[len(root_dir) :]
                    else:
                        raise ValueError("invalid root argument: '%s'" % root_dir)
                    live_path = path
                    if (
                        "dir" == contents_type
                        and not stat.S_ISDIR(lst.st_mode)
                        and os.path.isdir(live_path)
                    ):
                        # Even though this was a directory in the original ${D}, it exists
                        # as a symlink to a directory in the live filesystem.  It must be
                        # recorded as a real directory in the tar file to ensure that tar
                        # can properly extract it's children.
                        live_path = os.path.realpath(live_path)
                        lst = os.lstat(live_path)

                    # Since os.lstat() inside TarFile.gettarinfo() can trigger a
                    # UnicodeEncodeError when python has something other than utf_8
                    # return from sys.getfilesystemencoding() (as in bug #388773),
                    # we implement the needed functionality here, using the result
                    # of our successful lstat call. An alternative to this would be
                    # to pass in the fileobj argument to TarFile.gettarinfo(), so
                    # that it could use fstat instead of lstat. However, that would
                    # have the unwanted effect of dereferencing symlinks.

                    tarinfo = image_tar.tarinfo(arcname)
                    tarinfo.mode = lst.st_mode
                    tarinfo.uid = lst.st_uid
                    tarinfo.gid = lst.st_gid
                    tarinfo.size = 0
                    tarinfo.mtime = lst.st_mtime
                    tarinfo.linkname = ""
                    if stat.S_ISREG(lst.st_mode):
                        inode = (lst.st_ino, lst.st_dev)
                        if (
                            lst.st_nlink > 1
                            and inode in image_tar.inodes
                            and arcname != image_tar.inodes[inode]
                        ):
                            tarinfo.type = tarfile.LNKTYPE
                            tarinfo.linkname = image_tar.inodes[inode]
                        else:
                            image_tar.inodes[inode] = arcname
                            tarinfo.type = tarfile.REGTYPE
                            tarinfo.size = lst.st_size
                    elif stat.S_ISDIR(lst.st_mode):
                        tarinfo.type = tarfile.DIRTYPE
                    elif stat.S_ISLNK(lst.st_mode):
                        tarinfo.type = tarfile.SYMTYPE
                        tarinfo.linkname = os.readlink(live_path)
                    else:
                        continue
                    try:
                        tarinfo.uname = pwd.getpwuid(tarinfo.uid)[0]
                    except KeyError:
                        pass
                    try:
                        tarinfo.gname = grp.getgrgid(tarinfo.gid)[0]
                    except KeyError:
                        pass

                    if stat.S_ISREG(lst.st_mode):
                        if protect and protect(path):
                            protect_file.seek(0)
                            tarinfo.size = protect_file_size
                            image_tar.addfile(tarinfo, protect_file)
                        else:
                            path_bytes = _unicode_encode(
                                path, encoding=_encodings["fs"], errors="strict"
                            )

                            with open(path_bytes, "rb") as f:
                                image_tar.addfile(tarinfo, f)

                    else:
                        image_tar.addfile(tarinfo)

        image_tarinfo = container.getmember(image_tarinfo.name)
        self._record_checksum(checksum_info, image_tarinfo)

        if self.create_signature:
            self._add_signature(checksum_info, image_tarinfo, container)

        self._add_manifest(container)
        container.close()

    def _record_checksum(self, checksum_info, tarinfo):
        """
        Record checksum result for the given file.
        Replace old checksum if already exists.
        """
        for c in self.checksums:
            if c[1] == tarinfo.name:
                self.checksums.remove(c)
                break

        checksum_record = ["DATA", tarinfo.name, str(tarinfo.size)]

        for c in checksum_info.libs:
            checksum_record.append(c)
            checksum_record.append(checksum_info.libs[c].hexdigest())

        self.checksums.append(checksum_record)

    def _add_manifest(self, container):
        """
        Add Manifest to the container based on current checksums.
        Creare GPG signatue if needed.
        """
        manifest = io.BytesIO()

        for m in self.checksums:
            manifest.write((" ".join(m) + "\n").encode("UTF-8"))

        if self.create_signature:
            checksum_info = checksum_helper(
                self.settings, gpg_operation=checksum_helper.SIGNING, detached=False
            )
            checksum_info.update(manifest.getvalue())
            checksum_info.finish()
            manifest.seek(0)
            manifest.write(checksum_info.gpg_output)

        manifest_tarinfo = tarfile.TarInfo("Manifest")
        manifest_tarinfo.size = manifest.tell()
        manifest_tarinfo.mtime = datetime.utcnow().timestamp()
        manifest.seek(0)
        container.addfile(manifest_tarinfo, manifest)
        manifest.close()

    def _load_manifest(self, manifest_string):
        """
        Check, load, and return manifest in a list by files
        """
        manifest = []
        manifest_filenames = []

        for manifest_record in manifest_string.splitlines():
            if manifest_record == "":
                continue
            manifest_record = manifest_record.strip().split()

            if manifest_record[0] != "DATA":
                raise DigestException("invalied Manifest")

            if manifest_record[1] in manifest_filenames:
                raise DigestException("Manifest duplicate file exists")

            try:
                int(manifest_record[2])
            except ValueError:
                raise DigestException("Manifest invalied file size")

            manifest.append(manifest_record)
            manifest_filenames.append(manifest_record[1])

        return manifest

    def _add_signature(self, checksum_info, tarinfo, container, manifest=True):
        """
        Add GPG signature for the given tarinfo file.
        manifest: add to manifest
        """
        if checksum_info.gpg_output is None:
            raise GPGException("GPG signature is not exists")

        signature = io.BytesIO(checksum_info.gpg_output)
        signature_tarinfo = tarfile.TarInfo(f"{tarinfo.name}.sig")
        signature_tarinfo.size = len(signature.getvalue())
        signature_tarinfo.mtime = datetime.utcnow().timestamp()
        container.addfile(signature_tarinfo, signature)

        if manifest:
            signature_checksum_info = checksum_helper(self.settings)
            signature.seek(0)
            signature_checksum_info.update(signature.read())
            signature_checksum_info.finish()
            self._record_checksum(signature_checksum_info, signature_tarinfo)

        signature.close()

    def _verify_binpkg(self, metadata_only=False):
        """
        Verify current GPKG file.
        """
        # Check file path
        if self.gpkg_file is None:
            raise FileNotFound("no gpkg file provided")

        # Check if is file
        if not os.path.isfile(self.gpkg_file):
            raise FileNotFound(f"File not found {self.gpkg_file}")

        # Check if is tar file
        with open(self.gpkg_file, "rb") as container:
            container_tar_format = self._get_tar_format(container)
            if container_tar_format is None:
                raise InvalidBinaryPackageFormat(
                    f"Cannot identify tar format: {self.gpkg_file}"
                )

        # Check container
        with tarfile.open(self.gpkg_file, "r") as container:
            try:
                container_files = container.getnames()
            except tarfile.ReadError:
                raise InvalidBinaryPackageFormat(
                    f"Cannot read tar file: {self.gpkg_file}"
                )

            # Check gpkg header
            if self.gpkg_version not in container_files:
                raise InvalidBinaryPackageFormat(f"Invalid gpkg file: {self.gpkg_file}")

            # If any signature exists, we assume all files have signature.
            if any(f.endswith(".sig") for f in container_files):
                signature_exist = True
            else:
                signature_exist = False

            # Check if all files are unique to avoid same name attack
            container_files_unique = []
            for f in container_files:
                if f in container_files_unique:
                    raise InvalidBinaryPackageFormat(
                        "Duplicate file %s exist, potential attack?" % f
                    )
                container_files_unique.append(f)

            del container_files_unique

            # Add all files to check list
            unverified_files = container_files.copy()
            unverified_files.remove(self.gpkg_version)

            # Check Manifest file
            if "Manifest" not in unverified_files:
                raise MissingSignature(f"Manifest not found: {self.gpkg_file}")

            manifest_file = container.extractfile("Manifest")
            manifest_data = manifest_file.read()
            manifest_file.close()

            if b"-----BEGIN PGP SIGNATURE-----" in manifest_data:
                signature_exist = True

            # Check Manifest signature if needed.
            # binpkg-ignore-signature can override this.
            if self.request_signature or signature_exist:
                checksum_info = checksum_helper(
                    self.settings, gpg_operation=checksum_helper.VERIFY, detached=False
                )

                try:
                    checksum_info.update(manifest_data)
                    checksum_info.finish()
                except (InvalidSignature, MissingSignature):
                    if self.verify_signature:
                        raise

                manifest_data = checksum_info.gpg_output
                unverified_files.remove("Manifest")
            else:
                unverified_files.remove("Manifest")

            # Load manifest and create manifest check list
            manifest = self._load_manifest(manifest_data.decode("UTF-8"))
            unverified_manifest = manifest.copy()

            # Check all remaining files
            for f in unverified_files.copy():
                if f.endswith(".sig"):
                    f_signature = None
                else:
                    f_signature = f + ".sig"

                # Find current file manifest record
                manifest_record = None
                for m in manifest:
                    if m[1] == f:
                        manifest_record = m

                if manifest_record is None:
                    raise DigestException(f"{f} checksum not found in {self.gpkg_file}")

                if int(manifest_record[2]) != int(container.getmember(f).size):
                    raise DigestException(
                        f"{f} file size mismatched in {self.gpkg_file}"
                    )

                # Ignore image file and signature if not needed
                if os.path.basename(f).startswith("image") and metadata_only:
                    unverified_files.remove(f)
                    unverified_manifest.remove(manifest_record)
                    continue

                # Verify current file signature if needed
                # binpkg-ignore-signature can override this.
                if (
                    (self.request_signature or signature_exist)
                    and self.verify_signature
                    and f_signature
                ):
                    if f_signature in unverified_files:
                        signature_file = container.extractfile(f_signature)
                        signature = signature_file.read()
                        signature_file.close()
                        checksum_info = checksum_helper(
                            self.settings,
                            gpg_operation=checksum_helper.VERIFY,
                            signature=signature,
                        )
                    else:
                        raise MissingSignature(
                            f"{f} signature not found in {self.gpkg_file}"
                        )
                else:
                    checksum_info = checksum_helper(self.settings)

                # Verify current file checksum
                f_io = container.extractfile(f)
                while True:
                    buffer = f_io.read(HASHING_BLOCKSIZE)
                    if buffer:
                        checksum_info.update(buffer)
                    else:
                        checksum_info.finish()
                        break
                f_io.close()

                # At least one supported checksum must be checked
                verified_hash_count = 0
                for c in checksum_info.libs:
                    try:
                        if (
                            checksum_info.libs[c].hexdigest().lower()
                            == manifest_record[manifest_record.index(c) + 1].lower()
                        ):
                            verified_hash_count += 1
                        else:
                            raise DigestException(
                                f"{f} checksum mismatched in {self.gpkg_file}"
                            )
                    except KeyError:
                        # Checksum method not supported
                        pass

                if verified_hash_count < 1:
                    raise DigestException(
                        f"{f} no supported checksum found in {self.gpkg_file}"
                    )

                # Current file verified
                unverified_files.remove(f)
                unverified_manifest.remove(manifest_record)

        # Check if any file IN Manifest but NOT IN binary package
        if len(unverified_manifest) != 0:
            raise DigestException(
                f"Missing files: {str(unverified_manifest)} in {self.gpkg_file}"
            )

        # Check if any file NOT IN Manifest but IN binary package
        if len(unverified_files) != 0:
            raise DigestException(
                f"Unknown files exists: {str(unverified_files)} in {self.gpkg_file}"
            )

        # Save current Manifest for other operations.
        self.manifest_old = manifest.copy()

    def _generate_metadata_from_dir(self, metadata_dir):
        """
        read all files in metadata_dir and return as dict
        """
        metadata = {}
        metadata_dir = normalize_path(
            _unicode_decode(metadata_dir, encoding=_encodings["fs"], errors="strict")
        )
        for parent, dirs, files in os.walk(metadata_dir):
            for f in files:
                try:
                    f = _unicode_decode(f, encoding=_encodings["fs"], errors="strict")
                except UnicodeDecodeError:
                    continue
                with open(os.path.join(parent, f), "rb") as metafile:
                    metadata[f] = metafile.read()
        return metadata

    def _get_binary_cmd(self, compression, mode):
        """
        get command list form portage and try match compressor
        """
        if compression not in _compressors:
            raise InvalidCompressionMethod(compression)

        compressor = _compressors[compression]
        if mode not in compressor:
            raise InvalidCompressionMethod("{}: {}".format(compression, mode))

        cmd = shlex_split(varexpand(compressor[mode], mydict=self.settings))
        # Filter empty elements that make Popen fail
        cmd = [x for x in cmd if x != ""]

        if (not cmd) and ((mode + "_alt") in compressor):
            cmd = shlex_split(
                varexpand(compressor[mode + "_alt"], mydict=self.settings)
            )
            cmd = [x for x in cmd if x != ""]

        if not cmd:
            raise CompressorNotFound(compression)
        if not find_binary(cmd[0]):
            raise CompressorNotFound(cmd[0])

        return cmd

    def _get_compression_cmd(self, compression=None):
        """
        return compression command for Popen
        """
        if compression is None:
            compression = self.compression
        if compression is None:
            return None
        else:
            return self._get_binary_cmd(compression, "compress")

    def _get_decompression_cmd(self, compression=None):
        """
        return decompression command for Popen
        """
        if compression is None:
            compression = self.compression
        if compression is None:
            return None
        else:
            return self._get_binary_cmd(compression, "decompress")

    def _get_tar_format(self, fileobj):
        """
        Try to detect tar version
        """
        old_position = fileobj.tell()
        fileobj.seek(0x101)
        magic = fileobj.read(8)
        fileobj.seek(0x9C)
        typeflag = fileobj.read(1)
        fileobj.seek(old_position)

        if magic == b"ustar  \x00":
            return tarfile.GNU_FORMAT
        elif magic == b"ustar\x0000":
            if typeflag == b"x" or typeflag == b"g":
                return tarfile.PAX_FORMAT
            else:
                return tarfile.USTAR_FORMAT

        return None

    def _get_tar_format_from_stats(
        self,
        image_max_prefix_length,
        image_max_name_length,
        image_max_linkname_length,
        image_max_file_size,
        image_total_size,
    ):
        """
        Choose the corresponding tar format according to
        the image information
        """
        # Max possible size in UStar is 8 GiB (8589934591 bytes)
        # stored in 11 octets
        # Use 8000000000, just in case we need add something extra

        # Total size > 8 GiB, container need use GNU tar format
        if image_total_size < 8000000000:
            container_tar_format = tarfile.USTAR_FORMAT
        else:
            container_tar_format = tarfile.GNU_FORMAT

        # Image at least one file > 8 GiB, image need use GNU tar format
        if image_max_file_size < 8000000000:
            image_tar_format = tarfile.USTAR_FORMAT
        else:
            image_tar_format = tarfile.GNU_FORMAT

        # UStar support max 155 prefix length, 100 file name and 100 link name,
        # ends with \x00. If any exceeded, failback to GNU format.
        if image_max_prefix_length >= 155:
            image_tar_format = tarfile.GNU_FORMAT

        if image_max_name_length >= 100:
            image_tar_format = tarfile.GNU_FORMAT

        if image_max_linkname_length >= 100:
            image_tar_format = tarfile.GNU_FORMAT
        return container_tar_format, image_tar_format

    def _check_pre_image_files(self, root_dir, image_prefix="image"):
        """
        Check the pre image files size and path, return the longest
        path length, largest single file size, and total files size.
        """
        image_prefix_length = len(image_prefix) + 1
        root_dir = os.path.join(
            normalize_path(
                _unicode_decode(root_dir, encoding=_encodings["fs"], errors="strict")
            ),
            "",
        )
        root_dir_length = len(
            _unicode_encode(root_dir, encoding=_encodings["fs"], errors="strict")
        )

        image_max_prefix_length = 0
        image_max_name_length = 0
        image_max_link_length = 0
        image_max_file_size = 0
        image_total_size = 0

        for parent, dirs, files in os.walk(root_dir):
            parent = _unicode_decode(parent, encoding=_encodings["fs"], errors="strict")
            for d in dirs:
                try:
                    d = _unicode_decode(d, encoding=_encodings["fs"], errors="strict")
                except UnicodeDecodeError as err:
                    writemsg(colorize("BAD", "\n*** %s\n\n" % err), noiselevel=-1)
                    raise

                d = os.path.join(parent, d)
                prefix_length = (
                    len(_unicode_encode(d, encoding=_encodings["fs"], errors="strict"))
                    - root_dir_length
                    + image_prefix_length
                )

                if os.path.islink(d):
                    path_link = os.readlink(d)
                    path_link_length = len(
                        _unicode_encode(
                            path_link, encoding=_encodings["fs"], errors="strict"
                        )
                    )
                    image_max_link_length = max(image_max_link_length, path_link_length)

                image_max_prefix_length = max(image_max_prefix_length, prefix_length)

            for f in files:
                try:
                    f = _unicode_decode(f, encoding=_encodings["fs"], errors="strict")
                except UnicodeDecodeError as err:
                    writemsg(colorize("BAD", "\n*** %s\n\n" % err), noiselevel=-1)
                    raise

                filename_length = len(
                    _unicode_encode(f, encoding=_encodings["fs"], errors="strict")
                )
                image_max_name_length = max(image_max_name_length, filename_length)

                f = os.path.join(parent, f)
                path_length = (
                    len(_unicode_encode(f, encoding=_encodings["fs"], errors="strict"))
                    - root_dir_length
                    + image_prefix_length
                )

                file_stat = os.lstat(f)

                if os.path.islink(f):
                    path_link = os.readlink(f)
                    path_link_length = len(
                        _unicode_encode(
                            path_link, encoding=_encodings["fs"], errors="strict"
                        )
                    )
                elif file_stat.st_nlink > 1:
                    # Hardlink exists
                    path_link_length = path_length
                else:
                    path_link_length = 0

                image_max_link_length = max(image_max_link_length, path_link_length)

                try:
                    file_size = os.path.getsize(f)
                except FileNotFoundError:
                    # Ignore file not found if symlink to non-existing file
                    if os.path.islink(f):
                        continue
                    else:
                        raise
                image_total_size += file_size
                image_max_file_size = max(image_max_file_size, file_size)

        return (
            image_max_prefix_length,
            image_max_name_length,
            image_max_link_length,
            image_max_file_size,
            image_total_size,
        )

    def _check_pre_quickpkg_files(self, contents, root, image_prefix="image"):
        """
        Check the pre quickpkg files size and path, return the longest
        path length, largest single file size, and total files size.
        """
        image_prefix_length = len(image_prefix) + 1
        root_dir = os.path.join(
            normalize_path(
                _unicode_decode(root, encoding=_encodings["fs"], errors="strict")
            ),
            "",
        )
        root_dir_length = len(
            _unicode_encode(root_dir, encoding=_encodings["fs"], errors="strict")
        )

        image_max_prefix_length = 0
        image_max_name_length = 0
        image_max_link_length = 0
        image_max_file_size = 0
        image_total_size = 0

        paths = list(contents)
        for path in paths:
            try:
                path = _unicode_decode(path, encoding=_encodings["fs"], errors="strict")
            except UnicodeDecodeError as err:
                writemsg(colorize("BAD", "\n*** %s\n\n" % err), noiselevel=-1)
                raise

            d, f = os.path.split(path)

            prefix_length = (
                len(_unicode_encode(d, encoding=_encodings["fs"], errors="strict"))
                - root_dir_length
                + image_prefix_length
            )
            image_max_prefix_length = max(image_max_prefix_length, prefix_length)

            filename_length = len(
                _unicode_encode(f, encoding=_encodings["fs"], errors="strict")
            )
            image_max_name_length = max(image_max_name_length, filename_length)

            path_length = (
                len(_unicode_encode(path, encoding=_encodings["fs"], errors="strict"))
                - root_dir_length
                + image_prefix_length
            )

            file_stat = os.lstat(path)

            if os.path.islink(path):
                path_link = os.readlink(path)
                path_link_length = len(
                    _unicode_encode(
                        path_link, encoding=_encodings["fs"], errors="strict"
                    )
                )
            elif file_stat.st_nlink > 1:
                # Hardlink exists
                path_link_length = path_length
            else:
                path_link_length = 0

            image_max_link_length = max(image_max_link_length, path_link_length)

            if os.path.isfile(path):
                try:
                    file_size = os.path.getsize(path)
                except FileNotFoundError:
                    # Ignore file not found if symlink to non-existing file
                    if os.path.islink(path):
                        continue
                    else:
                        raise
                image_total_size += file_size
                if file_size > image_max_file_size:
                    image_max_file_size = file_size

        return (
            image_max_prefix_length,
            image_max_name_length,
            image_max_link_length,
            image_max_file_size,
            image_total_size,
        )

    def _create_tarinfo(self, file_name):
        """
        Create new tarinfo for the new file
        """
        if self.compression is None:
            ext = ""
        elif self.compression in self.ext_list:
            ext = self.ext_list[self.compression]
        else:
            raise InvalidCompressionMethod(self.compression)

        data_tarinfo = tarfile.TarInfo(
            os.path.join(self.base_name, file_name + ".tar" + ext)
        )
        return data_tarinfo

    def _extract_filename_compression(self, file_name):
        """
        Extract the file basename and compression method
        """
        file_name = os.path.basename(file_name)
        if file_name.endswith(".tar"):
            return file_name[:-4], None

        for compression in self.ext_list:
            if file_name.endswith(".tar" + self.ext_list[compression]):
                return (
                    file_name[: -len(".tar" + self.ext_list[compression])],
                    compression,
                )

        raise InvalidCompressionMethod(file_name)

    def _get_inner_tarinfo(self, tar, file_name):
        """
        Get inner tarinfo from given container.
        Will try get file_name from correct basename first,
        if it fail, try any file that have same name as file_name, and
        return the first one.
        """
        if self.gpkg_version not in tar.getnames():
            raise InvalidBinaryPackageFormat("Invalid gpkg file.")

        # Try get file with correct basename
        inner_tarinfo = None
        if self.base_name is None:
            base_name = ""
        else:
            base_name = self.base_name
        all_files = tar.getmembers()
        for f in all_files:
            if os.path.dirname(f.name) == base_name:
                try:
                    f_name, f_comp = self._extract_filename_compression(f.name)
                except InvalidCompressionMethod:
                    continue

                if f_name == file_name:
                    return f, f_comp

        # If failed, try get any file name matched
        if inner_tarinfo is None:
            for f in all_files:
                try:
                    f_name, f_comp = self._extract_filename_compression(f.name)
                except InvalidCompressionMethod:
                    continue
                if f_name == file_name:
                    if self.base_name is not None:
                        writemsg(
                            colorize(
                                "WARN", "Package basename mismatched, using " + f.name
                            )
                        )
                    self.base_name_alt = os.path.dirname(f.name)
                    return f, f_comp

        # Not found
        raise FileNotFound(f"File Not found: {file_name}")
