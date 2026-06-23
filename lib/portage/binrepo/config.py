# Copyright 2020-2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from collections import OrderedDict
from collections.abc import Mapping
from hashlib import md5

from portage._sets.base import WildcardPackageSet
from portage.localization import _
from portage.repository.config import _find_bad_atoms
from portage.util import _recursive_file_list, writemsg
from portage.util.configparser import SafeConfigParser, ConfigParserError, read_configs


class BinRepoConfig:
    __slots__ = (
        "frozen",
        "openpgp_key_package",
        "name",
        "name_fallback",
        "fetchcommand",
        "getbinpkg_exclude",
        "getbinpkg_include",
        "location",
        "priority",
        "resumecommand",
        "sync_uri",
        "verify_signature",
    )
    _bool_opts = ("frozen", "verify_signature")

    def __init__(self, opts):
        """
        Create a BinRepoConfig with options in opts.
        """
        for k in self.__slots__:
            setattr(self, k, opts.get(k.replace("_", "-")))
        for k in self._bool_opts:
            if isinstance(getattr(self, k, None), str):
                setattr(self, k, getattr(self, k).lower() in ("true", "yes"))

        # getbinpkg-exclude and getbinpkg-include validation
        for opt in ("getbinpkg-exclude", "getbinpkg-include"):
            attr = opt.replace("-", "_")
            if self.name == "DEFAULT":
                setattr(self, attr, None)
                continue
            getbinpkg_atoms = opts.get(opt, "").split()
            bad_atoms = _find_bad_atoms(getbinpkg_atoms)
            if bad_atoms:
                writemsg(
                    "\n!!! The following atoms are invalid in %s attribute for "
                    "binrepo [%s] (only package names and slot atoms allowed):\n"
                    "\n    %s\n" % (opt, self.name, "\n    ".join(bad_atoms))
                )
                for a in bad_atoms:
                    getbinpkg_atoms.remove(a)
            getbinpkg_set = WildcardPackageSet(getbinpkg_atoms, allow_repo=True)
            setattr(self, attr, getbinpkg_set)
        conflicted_atoms = (
            self.getbinpkg_exclude
            and self.getbinpkg_exclude.getAtoms().intersection(
                self.getbinpkg_include.getAtoms()
            )
        )
        if conflicted_atoms:
            writemsg(
                "\n!!! The following atoms appear in both the getbinpkg-exclude "
                "getbinpkg-include lists for binrepo [%s]:\n"
                "\n    %s\n" % (self.name, "\n    ".join(conflicted_atoms))
            )
            for a in conflicted_atoms:
                self.getbinpkg_exclude.remove(a)
                self.getbinpkg_include.remove(a)

    def info_string(self):
        """
        Returns a formatted string containing information about the repository.
        Used by emerge --info.
        """
        indent = " " * 4
        repo_msg = []
        repo_msg.append(self.name or self.name_fallback)
        if self.location:
            repo_msg.append(indent + "location: " + self.location)
        if self.priority is not None:
            repo_msg.append(indent + "priority: " + str(self.priority))
        repo_msg.append(indent + "sync-uri: " + self.sync_uri)
        repo_msg.append(indent + f"verify-signature: {self.verify_signature}")
        if self.frozen:
            repo_msg.append(f"{indent}frozen: {str(self.frozen).lower()}")
        repo_msg.append("")
        return "\n".join(repo_msg)


class BinRepoConfigLoader(Mapping):
    def __init__(self, paths, settings):
        """Load config from files in paths"""

        # Defaults for value interpolation.
        parser_defaults = {
            "frozen": "false",
            "EPREFIX": settings["EPREFIX"],
            "EROOT": settings["EROOT"],
            "PORTAGE_CONFIGROOT": settings["PORTAGE_CONFIGROOT"],
            "ROOT": settings["ROOT"],
        }

        try:
            parser = self._parse(paths, parser_defaults)
        except ConfigParserError as e:
            writemsg(
                _("!!! Error while reading binrepo config file: %s\n") % e,
                noiselevel=-1,
            )
            parser = SafeConfigParser(defaults=parser_defaults)

        repos = []
        sync_uris = []
        for section_name in parser.sections():
            repo_data = dict(parser[section_name].items())
            repo_data["name"] = section_name
            repo = BinRepoConfig(repo_data)
            if repo.sync_uri is None:
                writemsg(
                    _("!!! Missing sync-uri setting for binrepo %s\n") % (repo.name,),
                    noiselevel=-1,
                )
                continue

            sync_uri = self._normalize_uri(repo.sync_uri)
            sync_uris.append(sync_uri)
            repo.sync_uri = sync_uri
            if repo.priority is not None:
                try:
                    repo.priority = int(repo.priority)
                except ValueError:
                    repo.priority = None
            repos.append(repo)

        sync_uris = set(sync_uris)
        current_priority = 0
        # Convert PORTAGE_BINHOST entries into implicit binrepos.conf ones
        for sync_uri in reversed(settings.get("PORTAGE_BINHOST", "").split()):
            sync_uri = self._normalize_uri(sync_uri)
            if sync_uri not in sync_uris:
                current_priority += 1
                sync_uris.add(sync_uri)
                repos.append(
                    BinRepoConfig(
                        {
                            "name-fallback": self._digest_uri(sync_uri),
                            "name": None,
                            "priority": current_priority,
                            "sync-uri": sync_uri,
                        }
                    )
                )

        # With PORTAGE_BINHOST, it's not clear what the implicit name would
        # be, so treat it like local.
        if not settings.get("PORTAGE_BINHOST", ""):
            for repo in repos:
                if repo.location is None:
                    repo.location = (
                        f"{settings['EPREFIX']}/var/cache/binhost/{repo.name}"
                    )

        self._data = OrderedDict(
            (repo.name or repo.name_fallback, repo)
            for repo in sorted(
                repos,
                key=lambda repo: (repo.priority or 0, repo.name or repo.name_fallback),
            )
        )

    @staticmethod
    def _digest_uri(uri):
        return md5(uri.encode("utf_8")).hexdigest()

    @staticmethod
    def _normalize_uri(uri):
        return uri.rstrip("/")

    @staticmethod
    def _parse(paths, defaults):
        parser = SafeConfigParser(defaults=defaults)
        recursive_paths = []
        for p in paths:
            if isinstance(p, str):
                recursive_paths.extend(_recursive_file_list(p))
            else:
                recursive_paths.append(p)

        read_configs(parser, recursive_paths)
        return parser

    def __iter__(self):
        return iter(self._data)

    def __contains__(self, key):
        return key in self._data

    def __getitem__(self, key):
        return self._data[key]

    def __len__(self):
        return len(self._data)
