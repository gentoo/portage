# Copyright 2010-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import collections
from functools import lru_cache
from typing import Optional

from portage import eapi_is_supported


def eapi_has_iuse_defaults(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).iuse_defaults


def eapi_has_iuse_effective(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).iuse_effective


def eapi_has_slot_deps(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).slot_deps


def eapi_has_slot_operator(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).slot_operator


def eapi_has_src_uri_arrows(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).src_uri_arrows


def eapi_has_selective_src_uri_restriction(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).selective_src_uri_restriction


def eapi_has_use_deps(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).use_deps


def eapi_has_strong_blocks(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).strong_blocks


def eapi_has_src_prepare_and_src_configure(eapi: str) -> bool:
    return eapi not in ("0", "1")


def eapi_supports_prefix(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).prefix


def eapi_exports_AA(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).exports_AA


def eapi_exports_KV(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).exports_KV


def eapi_exports_merge_type(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).exports_merge_type


def eapi_exports_replace_vars(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).exports_replace_vars


def eapi_exports_EBUILD_PHASE_FUNC(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).exports_EBUILD_PHASE_FUNC


def eapi_exports_PORTDIR(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).exports_PORTDIR


def eapi_exports_ECLASSDIR(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).exports_ECLASSDIR


def eapi_has_pkg_pretend(eapi: str) -> bool:
    return eapi not in ("0", "1", "2", "3")


def eapi_has_implicit_rdepend(eapi: str) -> bool:
    return eapi in ("0", "1", "2", "3")


def eapi_has_dosed_dohard(eapi: str) -> bool:
    return eapi in ("0", "1", "2", "3")


def eapi_has_required_use(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).required_use


def eapi_has_required_use_at_most_one_of(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).required_use_at_most_one_of


def eapi_has_use_dep_defaults(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).use_dep_defaults


def eapi_requires_posixish_locale(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).posixish_locale


def eapi_has_repo_deps(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).repo_deps


def eapi_supports_stable_use_forcing_and_masking(eapi: str) -> bool:
    return eapi not in ("0", "1", "2", "3", "4", "4-slot-abi")


def eapi_allows_directories_on_profile_level_and_repository_level(eapi: str) -> bool:
    return eapi not in ("0", "1", "2", "3", "4", "4-slot-abi", "5", "6")


def eapi_allows_package_provided(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).allows_package_provided


def eapi_has_bdepend(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).bdepend


def eapi_has_idepend(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).idepend


def eapi_empty_groups_always_true(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).empty_groups_always_true


def eapi_path_variables_end_with_trailing_slash(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).path_variables_end_with_trailing_slash


def eapi_has_broot(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).broot


def eapi_has_sysroot(eapi: str) -> bool:
    return _get_eapi_attrs(eapi).sysroot


_eapi_attrs = collections.namedtuple(
    "_eapi_attrs",
    (
        "allows_package_provided",
        "bdepend",
        "broot",
        "exports_AA",
        "exports_EBUILD_PHASE_FUNC",
        "exports_ECLASSDIR",
        "exports_KV",
        "exports_merge_type",
        "exports_PORTDIR",
        "exports_replace_vars",
        "feature_flag_test",
        "idepend",
        "iuse_defaults",
        "iuse_effective",
        "posixish_locale",
        "path_variables_end_with_trailing_slash",
        "prefix",
        "repo_deps",
        "required_use",
        "required_use_at_most_one_of",
        "selective_src_uri_restriction",
        "slot_operator",
        "slot_deps",
        "src_uri_arrows",
        "strong_blocks",
        "use_deps",
        "use_dep_defaults",
        "empty_groups_always_true",
        "sysroot",
    ),
)


class Eapi:
    ALL_EAPIS = (
        "0",
        "1",
        "2",
        "3",
        "4",
        "4-slot-abi",
        "5",
        "6",
        "7",
        "8",
    )

    _eapi_val: int = -1

    def __init__(self, eapi_string: str):
        if not eapi_string in self.ALL_EAPIS:
            raise ValueError(f"'{eapi_string}' not recognized as a valid EAPI")

        self._eapi_val = int(eapi_string.partition("-")[0])

    def __ge__(self, other: "Eapi") -> bool:
        return self._eapi_val >= other._eapi_val

    def __le__(self, other: "Eapi") -> bool:
        return self._eapi_val <= other._eapi_val


@lru_cache(32)
def _get_eapi_attrs(eapi_str: Optional[str]) -> _eapi_attrs:
    """
    When eapi is None then validation is not as strict, since we want the
    same to work for multiple EAPIs that may have slightly different rules.
    An unsupported eapi is handled the same as when eapi is None, which may
    be helpful for handling of corrupt EAPI metadata in essential functions
    such as pkgsplit.
    """
    if eapi_str is None or not eapi_is_supported(eapi_str):
        return _eapi_attrs(
            allows_package_provided=True,
            bdepend=False,
            broot=True,
            empty_groups_always_true=False,
            exports_AA=False,
            exports_EBUILD_PHASE_FUNC=True,
            exports_ECLASSDIR=False,
            exports_KV=False,
            exports_merge_type=True,
            exports_PORTDIR=True,
            exports_replace_vars=True,
            feature_flag_test=False,
            idepend=False,
            iuse_defaults=True,
            iuse_effective=False,
            path_variables_end_with_trailing_slash=False,
            posixish_locale=False,
            prefix=True,
            repo_deps=True,
            required_use=True,
            required_use_at_most_one_of=True,
            selective_src_uri_restriction=True,
            slot_deps=True,
            slot_operator=True,
            src_uri_arrows=True,
            strong_blocks=True,
            sysroot=True,
            use_deps=True,
            use_dep_defaults=True,
        )
    else:
        eapi = Eapi(eapi_str)
        return _eapi_attrs(
            allows_package_provided=eapi <= Eapi("6"),
            bdepend=eapi >= Eapi("7"),
            broot=eapi >= Eapi("7"),
            empty_groups_always_true=eapi <= Eapi("6"),
            exports_AA=eapi <= Eapi("3"),
            exports_EBUILD_PHASE_FUNC=eapi >= Eapi("5"),
            exports_ECLASSDIR=eapi <= Eapi("6"),
            exports_KV=eapi <= Eapi("3"),
            exports_merge_type=eapi >= Eapi("4"),
            exports_PORTDIR=eapi <= Eapi("6"),
            exports_replace_vars=eapi >= Eapi("4"),
            feature_flag_test=False,
            idepend=eapi >= Eapi("8"),
            iuse_defaults=eapi >= Eapi("1"),
            iuse_effective=eapi >= Eapi("5"),
            path_variables_end_with_trailing_slash=eapi <= Eapi("6"),
            posixish_locale=eapi >= Eapi("6"),
            prefix=eapi >= Eapi("3"),
            repo_deps=False,
            required_use=eapi >= Eapi("4"),
            required_use_at_most_one_of=eapi >= Eapi("5"),
            selective_src_uri_restriction=eapi >= Eapi("8"),
            slot_deps=eapi >= Eapi("1"),
            slot_operator=eapi >= Eapi("5"),
            src_uri_arrows=eapi >= Eapi("2"),
            strong_blocks=eapi >= Eapi("2"),
            sysroot=eapi >= Eapi("7"),
            use_deps=eapi >= Eapi("2"),
            use_dep_defaults=eapi >= Eapi("4"),
        )
