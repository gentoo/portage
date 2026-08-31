# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""
Support for running the dependency calculation in a child process.

The calculation allocates far more memory than the merge that follows it,
and CPython cannot return that memory to the operating system once the
depgraph is freed, because the objects which do survive the calculation are
spread across many partially used arenas. Merging in a process which never
performed the calculation avoids the problem entirely: the child exits and
the kernel reclaims everything it allocated.

The child sends the scheduler graph back as plain data, and the parent
rebuilds the Package instances and the digraph from it. See bug 549906.
"""

import os
import pickle
import signal
import socket
import sys
import traceback

import portage
from portage.dep import Atom
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.digraph import digraph
from portage.versions import _pkg_str

from _emerge.Blocker import Blocker
from _emerge.BlockerDepPriority import BlockerDepPriority
from _emerge.depgraph import _scheduler_graph_config
from _emerge.DepPriority import DepPriority
from _emerge.FakeVartree import FakeVartree, fake_vartree_options
from _emerge.Package import Package, _PackageMetadataWrapper
from _emerge.UnmergeDepPriority import UnmergeDepPriority

_RECV_CHUNK_SIZE = 1 << 20
_LENGTH_BYTES = 8

# Sent by the child once it owns stdio, so that the parent knows whether a
# later failure may be retried in process. See run_in_child().
_CHILD_READY = b"\x01"

# The dbapi that a Package of each type_name must be constructed against.
_TYPE_NAME_TREE = {
    "ebuild": "porttree",
    "binary": "bintree",
    "installed": "vartree",
}

# Metadata keys whose value in Package._metadata is derived from the settings
# of the process that holds the instance, rather than from the vdb or from the
# ebuild. Package derives them again for itself, from _raw_metadata.
_DERIVED_METADATA_KEYS = frozenset(
    {"CHOST", "USE"} | _PackageMetadataWrapper._use_conditional_keys
)


class ForkFailed(Exception):
    """
    The child never reached the calculation, so it has shown no resolution
    output and asked nothing, and the caller may calculate in the current
    process. It may have printed a traceback for the failure itself.
    """


class ChildFailed(Exception):
    """
    The child failed after it took over stdio, so it may already have
    displayed the merge list or asked the user to confirm it. The caller
    must not calculate again, because that would repeat all of it.

    The exit_code attribute is what emerge should exit with, which carries
    a signal that killed the child, so that an interrupted --ask prompt
    reports as an interrupt rather than as a failure.
    """

    def __init__(self, message, exit_code=1):
        super().__init__(message)
        self.exit_code = exit_code


class _TransferError(Exception):
    """
    A result could not be read from the child. run_in_child() turns this
    into ForkFailed or ChildFailed, depending on how far the child got.
    """


def enabled(myopts):
    """
    Check whether the dependency calculation should run in a child process.

    This is on by default, and PORTAGE_FORK_DEP_CALC=0 in the environment
    turns it off.
    """
    if os.environ.get("PORTAGE_FORK_DEP_CALC") == "0":
        return False
    # --pretend has no merge phase to save the memory for, and --resume
    # keeps its depgraph in scope for the merge (see action_build).
    for opt in ("--pretend", "--resume"):
        if opt in myopts:
            return False
    return True


class _ArgPlaceholder:
    """
    Stands in for a DependencyArg node of the scheduler graph.

    Scheduler._prune_digraph() discards every root node which is not a
    Package, so these nodes only need to preserve the shape of the graph.
    For the same reason the key does not have to be unique: two args with
    the same repr collapse into one node, which changes nothing once the
    node is discarded.
    """

    __slots__ = ("_key",)

    def __init__(self, key):
        self._key = key

    def __repr__(self):
        return f"_ArgPlaceholder({self._key!r})"

    def __eq__(self, other):
        return isinstance(other, _ArgPlaceholder) and other._key == self._key

    def __hash__(self):
        return hash(self._key)


def _encode_priority(priority):
    """
    Encode a DepPriority, UnmergeDepPriority or BlockerDepPriority as its
    class name plus the values of the slots which are set.
    """
    values = {}
    for cls in type(priority).__mro__:
        for slot in getattr(cls, "__slots__", ()):
            if slot.startswith("__") or slot in values:
                continue
            try:
                value = getattr(priority, slot)
            except AttributeError:
                continue
            if slot == "satisfied" and value:
                # This can reference an installed Package, which is not
                # picklable. schedulerGraph() already flattens it to True,
                # but only for the priorities it reaches through the graph
                # edges, and a Blocker carries one of its own.
                value = True
            values[slot] = value
    return (type(priority).__name__, values)


def _decode_priority(encoded):
    name, values = encoded
    for cls in (DepPriority, UnmergeDepPriority, BlockerDepPriority):
        if cls.__name__ == name:
            return cls(**values)
    raise _TransferError(f"unknown dependency priority class: {name}")


def _encode_metadata(pkg):
    """
    Encode the metadata of a Package.

    Send the raw metadata, so that _set_use() can still restore the USE
    conditional values to their unevaluated state, together with the entries
    which FakeVartree rewrote in _metadata since, so that the merge sees the
    dependencies the calculation used rather than the ones the vdb holds.
    """
    metadata = dict(pkg._raw_metadata)
    for key, value in pkg._metadata.items():
        if key not in _DERIVED_METADATA_KEYS and metadata.get(key) != value:
            metadata[key] = value
    return metadata


def _encode_node(node):
    if isinstance(node, Blocker):
        # Blocker.satisfied is deliberately not carried over. The Scheduler
        # recomputes it from its own BlockerDB, against the vdb as it is at
        # merge time rather than as the calculation saw it.
        return (
            "blocker",
            node.root,
            str(node.atom),
            node.eapi,
            _encode_priority(node.priority),
        )

    if not isinstance(node, Package):
        # A DependencyArg node.
        return ("arg", f"{type(node).__name__}:{node}")

    cpv = node.cpv
    return (
        "package",
        node.root,
        str(cpv),
        node.type_name,
        node.built,
        node.installed,
        node.operation,
        node.onlydeps,
        _encode_metadata(node),
        # Fields which _pkg_str carries for binary packages, and which
        # Package._gen_hash_key() uses to tell similar packages apart.
        {
            key: getattr(cpv, key, None)
            for key in ("build_id", "build_time", "file_size", "mtime")
        },
    )


def _decode_node(entry, trees):
    kind = entry[0]

    if kind == "arg":
        return _ArgPlaceholder(entry[1])

    if kind == "blocker":
        _, root, atom, eapi, priority = entry
        return Blocker(
            atom=Atom(atom), root=root, eapi=eapi, priority=_decode_priority(priority)
        )

    (
        _,
        root,
        cpv,
        type_name,
        built,
        installed,
        operation,
        onlydeps,
        metadata,
        cpv_attrs,
    ) = entry

    try:
        root_config = trees[root]["root_config"]
        db = trees[root][_TYPE_NAME_TREE[type_name]].dbapi
    except KeyError as e:
        raise _TransferError(f"unknown root or package type from the child: {e}") from e
    return Package(
        built=built,
        cpv=_pkg_str(
            cpv,
            metadata=metadata,
            settings=root_config.settings,
            db=db,
            **{k: v for k, v in cpv_attrs.items() if v is not None},
        ),
        installed=installed,
        metadata=metadata,
        onlydeps=onlydeps,
        operation=operation,
        root_config=root_config,
        type_name=type_name,
    )


def encode_scheduler_graph(graph_config):
    """
    Encode a _scheduler_graph_config instance as plain data.
    """
    graph = graph_config.graph
    nodes = list(graph.nodes) if graph is not None else []
    index = {node: i for i, node in enumerate(nodes)}

    edges = []
    if graph is not None:
        for node in nodes:
            children = graph.nodes[node][0]
            for child, priorities in children.items():
                for priority in priorities:
                    edges.append(
                        (index[node], index[child], _encode_priority(priority))
                    )

    # Blockers which altlist() solved are in the mergelist, for display,
    # without being nodes of the scheduler graph. Send them after the graph
    # nodes, so that the mergelist can refer to them by index too.
    graph_nodes = len(nodes)
    for node in graph_config.mergelist:
        if node not in index:
            index[node] = len(nodes)
            nodes.append(node)

    # Packages which are in the pkg_cache but not in the graph, which is
    # mostly the installed packages that the scheduler's fake vartrees are
    # populated from.
    cached = [
        _encode_node(pkg) for pkg in graph_config.pkg_cache.values() if pkg not in index
    ]

    # The cpvs whose dynamic dependencies the calculation already resolved.
    # Without this the fake vartree would try to resolve them again during
    # the merge, from inside a running event loop.
    aux_get_history = {}
    for root, root_trees in graph_config.trees.items():
        history = getattr(root_trees["vartree"], "_aux_get_history", None)
        if history is not None:
            aux_get_history[root] = [str(cpv) for cpv in history]

    return {
        "nodes": [_encode_node(node) for node in nodes],
        "graph_nodes": graph_nodes,
        "edges": edges,
        "mergelist": [index[node] for node in graph_config.mergelist],
        "cached": cached,
        "aux_get_history": aux_get_history,
    }


def decode_scheduler_graph(payload, trees, myopts):
    """
    Rebuild a _scheduler_graph_config instance from encode_scheduler_graph()
    output. The trees must be the ones this process will merge with.

    @raise ChildFailed: the result could not be decoded.
    """
    try:
        return _decode_scheduler_graph(payload, trees, myopts)
    except _TransferError as e:
        raise ChildFailed(str(e)) from None


def _decode_scheduler_graph(payload, trees, myopts):
    nodes = [_decode_node(entry, trees) for entry in payload["nodes"]]

    graph = digraph()
    for node in nodes[: payload["graph_nodes"]]:
        graph.add(node, None)
    for parent, child, priority in payload["edges"]:
        graph.add(nodes[child], nodes[parent], priority=_decode_priority(priority))

    # Keyed by the Package rather than by its _hash_key, which depgraph and
    # Scheduler use. Task hashes and compares by _hash_key, so the two keys
    # are interchangeable.
    pkg_cache = {}
    for node in nodes:
        if isinstance(node, Package):
            pkg_cache[node] = node
    for entry in payload["cached"]:
        pkg = _decode_node(entry, trees)
        pkg_cache.setdefault(pkg, pkg)

    mergelist = [nodes[i] for i in payload["mergelist"]]
    fake_trees = _fake_trees(payload, trees, myopts, pkg_cache)

    return _scheduler_graph_config(fake_trees, pkg_cache, graph, mergelist)


def _fake_trees(payload, trees, myopts, pkg_cache):
    """
    Recreate the fake vartrees which the depgraph handed to the scheduler,
    populated from the packages that the child sent rather than from the
    vdb, so that the dynamic dependencies it resolved are preserved.
    """
    fake_vartree_kwargs = fake_vartree_options(myopts)

    fake_trees = {}
    for root, root_trees in trees.items():
        fake_vartree = FakeVartree(
            root_trees["root_config"],
            pkg_cache=pkg_cache,
            **fake_vartree_kwargs,
        )
        # Inject the installed packages the child sent, so that _sync() keeps
        # them instead of reading the vdb again. It still validates each one
        # against the COUNTER and the mtime in the vdb, and discards any which
        # no longer match.
        for pkg in pkg_cache.values():
            if pkg.installed and pkg.operation == "nomerge" and pkg.root == root:
                fake_vartree.dbapi.cpv_inject(pkg)

        # The cpvs whose dynamic dependencies the child already resolved. This
        # has to come after the injection, since cpv_discard() drops from it.
        fake_vartree._aux_get_history.update(payload["aux_get_history"].get(root, ()))
        fake_vartree.sync()
        fake_trees[root] = {"vartree": fake_vartree}

    return fake_trees


def _send(sock, payload):
    blob = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    sock.sendall(len(blob).to_bytes(_LENGTH_BYTES, "little"))
    sock.sendall(blob)


def _recv_exact(sock, size):
    """
    Read exactly size bytes, or return None if the peer closed first.
    """
    chunks = []
    received = 0
    while received < size:
        chunk = sock.recv(min(_RECV_CHUNK_SIZE, size - received))
        if not chunk:
            return None
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


def _recv(sock):
    header = _recv_exact(sock, _LENGTH_BYTES)
    if header is None:
        raise _TransferError("the child exited without sending a result")

    blob = _recv_exact(sock, int.from_bytes(header, "little"))
    if blob is None:
        raise _TransferError("the child exited while sending its result")

    try:
        return pickle.loads(blob)
    except Exception as e:
        raise _TransferError(f"malformed result from the child: {e}") from e


def _child_setup():
    """
    Put the child in the state that portage expects of a forked process.

    This is ForkProcess._bootstrap() less the SIGINT and SIGTERM handlers,
    which the child keeps because it owns the terminal and runs the --ask
    prompt, so an interrupt has to behave as it does in emerge itself.
    """
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    try:
        wakeup_fd = signal.set_wakeup_fd(-1)
        if wakeup_fd > 0:
            os.close(wakeup_fd)
    except (ValueError, OSError):
        pass

    portage.locks._close_fds()
    portage.process.spawned_pids = []


def _child_exit_hooks():
    """
    Run the exit hooks which the child registered, since os._exit() will not.

    run_exitfuncs() skips the hooks that were registered before the fork (see
    bug 937891), and never sees a coroutine hook, which atexit_register() puts
    on the event loop for close() to run.
    """
    try:
        loop = global_event_loop(create=False)
        if loop is not None:
            loop.close()
    except BaseException:
        traceback.print_exc()

    try:
        portage.process.run_exitfuncs()
    except BaseException:
        traceback.print_exc()


def run_in_child(target):
    """
    Call target() in a child process and return the value it produced.

    The value must be picklable. The child inherits stdio, so anything the
    target displays (or asks the user) behaves as it does in process.

    @raise ForkFailed: the child never reached target(), and the caller may
            call it in this process instead.
    @raise ChildFailed: the child reached target() and then failed. It may
            have displayed output or prompted the user, so the caller must
            not call target() again. Its exit_code attribute carries the
            status of the child, so that an interrupt stays an interrupt.
    """
    try:
        parent_sock, child_sock = socket.socketpair()
    except OSError as e:
        raise ForkFailed(f"socketpair failed: {e}") from e

    sys.stdout.flush()
    sys.stderr.flush()

    try:
        pid = os.fork()
    except OSError as e:
        parent_sock.close()
        child_sock.close()
        raise ForkFailed(f"fork failed: {e}") from e

    if pid == 0:
        status = 1
        try:
            parent_sock.close()
            _child_setup()
            # Everything from here on may write to the inherited stdio, so
            # tell the parent that a failure is no longer safe to retry.
            child_sock.sendall(_CHILD_READY)
            _send(child_sock, target())
            status = 0
        except SystemExit as e:
            # UserQuery.query() exits this way when the prompt is interrupted.
            status = e.code if isinstance(e.code, int) else int(e.code is not None)
        except KeyboardInterrupt:
            status = 128 + signal.SIGINT
        except BaseException:
            traceback.print_exc()
        finally:
            _child_exit_hooks()
            try:
                sys.stdout.flush()
                sys.stderr.flush()
                child_sock.close()
            except BaseException:
                pass
            os._exit(status)

    child_sock.close()
    started = False
    try:
        try:
            started = _recv_exact(parent_sock, len(_CHILD_READY)) == _CHILD_READY
            if not started:
                raise _TransferError("the child exited before it started")
            payload = _recv(parent_sock)
        finally:
            parent_sock.close()
    except _TransferError as e:
        message = str(e)
    except KeyboardInterrupt:
        # The same signal reached the child, which is where the calculation
        # or the prompt was interrupted, so let its status say so.
        message = "the child was interrupted"
    except Exception as e:
        message = f"could not read the result from the child: {e}"
    except BaseException:
        # Reap the child rather than leaving it behind.
        _wait(pid)
        raise
    else:
        status = _wait(pid)
        if status not in (0, None):
            raise ChildFailed(
                f"the child exited with status {status}", exit_code=status
            )
        return payload

    status = _wait(pid)
    if started:
        raise ChildFailed(message, exit_code=status or 1) from None
    raise ForkFailed(message) from None


def _wait(pid):
    """
    Reap pid and return its exit status, or None if it was reaped elsewhere.
    """
    while True:
        try:
            _, status = os.waitpid(pid, 0)
        except InterruptedError:
            continue
        except ChildProcessError:
            return None
        if os.WIFEXITED(status):
            return os.WEXITSTATUS(status)
        if os.WIFSIGNALED(status):
            return 128 + os.WTERMSIG(status)
        return 1
