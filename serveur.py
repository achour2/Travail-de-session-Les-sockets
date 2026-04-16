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
    }


def make_ack(seq):
    return protocole.make_header(
        protocole.PROTOCOL_VERSION, protocole.MSG_ACK, 0, seq, 0, 0
    )


def list_server_files():
    files = sorted(
        path.name for path in SERVER_ROOT.iterdir() if path.is_file() and not path.name.startswith(".")
    )
    upload_files = sorted(
        f"uploads/{path.name}" for path in UPLOAD_DIR.iterdir() if path.is_file()
    ) if UPLOAD_DIR.exists() else []
    return "\n".join(files + upload_files).encode("utf-8")


def start_upload_session(addr, seq, payload, sessions):
    if len(payload) < 2:
        return None, "Payload initial incomplet"

    name_len = struct.unpack("!H", payload[:2])[0]
    if len(payload) < 2 + name_len:
        return None, "Nom de fichier incomplet"

    filename = payload[2 : 2 + name_len].decode("utf-8", errors="strict")
    if not filename or Path(filename).name != filename:
        return None, "Nom de fichier invalide"

    UPLOAD_DIR.mkdir(exist_ok=True)
    destination = UPLOAD_DIR / filename
    file_obj = destination.open("wb")
    file_obj.write(payload[2 + name_len :])
    sessions[addr] = {"expected_seq": seq + 1, "file": file_obj, "path": destination}
    return filename, None


def append_upload_session(addr, seq, payload, sessions):
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
        session["completed_seq"] = seq
        session["completed"] = True
        return f"Fichier recu: {path.name}"

    session["file"].write(payload)
    session["expected_seq"] += 1
    return None


def close_session(sessions, addr):
    session = sessions.pop(addr, None)
    if session is not None and not session["file"].closed:
        session["file"].close()


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

    while True:
        data, addr = sock.recvfrom(65535)
        try:
            ver, typ, seq, ack, payload_len, checksum = protocole.parse_header(data)
        except ValueError:
            print(f"Paquet ignore de {addr}: message trop court", flush=True)
            continue

        if not protocole.is_supported_version(ver):
            print(f"Paquet ignore de {addr}: version {ver} non supportee", flush=True)
            continue

        payload = data[protocole.HEADER_SIZE : protocole.HEADER_SIZE + payload_len]

        if typ == protocole.MSG_OPEN:
            print(f"[RECV] OPEN de {addr}", flush=True)
            rep = protocole.make_header(
                protocole.PROTOCOL_VERSION, protocole.MSG_OPEN_ACK, 0, 0, 0, 0
            )
            print(f"[SEND] OPEN_ACK vers {addr}", flush=True)
            sock.sendto(rep, addr)

        elif typ == protocole.MSG_LS:
            print(f"[RECV] LS de {addr}", flush=True)
            listing = list_server_files()
            rep = protocole.make_header(
                protocole.PROTOCOL_VERSION,
                protocole.MSG_LS_RESP,
                0,
                0,
                len(listing),
                0,
            ) + listing
            print(f"[SEND] LS_RESP vers {addr} ({len(listing)} octets)", flush=True)
            sock.sendto(rep, addr)

        elif typ == protocole.MSG_DATA:
            try:
                existing_session = upload_sessions.get(addr)
                if existing_session is not None and seq < existing_session["expected_seq"]:
                    print(
                        f"[RECV] DATA seq={seq} duplique depuis {addr}",
                        flush=True,
                    )
                    print(f"[SEND] ACK {seq} vers {addr}", flush=True)
                    sock.sendto(make_ack(seq), addr)
                    continue

                if seq == 1:
                    filename, error = start_upload_session(addr, seq, payload, upload_sessions)
                    if error is not None:
                        print(f"Televersement refuse de {addr}: {error}", flush=True)
                        close_session(upload_sessions, addr)
                        continue
                    print(
                        f"[RECV] DATA seq=1 debut televersement {filename} "
                        f"depuis {addr} ({payload_len} octets)"
                    , flush=True)
                else:
                    result = append_upload_session(addr, seq, payload, upload_sessions)
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
                session = upload_sessions.get(addr)
                if session is not None and session.get("completed"):
                    close_session(upload_sessions, addr)
            except OSError as exc:
                print(f"Erreur d'ecriture pour {addr}: {exc}", flush=True)
                close_session(upload_sessions, addr)

        elif typ == protocole.MSG_BYE:
            close_session(upload_sessions, addr)
            print(f"[RECV] BYE de {addr} - fermeture de session", flush=True)

        else:
            print(f"Message inconnu de {addr}: type={typ}", flush=True)


if __name__ == "__main__":
    main()
