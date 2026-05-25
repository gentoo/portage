# Copyright 2010-2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import hashlib
import os


class MockUserPatches:
    # for the purposes of testing, it doesn't really matter much what the actual
    # user patch files contain. we therefore use the NIST SHA-256 test vectors
    # and include the hashes here for reference when debugging tests.
    #
    # NullPatch -> e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
    #
    # Patch1 -> 28969cdfa74a12c82f3bad960b0b000aca2ac329deea5c2328ebc6f2ba9802c1
    # Patch2 -> 5ca7133fa735326081558ac312c620eeca9970d1e70a4b95533d956f072d1f98
    # Patch3 -> dff2e73091f6c05e528896c4c831b9448653dc2ff043528f6769437bc7b975c2
    # Patch4 -> b16aa56be3880d18cd41e68384cf1ec8c17680c45a02b1575dc1518923ae8b0e
    # Patch5 -> f0887fe961c9cd3beab957e8222494abb969b1ce4c6557976df8b0f6d20e9166
    # Patch6 -> eca0a060b489636225b4fa64d267dabbe44273067ac679f20820bddc6b6a90ac

    # empty patch file used to cancel another patch
    NullPatch = b""

    # for use as the user patch file content for ResolverPlayground
    Patch1 = b"\xd3"
    Patch2 = b"\x11\xaf"
    Patch3 = b"\xb4\x19\x0e"
    Patch4 = b"\x74\xba\x25\x21"
    Patch5 = b"\xc2\x99\x20\x96\x82"
    Patch6 = b"\xe1\xdc\x72\x4d\x56\x21"

    """
    Calculate the expected hash over the specified user patch files which may
    be a subset of the possible patches configured.

    @param user_patches: dict of dicts defining patch folders, files, and text
                         as might be passed to ResolvePlayground
    @param files: list of relative paths defining the patches to be hashed
    """

    def expected_hash(user_patches, files):
        patches = {
            os.path.basename(p): user_patches[os.path.dirname(p)][os.path.basename(p)]
            for p in files
        }

        expected = hashlib.sha256()
        for f in sorted(patches):
            content = patches[f]
            if len(content) == 0:
                continue
            if isinstance(content, str):
                content = content.encode()
            expected.update(hashlib.sha256(content).hexdigest().encode())

        return expected.hexdigest()
