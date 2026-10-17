"""Line framing for the local JVM bridge; empty trailing columns are data."""


def split_response(line):
    fields = line.rstrip('\r\n').split('\t')
    if not fields[0]:
        raise RuntimeError('Kotlin parser exited')
    return fields
