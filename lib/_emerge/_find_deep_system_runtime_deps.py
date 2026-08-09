# Copyright 1999-2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from _emerge.DepPriority import DepPriority
from _emerge.Package import Package

# The "toolchain" merge-wait scope. These are the packages which the ebuild
# environment itself invokes for essentially every build, so a partially
# installed state is liable to break an unrelated build that is running
# concurrently, no matter what that build declares as its dependencies. Note
# that this is a fixed list rather than something derived from the graph,
# since the property it describes is not expressed in package metadata.
CORE_TOOLCHAIN = frozenset(
    [
        "app-shells/bash",
        "dev-lang/perl",
        "dev-lang/python",
        "dev-libs/libffi",
        "sys-apps/baselayout",
        "sys-apps/coreutils",
        "sys-apps/sandbox",
        "sys-devel/binutils",
        "sys-devel/gcc",
        "sys-devel/gettext",
        "sys-libs/glibc",
        "sys-libs/musl",
    ]
)


def _find_deep_system_runtime_deps(graph, scope="deep"):
    """
    Find the packages which must be merged while no build jobs are running.

    @param graph: the dependency graph
    @param scope: "deep" for the @system set plus its transitive runtime
            dependencies, "system" for the @system set alone, "toolchain" for
            the core toolchain alone, or "none" for nothing.
    @rtype: set
    """
    if scope not in ("deep", "system", "toolchain", "none"):
        raise ValueError(f"invalid merge-wait scope: {scope}")

    if scope == "none":
        return set()

    node_stack = []
    for node in graph:
        if not isinstance(node, Package) or node.operation == "uninstall":
            continue
        if scope == "toolchain":
            selected = node.cp in CORE_TOOLCHAIN
        else:
            selected = node.root_config.sets["system"].findAtomForPackage(node)
        if selected:
            node_stack.append(node)

    if scope in ("system", "toolchain"):
        return set(node_stack)

    deep_system_deps = set()

    def ignore_priority(priority):
        """
        Ignore non-runtime priorities.
        """
        if isinstance(priority, DepPriority) and (
            priority.runtime or priority.runtime_post
        ):
            return False
        return True

    while node_stack:
        node = node_stack.pop()
        if node in deep_system_deps:
            continue
        deep_system_deps.add(node)
        for child in graph.child_nodes(node, ignore_priority=ignore_priority):
            if not isinstance(child, Package) or child.operation == "uninstall":
                continue
            node_stack.append(child)

    return deep_system_deps
