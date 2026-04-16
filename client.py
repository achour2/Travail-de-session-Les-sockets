from configparser import ConfigParser
from pathlib import Path
from socket import AF_INET, SOCK_DGRAM, timeout
import struct

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
        "mss": parser.getint("PROTOCOLE", "mss", fallback=1024),
        "window_size": parser.getint("PROTOCOLE", "fenetrage", fallback=1),
    }


def wait_for_message(sock, expected_type, max_reprises):
    for tentative in range(1, max_reprises + 1):
        try:
            data, _ = sock.recvfrom(65535)
            ver, typ, seq, ack, payload_len, checksum, payload = protocole.parse_packet(data)
            if not protocole.is_supported_version(ver):
                print(f"Version de protocole non supportee: {ver}")
                return None
            if typ != expected_type:
                print(
                    f"[RECV] type={typ} seq={seq} ack={ack} taille={payload_len} "
                    f"(attendu type={expected_type})"
                )
                continue
            print(f"[RECV] type={typ} seq={seq} ack={ack} taille={payload_len}")
            return ver, typ, seq, ack, payload
        except timeout:
            print(f"Timeout: tentative {tentative}/{max_reprises}")
        except ConnectionResetError:
            print("Connexion refusee: aucun serveur n'ecoute sur ce port")
            return None
        except ValueError as exc:
            print(f"Reponse ignoree: {exc}")
    return None


def wait_for_ack(sock, expected_ack, max_reprises):
    while True:
        message = wait_for_message(sock, protocole.MSG_ACK, max_reprises)
        if message is None:
            return False

        _, _, _, ack, _ = message
        if ack < expected_ack:
            print(f"[ACK] ancien ACK recu pour le segment {ack}, ignore")
            continue
        if ack != expected_ack:
            print(f"ACK inattendu recu: {ack}, attendu: {expected_ack}")
            return False
        print(f"[ACK] confirmation recue pour le segment {ack}")
        return True


def open_connection(sock, server_addr, config):
    payload = protocole.build_negotiation_payload(
        config["mss"],
        config["window_size"],
    )
    packet = protocole.build_packet(
        protocole.PROTOCOL_VERSION, protocole.MSG_OPEN, 0, 0, payload
    )

    for tentative in range(1, config["max_reprises"] + 1):
        print(f"[SEND] OPEN vers {server_addr[0]}:{server_addr[1]} (tentative {tentative})")
        sock.sendto(packet, server_addr)
        message = wait_for_message(sock, protocole.MSG_OPEN_ACK, 1)
        if message is not None:
            _, _, _, _, response_payload = message
            try:
                negotiated_mss, negotiated_window = protocole.parse_negotiation_payload(
                    response_payload
                )
            except ValueError as exc:
                print(f"OPEN_ACK invalide: {exc}")
                return None
            print(
                "Connecte au serveur "
                f"(mss={negotiated_mss}, window_size={negotiated_window})"
            )
            return {
                "addr": server_addr,
                "mss": negotiated_mss,
                "window_size": negotiated_window,
            }
        print(f"Nouvelle tentative de connexion {tentative}/{config['max_reprises']}")

    print("Echec de connexion apres plusieurs tentatives")
    return None


def list_remote_files(sock, connection, max_reprises):
    packet = protocole.build_packet(
        protocole.PROTOCOL_VERSION, protocole.MSG_LS, 0, 0
    )
    server_addr = connection["addr"]
    print(f"[SEND] LS vers {server_addr[0]}:{server_addr[1]}")
    sock.sendto(packet, server_addr)
    message = wait_for_message(sock, protocole.MSG_LS_RESP, max_reprises)
    if message is None:
        print("Impossible de recuperer la liste des fichiers")
        return

    _, _, _, _, payload = message
    listing = payload.decode("utf-8", errors="replace")
    print("Fichiers disponibles sur le serveur:")
    if listing:
        print(listing)
    else:
        print("(aucun fichier)")


def send_packet_with_retry(sock, packet, server_addr, seq, max_reprises):
    for tentative in range(1, max_reprises + 1):
        payload_len = len(packet) - protocole.HEADER_SIZE
        print(
            f"[SEND] DATA seq={seq} taille={payload_len} "
            f"vers {server_addr[0]}:{server_addr[1]} (tentative {tentative})"
        )
        sock.sendto(packet, server_addr)
        if wait_for_ack(sock, seq, 1):
            return True
        print(f"Reemission du paquet {seq} ({tentative}/{max_reprises})")
    return False


def upload_file(sock, connection, filepath, max_reprises):
    path = Path(filepath)
    if not path.is_file():
        print(f"Fichier introuvable: {filepath}")
        return

    server_addr = connection["addr"]
    mss = connection["mss"]
    window_size = connection["window_size"]

    filename_bytes = path.name.encode("utf-8")
    if len(filename_bytes) > 65535:
        print("Nom de fichier trop long")
        return

    data = path.read_bytes()
    print(
        f"Preparation du fichier {path.name}: {len(data)} octets "
        f"(mss negocie={mss}, window_size={window_size})"
    )
    first_chunk_size = max(1, mss - 2 - len(filename_bytes))
    chunks = []

    first_payload = protocole.build_filename_payload(filename_bytes)
    first_payload += data[:first_chunk_size]
    chunks.append(first_payload)

    offset = first_chunk_size
    while offset < len(data):
        chunks.append(data[offset : offset + mss])
        offset += mss

    if not send_data_chunks(sock, server_addr, chunks, max_reprises):
        print("Echec du televersement")
        return

    end_packet = protocole.build_packet(
        protocole.PROTOCOL_VERSION, protocole.MSG_DATA, len(chunks) + 1, 0
    )
    print(f"[SEND] FIN seq={len(chunks) + 1}")
    if not send_packet_with_retry(sock, end_packet, server_addr, len(chunks) + 1, max_reprises):
        print("Echec de finalisation du televersement")
        return

    print(f"Fichier televerse: {path.name} en {len(chunks)} segment(s) + FIN")


def send_data_chunks(sock, server_addr, chunks, max_reprises):
    for seq, payload in enumerate(chunks, start=1):
        packet = protocole.build_packet(
            protocole.PROTOCOL_VERSION, protocole.MSG_DATA, seq, 0, payload
        )
        if not send_packet_with_retry(sock, packet, server_addr, seq, max_reprises):
            return False
    return True


def request_resume(sock, connection, filename, max_reprises):
    server_addr = connection["addr"]
    filename_bytes = filename.encode("utf-8")
    packet = protocole.build_packet(
        protocole.PROTOCOL_VERSION,
        protocole.MSG_RESUME,
        0,
        0,
        protocole.build_filename_payload(filename_bytes),
    )
    print(f"[SEND] RESUME {filename} vers {server_addr[0]}:{server_addr[1]}")
    sock.sendto(packet, server_addr)
    message = wait_for_message(sock, protocole.MSG_RESUME_ACK, max_reprises)
    if message is None:
        print("Impossible de recuperer le point de reprise")
        return None

    _, _, _, _, payload = message
    try:
        return protocole.parse_resume_ack_payload(payload)
    except ValueError as exc:
        print(f"RESUME_ACK invalide: {exc}")
        return None


def resume_file(sock, connection, filepath, max_reprises):
    path = Path(filepath)
    if not path.is_file():
        print(f"Fichier introuvable: {filepath}")
        return

    server_addr = connection["addr"]
    mss = connection["mss"]
    data = path.read_bytes()

    offset = request_resume(sock, connection, path.name, max_reprises)
    if offset is None:
        return
    if offset > len(data):
        print(
            f"Resume impossible: le serveur annonce {offset} octets, "
            f"mais le fichier local en contient {len(data)}"
        )
        return

    print(
        f"Reprise de {path.name}: offset serveur={offset} / taille locale={len(data)}"
    )
    remaining = data[offset:]
    chunks = [remaining[i : i + mss] for i in range(0, len(remaining), mss)]

    if chunks and not send_data_chunks(sock, server_addr, chunks, max_reprises):
        print("Echec de la reprise du televersement")
        return

    end_seq = len(chunks) + 1
    end_packet = protocole.build_packet(
        protocole.PROTOCOL_VERSION, protocole.MSG_DATA, end_seq, 0
    )
    print(f"[SEND] FIN reprise seq={end_seq}")
    if not send_packet_with_retry(sock, end_packet, server_addr, end_seq, max_reprises):
        print("Echec de finalisation de la reprise")
        return

    print(f"Reprise terminee pour {path.name}")


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
            server_addr = open_connection(sock, addr, config)

        elif cmd[0] == "ls":
            if server_addr is None:
                print("Aucun serveur connecte. Utilise d'abord: open IP")
                continue
            list_remote_files(sock, server_addr, config["max_reprises"])

        elif cmd[0] == "put":
            if len(cmd) != 2:
                print("Usage: put nom_de_fichier")
                continue
            if server_addr is None:
                print("Aucun serveur connecte. Utilise d'abord: open IP")
                continue
            upload_file(
                sock,
                server_addr,
                cmd[1],
                config["max_reprises"],
            )

        elif cmd[0] == "resume":
            if len(cmd) != 2:
                print("Usage: resume nom_de_fichier")
                continue
            if server_addr is None:
                print("Aucun serveur connecte. Utilise d'abord: open IP")
                continue
            resume_file(
                sock,
                server_addr,
                cmd[1],
                config["max_reprises"],
            )

        elif cmd[0] == "bye":
            if server_addr:
                header = protocole.build_packet(
                    protocole.PROTOCOL_VERSION, protocole.MSG_BYE, 0, 0
                )
                sock.sendto(header, server_addr["addr"])
            print("Fermeture du client")
            break
        else:
            print(f"Commande inconnue: {cmd[0]}")


if __name__ == "__main__":
    main()
