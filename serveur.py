from configparser import ConfigParser
from pathlib import Path
from socket import AF_INET, SOCK_DGRAM, SO_REUSEADDR, SOL_SOCKET
import struct

import protocole
import usocket

PORT = 4242
CONFIG_PATH = Path(__file__).with_name("config.ini")
SERVER_ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = SERVER_ROOT / "uploads"


def load_config():
    parser = ConfigParser()
    parser.read(CONFIG_PATH, encoding="utf-8")

    return {
        "fiabilite": parser.getfloat("RESEAU", "fiabilite", fallback=1.0),
        "taux_corruption": parser.getfloat("RESEAU", "taux_corruption", fallback=0.0),
        "mss": parser.getint("PROTOCOLE", "mss", fallback=1024),
        "window_size": parser.getint("PROTOCOLE", "fenetrage", fallback=1),
    }


def make_ack(seq):
    return protocole.build_packet(
        protocole.PROTOCOL_VERSION, protocole.MSG_ACK, 0, seq
    )


def list_server_files():
    files = sorted(
        path.name for path in SERVER_ROOT.iterdir() if path.is_file() and not path.name.startswith(".")
    )
    upload_files = sorted(
        f"uploads/{path.name}" for path in UPLOAD_DIR.iterdir() if path.is_file()
    ) if UPLOAD_DIR.exists() else []
    return "\n".join(files + upload_files).encode("utf-8")


def start_upload_session(addr, seq, payload, sessions, negotiated_mss):
    if len(payload) < 2:
        return None, "Payload initial incomplet"

    try:
        filename, file_data = protocole.parse_filename_payload(payload)
    except ValueError as exc:
        return None, str(exc)
    if not filename or Path(filename).name != filename:
        return None, "Nom de fichier invalide"

    close_session(sessions, addr)
    UPLOAD_DIR.mkdir(exist_ok=True)
    destination = UPLOAD_DIR / filename
    file_obj = destination.open("wb")
    if len(file_data) > negotiated_mss:
        file_obj.close()
        destination.unlink(missing_ok=True)
        return None, f"Bloc initial trop grand: {len(file_data)} > MSS {negotiated_mss}"
    file_obj.write(file_data)
    sessions[addr] = {
        "expected_seq": seq + 1,
        "file": file_obj,
        "path": destination,
        "mode": "put",
    }
    return filename, None


def append_upload_session(addr, seq, payload, sessions, negotiated_mss):
    session = sessions.get(addr)
    if session is None:
        return "Aucune session de televersement active"
    if seq < session["expected_seq"]:
        return f"DUPLICATE:{seq}"
    if seq != session["expected_seq"]:
        return f"Numero de sequence inattendu: {seq}"

    if len(payload) == 0:
        session["file"].close()
        path = session["path"]
        session["expected_seq"] = seq + 1
        session["completed_seq"] = seq
        session["completed"] = True
        return f"Fichier recu: {path.name}"

    if len(payload) > negotiated_mss:
        return f"Bloc trop grand: {len(payload)} > MSS {negotiated_mss}"

    session["file"].write(payload)
    session["expected_seq"] += 1
    return None


def close_session(sessions, addr):
    session = sessions.pop(addr, None)
    if session is not None and not session["file"].closed:
        session["file"].close()


def start_resume_session(addr, filename, sessions):
    if not filename or Path(filename).name != filename:
        return None, "Nom de fichier invalide"

    close_session(sessions, addr)
    UPLOAD_DIR.mkdir(exist_ok=True)
    destination = UPLOAD_DIR / filename
    bytes_received = destination.stat().st_size if destination.exists() else 0
    mode = "ab" if bytes_received > 0 else "wb"
    file_obj = destination.open(mode)
    sessions[addr] = {
        "expected_seq": 1,
        "file": file_obj,
        "path": destination,
        "mode": "resume",
    }
    return bytes_received, None


def main():
    config = load_config()
    sock = usocket.usocket(
        AF_INET,
        SOCK_DGRAM,
        fiabilite=config["fiabilite"],
        taux_corruption=config["taux_corruption"],
    )
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", PORT))
    except OSError as exc:
        print(f"Impossible de demarrer le serveur sur le port {PORT}: {exc}", flush=True)
        return

    print(f"Serveur en ecoute sur le port {PORT}", flush=True)
    upload_sessions = {}
    peer_params = {}

    while True:
        data, addr = sock.recvfrom(65535)
        try:
            ver, typ, seq, ack, payload_len, checksum, payload = protocole.parse_packet(data)
        except ValueError as exc:
            print(f"Paquet ignore de {addr}: {exc}", flush=True)
            continue

        if not protocole.is_supported_version(ver):
            print(f"Paquet ignore de {addr}: version {ver} non supportee", flush=True)
            continue

        if typ == protocole.MSG_OPEN:
            print(f"[RECV] OPEN de {addr}", flush=True)
            try:
                requested_mss, requested_window = protocole.parse_negotiation_payload(payload)
            except ValueError as exc:
                print(f"OPEN invalide de {addr}: {exc}", flush=True)
                continue
            negotiated_mss = max(1, min(requested_mss, config["mss"]))
            negotiated_window = max(1, min(requested_window, config["window_size"]))
            peer_params[addr] = {
                "mss": negotiated_mss,
                "window_size": negotiated_window,
            }
            rep = protocole.build_packet(
                protocole.PROTOCOL_VERSION,
                protocole.MSG_OPEN_ACK,
                0,
                0,
                protocole.build_negotiation_payload(negotiated_mss, negotiated_window),
            )
            print(
                f"[SEND] OPEN_ACK vers {addr} "
                f"(mss={negotiated_mss}, window_size={negotiated_window})",
                flush=True,
            )
            sock.sendto(rep, addr)

        elif typ == protocole.MSG_LS:
            print(f"[RECV] LS de {addr}", flush=True)
            listing = list_server_files()
            rep = protocole.build_packet(
                protocole.PROTOCOL_VERSION,
                protocole.MSG_LS_RESP,
                0,
                0,
                listing,
            )
            print(f"[SEND] LS_RESP vers {addr} ({len(listing)} octets)", flush=True)
            sock.sendto(rep, addr)

        elif typ == protocole.MSG_RESUME:
            print(f"[RECV] RESUME de {addr}", flush=True)
            try:
                filename, _ = protocole.parse_filename_payload(payload)
            except ValueError as exc:
                print(f"RESUME invalide de {addr}: {exc}", flush=True)
                continue
            bytes_received, error = start_resume_session(addr, filename, upload_sessions)
            if error is not None:
                print(f"RESUME refuse de {addr}: {error}", flush=True)
                close_session(upload_sessions, addr)
                continue
            rep = protocole.build_packet(
                protocole.PROTOCOL_VERSION,
                protocole.MSG_RESUME_ACK,
                0,
                0,
                protocole.build_resume_ack_payload(bytes_received),
            )
            print(
                f"[SEND] RESUME_ACK vers {addr} "
                f"(bytes_valides={bytes_received})",
                flush=True,
            )
            sock.sendto(rep, addr)

        elif typ == protocole.MSG_DATA:
            try:
                negotiated = peer_params.get(addr, {"mss": config["mss"], "window_size": 1})
                existing_session = upload_sessions.get(addr)
                if existing_session is not None and seq < existing_session["expected_seq"]:
                    print(
                        f"[RECV] DATA seq={seq} duplique depuis {addr}",
                        flush=True,
                    )
                    print(f"[SEND] ACK {seq} vers {addr}", flush=True)
                    sock.sendto(make_ack(seq), addr)
                    continue

                if existing_session is None:
                    if seq != 1:
                        print(
                            f"Paquet DATA ignore de {addr}: aucune session active pour seq={seq}",
                            flush=True,
                        )
                        continue
                    filename, error = start_upload_session(
                        addr,
                        seq,
                        payload,
                        upload_sessions,
                        negotiated["mss"],
                    )
                    if error is not None:
                        print(f"Televersement refuse de {addr}: {error}", flush=True)
                        close_session(upload_sessions, addr)
                        continue
                    print(
                        f"[RECV] DATA seq=1 debut televersement {filename} "
                        f"depuis {addr} ({payload_len} octets)"
                    , flush=True)
                else:
                    result = append_upload_session(
                        addr,
                        seq,
                        payload,
                        upload_sessions,
                        negotiated["mss"],
                    )
                    if result is not None:
                        if result.startswith("Fichier recu:"):
                            print(f"[RECV] DATA seq={seq} FIN depuis {addr}", flush=True)
                            print(f"{result} depuis {addr}", flush=True)
                        else:
                            print(f"Paquet DATA ignore de {addr}: {result}", flush=True)
                            continue
                    else:
                        print(
                            f"[RECV] DATA seq={seq} depuis {addr} ({payload_len} octets)",
                            flush=True,
                        )
                print(f"[SEND] ACK {seq} vers {addr}", flush=True)
                sock.sendto(make_ack(seq), addr)
            except OSError as exc:
                print(f"Erreur d'ecriture pour {addr}: {exc}", flush=True)
                close_session(upload_sessions, addr)

        elif typ == protocole.MSG_BYE:
            close_session(upload_sessions, addr)
            peer_params.pop(addr, None)
            print(f"[RECV] BYE de {addr} - fermeture de session", flush=True)

        else:
            print(f"Message inconnu de {addr}: type={typ}", flush=True)


if __name__ == "__main__":
    main()
