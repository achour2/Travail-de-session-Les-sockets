import struct

HEADER_FMT = "!BBIIHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
PROTOCOL_VERSION = 1

# Types de messages
MSG_OPEN = 1
MSG_OPEN_ACK = 2
MSG_BYE = 3
MSG_DATA = 4
MSG_ACK = 5
MSG_LS = 6
MSG_LS_RESP = 7


def make_header(ver, typ, seq, ack, payload_len, checksum):
    return struct.pack(HEADER_FMT, ver, typ, seq, ack, payload_len, checksum)


def parse_header(data):
    if len(data) < HEADER_SIZE:
        raise ValueError("Message trop court pour contenir un en-tete")
    return struct.unpack(HEADER_FMT, data[:HEADER_SIZE])


def is_supported_version(ver):
    return ver == PROTOCOL_VERSION
