"""Commands on the owning GUI's stdin; no keyboard simulation or ADB input."""


def listen_for_stop(stream, app):
    try:
        for line in stream:
            if line.strip() == 'STOP':
                break
        app.request_stop()  # EOF also means the controlling GUI has gone away.
    except (OSError, ValueError):
        app.request_stop()
