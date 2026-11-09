config: Cache parsed /etc/portage/env files instead of parsing them again for
each package that uses them.

Edits to these files are therefore no longer seen by an emerge that is
already running.
