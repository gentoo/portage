import fnmatch
import re
import types

from portage.eapi import (
    eapi_has_broot,
    eapi_has_sysroot,
    eapi_has_src_prepare_and_src_configure,
    eapi_exports_AA,
    eapi_exports_replace_vars,
    eapi_exports_ECLASSDIR,
    eapi_exports_PORTDIR,
    eapi_supports_prefix,
    eapi_exports_merge_type,
)
from repoman.modules.linechecks.base import LineCheck


class PhaseCheck(LineCheck):
    """basic class for function detection"""

    func_end_re = re.compile(r"^\}$")
    phase_funcs = (
        "pkg_pretend",
        "pkg_setup",
        "src_unpack",
        "src_prepare",
        "src_configure",
        "src_compile",
        "src_test",
        "src_install",
        "pkg_preinst",
        "pkg_postinst",
        "pkg_prerm",
        "pkg_postrm",
        "pkg_config",
    )
    phases_re = re.compile("(%s)" % "|".join(phase_funcs))
    in_phase = ""

    def check(self, num, line):
        m = self.phases_re.match(line)
        if m is not None:
            self.in_phase = m.group(1)
        if self.in_phase != "" and self.func_end_re.match(line) is not None:
            self.in_phase = ""

        return self.phase_check(num, line)

    def phase_check(self, num, line):
        """override this function for your checks"""
        pass


class EMakeParallelDisabled(PhaseCheck):
    """Check for emake -j1 calls which disable parallelization."""

    repoman_check_name = "upstream.workaround"
    re = re.compile(r"^\s*emake\s+.*-j\s*1\b")

    def phase_check(self, num, line):
        if self.in_phase == "src_compile" or self.in_phase == "src_install":
            if self.re.match(line):
                return self.errors["EMAKE_PARALLEL_DISABLED"]


class SrcCompileEconf(PhaseCheck):
    repoman_check_name = "ebuild.minorsyn"
    configure_re = re.compile(r"\s(econf|./configure)")

    def check_eapi(self, eapi):
        return eapi_has_src_prepare_and_src_configure(eapi)

    def phase_check(self, num, line):
        if self.in_phase == "src_compile":
            m = self.configure_re.match(line)
            if m is not None:
                return ("'%s'" % m.group(1)) + " call should be moved to src_configure"


class SrcUnpackPatches(PhaseCheck):
    repoman_check_name = "ebuild.minorsyn"
    src_prepare_tools_re = re.compile(r"\s(e?patch|sed)\s")

    def check_eapi(self, eapi):
        return eapi_has_src_prepare_and_src_configure(eapi)

    def phase_check(self, num, line):
        if self.in_phase == "src_unpack":
            m = self.src_prepare_tools_re.search(line)
            if m is not None:
                return ("'%s'" % m.group(1)) + " call should be moved to src_prepare"


# Refererences
# - https://projects.gentoo.org/pms/7/pms.html#x1-10900011.1
# - https://pkgcore.github.io/pkgcheck/_modules/pkgcheck/checks/codingstyle.html#VariableScopeCheck
_pms_vars = (
    ("A", None, ("src_*", "pkg_nofetch")),
    ("AA", eapi_exports_AA, ("src_*", "pkg_nofetch")),
    ("FILESDIR", None, ("src_*",)),
    ("DISTDIR", None, ("src_*",)),
    ("WORKDIR", None, ("src_*",)),
    ("S", None, ("src_*",)),
    ("PORTDIR", eapi_exports_PORTDIR, ("src_*",)),
    ("ECLASSDIR", eapi_exports_ECLASSDIR, ("src_*",)),
    ("ROOT", None, ("pkg_*",)),
    ("EROOT", eapi_supports_prefix, ("pkg_*",)),
    ("SYSROOT", eapi_has_sysroot, ("src_*", "pkg_setup")),
    ("ESYSROOT", eapi_has_sysroot, ("src_*", "pkg_setup")),
    ("BROOT", eapi_has_broot, ("src_*", "pkg_setup")),
    ("D", None, ("src_install", "pkg_preinst", "pkg_postint")),
    ("ED", eapi_supports_prefix, ("src_install", "pkg_preinst", "pkg_postint")),
    ("DESTTREE", None, ("src_install",)),
    ("INSDESTTREE", None, ("src_install",)),
    ("MERGE_TYPE", eapi_exports_merge_type, ("pkg_*",)),
    ("REPLACING_VERSIONS", eapi_exports_replace_vars, ("pkg_*",)),
    ("REPLACED_BY_VERSION", eapi_exports_replace_vars, ("pkg_prerm", "pkg_postrm")),
)


def _compile_phases():
    phase_vars = {}
    for phase_func in PhaseCheck.phase_funcs:
        for variable, eapi_filter, allowed_scopes in _pms_vars:
            allowed = False
            for scope in allowed_scopes:
                if fnmatch.fnmatch(phase_func, scope):
                    allowed = True
                    break

            if not allowed:
                phase_vars.setdefault(phase_func, []).append((variable, eapi_filter))

    phase_info = {}
    for phase_func, prohibited_vars in phase_vars.items():
        phase_func_vars = []
        for variable, eapi_filter in prohibited_vars:
            phase_func_vars.append(variable)
        phase_obj = phase_info[phase_func] = types.SimpleNamespace()
        phase_obj.prohibited_vars = dict(prohibited_vars)
        phase_obj.var_names = "(%s)" % "|".join(
            variable for variable, eapi_filter in prohibited_vars
        )
        phase_obj.var_reference = re.compile(
            r"\$(\{|)%s(\}|\W)" % (phase_obj.var_names,)
        )

    return phase_info


class PMSVariableReference(PhaseCheck):
    """Check phase scope for references to variables specified by PMS"""

    repoman_check_name = "variable.phase"
    phase_info = _compile_phases()

    def new(self, pkg):
        self._eapi = pkg.eapi

    def end(self):
        self._eapi = None

    def phase_check(self, num, line):
        try:
            phase_info = self.phase_info[self.in_phase]
        except KeyError:
            return

        eapi = self._eapi
        issues = []
        for m in phase_info.var_reference.finditer(line):
            open_brace = m.group(1)
            var_name = m.group(2)
            close_brace = m.group(3)
            # discard \W if matched by (\}|\W)
            close_brace = close_brace if close_brace == "}" else ""
            if bool(open_brace) != bool(close_brace):
                continue
            var_name = m.group(2)
            eapi_filter = phase_info.prohibited_vars[var_name]
            if eapi_filter is not None and not eapi_filter(eapi):
                continue
            issues.append(
                "phase %s: EAPI %s: variable %s: Forbidden reference to variable specified by PMS"
                % (self.in_phase, eapi, var_name)
            )
        return issues
