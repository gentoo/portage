backtracking: Reject a binary package early if we have several unusable
binpkgs rather than trying them all.

This is for the case where we know they're all fail for the same reason
as they have the same sub-slot dep recorded, but say have a different
BUILD_ID.
