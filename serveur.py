import usocket
import protocole


def main():
    sock = usocket.socket(usocket.AF_INET, usocket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 4242))
    print("Serveur en écoute sur le port 4242")

    while True:
        data, addr = sock.recvfrom(4096)
        if len(data) < protocole.HEADER_SIZE:
            continue

        ver, typ, seq, ack, payload_len, checksum = protocole.parse_header(data)

        if typ == protocole.MSG_OPEN:
            print(f"OPEN reçu de {addr}")
            rep = protocole.make_header(1, protocole.MSG_OPEN_ACK, 0, 0, 0, 0)
            sock.sendto(rep, addr)
        elif typ == protocole.MSG_BYE:
            print(f"BYE reçu de {addr} - fermeture")
        else:
            print(f"Message inconnu type={typ}")


if __name__ == "__main__":
    main()