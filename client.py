import usocket
import protocole
import sys


def main():
    sock = usocket.socket(usocket.AF_INET, usocket.SOCK_DGRAM)
    sock.settimeout(3.0)
    server_addr = None

    while True:
        cmd = input("> ").strip().split()
        if not cmd:
            continue

        if cmd[0] == "open":
            if len(cmd) != 2:
                print("Usage: open IP")
                continue
            addr = (cmd[1], 4242)
            header = protocole.make_header(1, protocole.MSG_OPEN, 0, 0, 0, 0)
            sock.sendto(header, addr)
            try:
                data, _ = sock.recvfrom(4096)
                typ = protocole.parse_header(data)[1]
                if typ == protocole.MSG_OPEN_ACK:
                    print("Connecté au serveur")
                    server_addr = addr
                else:
                    print("Erreur de handshake")
            except usocket.timeout:
                print("Timeout: serveur injoignable")

        elif cmd[0] == "bye":
            if server_addr:
                header = protocole.make_header(1, protocole.MSG_BYE, 0, 0, 0, 0)
                sock.sendto(header, server_addr)
            print("Fermeture du client")
            break
        else:
            print(f"Commande inconnue: {cmd[0]}")


if __name__ == "__main__":
    main()