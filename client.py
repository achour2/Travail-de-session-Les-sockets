from configparser import ConfigParser
from pathlib import Path
from socket import AF_INET, SOCK_DGRAM, timeout

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
        "timeout": parser.getfloat("RESEAU", "timeout", fallback=3.0),
        "max_reprises": parser.getint("RESEAU", "max_reprises", fallback=1),
    }


def open_connection(sock, server_addr, max_reprises):
    header = protocole.make_header(
        protocole.PROTOCOL_VERSION, protocole.MSG_OPEN, 0, 0, 0, 0
    )

    for tentative in range(1, max_reprises + 1):
        sock.sendto(header, server_addr)
        try:
            data, _ = sock.recvfrom(4096)
            ver, typ, seq, ack, payload_len, checksum = protocole.parse_header(data)
            if not protocole.is_supported_version(ver):
                print(f"Version de protocole non supportee: {ver}")
                return None
            if typ != protocole.MSG_OPEN_ACK:
                print(f"Reponse inattendue du serveur: type={typ}")
                return None

            print("Connecte au serveur")
            return server_addr
        except timeout:
            print(f"Timeout: tentative {tentative}/{max_reprises}")
        except ConnectionResetError:
            print("Connexion refusee: aucun serveur n'ecoute sur ce port")
            return None
        except ValueError as exc:
            print(f"Reponse ignoree: {exc}")

    print("Echec de connexion apres plusieurs tentatives")
    return None


def main():
    config = load_config()
    sock = usocket.usocket(
        AF_INET,
        SOCK_DGRAM,
        fiabilite=config["fiabilite"],
        taux_corruption=config["taux_corruption"],
    )
    sock.settimeout(config["timeout"])
    server_addr = None

    while True:
        try:
            cmd = input("> ").strip().split()
        except EOFError:
            print("\nFermeture du client")
            break
        except KeyboardInterrupt:
            print("\nInterruption utilisateur")
            break
        if not cmd:
            continue

        if cmd[0] == "open":
            if len(cmd) != 2:
                print("Usage: open IP")
                continue

            addr = (cmd[1], PORT)
            server_addr = open_connection(sock, addr, config["max_reprises"])

        elif cmd[0] == "bye":
            if server_addr:
                header = protocole.make_header(
                    protocole.PROTOCOL_VERSION, protocole.MSG_BYE, 0, 0, 0, 0
                )
                sock.sendto(header, server_addr)
            print("Fermeture du client")
            break
        else:
            print(f"Commande inconnue: {cmd[0]}")


if __name__ == "__main__":
    main()
