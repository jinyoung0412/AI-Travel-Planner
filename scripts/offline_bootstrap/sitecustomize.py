"""Activated only via the offline launcher's explicit PYTHONPATH."""
try:
    from scripts.offline_environment import install
    install()
except BaseException:
    # Python normally prints and ignores sitecustomize errors. Fail closed
    # without printing exception arguments (which may contain credentials).
    import os
    os.write(2, b'Offline boundary initialization failed\n')
    os._exit(70)
