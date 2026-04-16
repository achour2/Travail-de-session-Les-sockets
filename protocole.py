import struct
import zlib

HEADER_FMT = "!BBIIHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
NEGOTIATION_FMT = "!HH"
NEGOTIATION_SIZE = struct.calcsize(NEGOTIATION_FMT)
PROTOCOL_VERSION = 1

# Types de messages
MSG_OPEN = 1
MSG_OPEN_ACK = 2
MSG_BYE = 3
MSG_DATA = 4
MSG_ACK = 5
MSG_LS = 6
MSG_LS_RESP = 7


def compute_checksum(payload):
    return zlib.crc32(payload) & 0xFFFFFFFF


def make_header(ver, typ, seq, ack, payload_len, checksum):
    return struct.pack(HEADER_FMT, ver, typ, seq, ack, payload_len, checksum)


def build_packet(ver, typ, seq, ack, payload=b""):
    checksum = compute_checksum(payload)
    return make_header(ver, typ, seq, ack, len(payload), checksum) + payload


def parse_header(data):
    if len(data) < HEADER_SIZE:
        raise ValueError("Message trop court pour contenir un en-tete")
    return struct.unpack(HEADER_FMT, data[:HEADER_SIZE])


def parse_packet(data):
    ver, typ, seq, ack, payload_len, checksum = parse_header(data)
    total_len = HEADER_SIZE + payload_len
    if len(data) < total_len:
        raise ValueError("Message incomplet")
    payload = data[HEADER_SIZE:total_len]
    expected_checksum = compute_checksum(payload)
    if checksum != expected_checksum:
        raise ValueError(
            f"Checksum invalide: recu={checksum} attendu={expected_checksum}"
        )
    return ver, typ, seq, ack, payload_len, checksum, payload


def is_supported_version(ver):
    return ver == PROTOCOL_VERSION


def build_negotiation_payload(mss, window_size):
    return struct.pack(NEGOTIATION_FMT, mss, window_size)


def parse_negotiation_payload(payload):
    if len(payload) < NEGOTIATION_SIZE:
        raise ValueError("Payload de negotiation incomplet")
    return struct.unpack(NEGOTIATION_FMT, payload[:NEGOTIATION_SIZE])
