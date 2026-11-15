# Copyright 1999-2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import collections
from itertools import chain

from portage.output import blue, red
from portage.util import cmp_sort_key

from _emerge.resolver.output_helpers import _alnum_sort_key


class UseFlagDisplay:
    __slots__ = ("enabled", "forced", "name")

    def __init__(self, name, enabled, forced):
        self.name = name
        self.enabled = enabled
        self.forced = forced

    def __str__(self):
        s = self.name
        if self.enabled:
            s = red(s)
        else:
            s = "-" + s
            s = blue(s)
        if self.forced:
            s = f"({s})"
        return s

    def _cmp_combined(a, b):
        """
        Sort by name, combining enabled and disabled flags.
        """
        return (a.name > b.name) - (a.name < b.name)

    sort_combined = cmp_sort_key(_cmp_combined)
    del _cmp_combined

    def _cmp_separated(a, b):
        """
        Sort by name, separating enabled flags from disabled flags.
        """
        enabled_diff = b.enabled - a.enabled
        if enabled_diff:
            return enabled_diff
        return (a.name > b.name) - (a.name < b.name)

    sort_separated = cmp_sort_key(_cmp_separated)
    del _cmp_separated


def masked_use_reasons(pkg, use):
    """Return the MASKED_USE reasons for the disabled flags of pkg

    @param pkg: _emerge.Package.Package instance
    @param use: the enabled flags of pkg
    @rtype: dict
    @return: maps each flag to the conditionals that mask it, see
            portage.dep.get_masked_use_reasons()
    """
    if not pkg._metadata.get("MASKED_USE"):
        return {}
    reasons = pkg._get_pkgsettings().masked_use_reasons
    use = frozenset(use)
    iuse = pkg.iuse.all
    return {
        flag: reason
        for flag, reason in reasons.items()
        if flag in iuse and flag not in use
    }


def masked_use_display(pkg, reasons):
    """Create the MASKED_USE="..." string for pkg

    Flags are grouped by the conditionals that mask them, as in
    MASKED_USE="-gui => gtk qt6, -perforce => PYTHON_SINGLE_TARGET".
    A USE_EXPAND variable is named instead of its flags when all of
    its flags are masked by the same conditionals.

    @param pkg: _emerge.Package.Package instance
    @param reasons: dict from masked_use_reasons()
    @rtype: str
    @return: the string, or "" if there is nothing to show
    """
    use_expand = pkg.use.expand
    use_expand_hidden = pkg.use.expand_hidden

    def expand_var(flag):
        for varname in use_expand:
            if flag.startswith(varname + "_"):
                return varname
        return None

    iuse_by_var = {}
    for flag in pkg.iuse.all:
        iuse_by_var.setdefault(expand_var(flag), set()).add(flag)

    # Preserve the order in which the conditionals appear in MASKED_USE.
    by_reason = {}
    for flag, reason in reasons.items():
        by_reason.setdefault(reason, []).append(flag)

    groups = []
    for reason, flags in by_reason.items():
        items = []
        by_var = {}
        for flag in flags:
            varname = expand_var(flag)
            if varname is None:
                items.append(flag)
            elif varname not in use_expand_hidden:
                by_var.setdefault(varname, set()).add(flag)
        items.sort(key=_alnum_sort_key)
        for varname in sorted(by_var):
            if by_var[varname] == iuse_by_var[varname]:
                items.append(varname.upper())
            else:
                items.extend(sorted(by_var[varname], key=_alnum_sort_key))
        if not items:
            # All of the flags are in USE_EXPAND_HIDDEN.
            continue
        items = " ".join(blue(item) for item in items)
        if reason:
            cause = ",".join(
                blue(cond) if cond.startswith("-") else red(cond) for cond in reason
            )
            items = f"{cause} => {items}"
        groups.append(items)

    if not groups:
        return ""
    return 'MASKED_USE="{}"'.format(", ".join(groups))


_flag_info = collections.namedtuple("_flag_info", ("flag", "display"))


def pkg_use_display(pkg, opts, modified_use=None):
    settings = pkg.root_config.settings
    use_expand = pkg.use.expand
    use_expand_hidden = pkg.use.expand_hidden
    alphabetical_use = "--alphabetical" in opts
    forced_flags = set(chain(pkg.use.force, pkg.use.mask))
    if modified_use is None:
        use = set(pkg.use.enabled)
    else:
        use = set(modified_use)
    # Flags masked by MASKED_USE are shown separately.
    reasons = masked_use_reasons(pkg, use)
    use.discard(settings.get("ARCH"))
    use_expand_flags = set()
    use_enabled = {}
    use_disabled = {}
    for varname in use_expand:
        flag_prefix = varname.lower() + "_"
        for f in use:
            if f.startswith(flag_prefix):
                use_expand_flags.add(f)
                use_enabled.setdefault(varname.upper(), []).append(
                    _flag_info(f, f[len(flag_prefix) :])
                )

        for f in pkg.iuse.all:
            if f.startswith(flag_prefix):
                use_expand_flags.add(f)
                if f not in use and f not in reasons:
                    use_disabled.setdefault(varname.upper(), []).append(
                        _flag_info(f, f[len(flag_prefix) :])
                    )

    var_order = set(use_enabled)
    var_order.update(use_disabled)
    var_order = sorted(var_order)
    var_order.insert(0, "USE")
    use.difference_update(use_expand_flags)
    use_enabled["USE"] = list(_flag_info(f, f) for f in use)
    use_disabled["USE"] = []

    for f in pkg.iuse.all:
        if f not in use and f not in use_expand_flags and f not in reasons:
            use_disabled["USE"].append(_flag_info(f, f))

    flag_displays = []
    for varname in var_order:
        if varname.lower() in use_expand_hidden:
            continue
        flags = []
        for f in use_enabled.get(varname, []):
            flags.append(UseFlagDisplay(f.display, True, f.flag in forced_flags))
        for f in use_disabled.get(varname, []):
            flags.append(UseFlagDisplay(f.display, False, f.flag in forced_flags))
        if alphabetical_use:
            flags.sort(key=UseFlagDisplay.sort_combined)
        else:
            flags.sort(key=UseFlagDisplay.sort_separated)
        flag_displays.append(f"{varname}=\"{' '.join(f'{f}' for f in flags)}\"")

    if reasons:
        masked = masked_use_display(pkg, reasons)
        if masked:
            flag_displays.append(masked)

    return " ".join(flag_displays)
