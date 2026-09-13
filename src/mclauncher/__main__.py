import multiprocessing

# Absolute, not relative: the native window runs in a spawned child process that
# re-imports this module under a different name, where a relative import has no
# parent package to resolve against.
from mclauncher import ensure_streams, main

# At import time, so the spawned child process gets usable streams too.
ensure_streams()

if __name__ == "__main__":
    # A frozen build would otherwise re-run the launcher instead of starting
    # that child process.
    multiprocessing.freeze_support()
    main()
