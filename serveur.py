from configparser import ConfigParser
from pathlib import Path
from socket import AF_INET, SOCK_DGRAM, SO_REUSEADDR, SOL_SOCKET

import protocole
import usocket

PORT = 4242
CONFIG_PATH = Path(__file__).with_name("config.ini")


def load_config():
    parser = ConfigParser()
    parser.read(CONFIG_PATH, encoding="utf-8")

    return {
        "fiabilite": parser.getfloat("RESEAU", "fiabilite", fallback=1.0),
        "taux_corruption": parser.getfloat("RESEAU", "taux_corruption", fallback=0.0),
    }


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

    while True:
        data, addr = sock.recvfrom(4096)
        try:
            ver, typ, seq, ack, payload_len, checksum = protocole.parse_header(data)
        except ValueError:
            print(f"Paquet ignore de {addr}: message trop court", flush=True)
            continue

        if not protocole.is_supported_version(ver):
            print(f"Paquet ignore de {addr}: version {ver} non supportee", flush=True)
            continue

        if typ == protocole.MSG_OPEN:
            print(f"OPEN recu de {addr}", flush=True)
            rep = protocole.make_header(
                protocole.PROTOCOL_VERSION, protocole.MSG_OPEN_ACK, 0, 0, 0, 0
            )
            sock.sendto(rep, addr)
        elif typ == protocole.MSG_BYE:
            print(f"BYE recu de {addr} - fermeture de session", flush=True)
        else:
            print(f"Message inconnu de {addr}: type={typ}", flush=True)


if __name__ == "__main__":
    main()
