# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import portage


def show_lru_cache_info():
    if not os.environ.get("PORTAGE_SHOW_LRU_CACHE_INFO"):
        return

    portage_lru_caches = {
        portage.dep._use_reduce_cached: "use_reduce_cached",
        portage.eapi._get_eapi_attrs: "get_eapi_attrs",
        portage.process._encoded_length: "encoded_length",
        portage.versions.catpkgsplit: "catpkgsplit",
        portage.versions.vercmp: "vercmp",
    }

    print("Portage @lru_cache information")
    for method, name in portage_lru_caches.items():
        cache_info = method.cache_info()

        hits = cache_info.hits
        misses = cache_info.misses
        maxsize = cache_info.maxsize
        currsize = cache_info.currsize

        total = hits + misses
        if total:
            hitratio = hits / total
        else:
            hitratio = 0

        if maxsize:
            utilization = currsize / maxsize
        else:
            utilization = 0

        pretty_cache_info = f"hit ratio: {hitratio:.2%} (total: {total}, hits: {hits}, misses: {misses}) util: {utilization:.2%} ({maxsize} / {currsize})"

        print(f"{name}: {pretty_cache_info}")
