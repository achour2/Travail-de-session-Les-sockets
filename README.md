# usocket

Petit wrapper pédagogique autour de `socket.socket` pour simuler un réseau peu fiable.
L’idée est simple: pour les sockets UDP, chaque envoi a une probabilité `fiabilite`
de réussir. Si l’envoi est « perdu », la fonction renvoie quand même ce que
l’application s’attend à voir (ex: `len(data)`), ce qui permet de tester la robustesse
d’un protocole.

En plus, les réceptions UDP (`recv`, `recvfrom`, `recv_into`, `recvfrom_into`)
peuvent **corrompre** des données selon un taux configurable (`taux_corruption`).

## Fichiers fournis

- `usocket.pyc` : le module compilé (bytecode).
- `usocket.pyi` : signatures pour l’autocomplétion (IntelliSense).

Vous recevrez une version de `usocket.pyc` par version Python (3.10, 3.11, 3.12).
Prenez **celle qui correspond à votre Python et renommez-la usocket.pyc**.

## Installation

Placez `usocket.pyc` et `usocket.pyi` dans le même dossier que votre code (ou dans un
répertoire présent dans `PYTHONPATH`).

Si votre fichier `.pyc` a un nom versionné (ex: `usocket.311.pyc`), renommez-le
en `usocket.pyc` pour que l’import fonctionne simplement.

Ensuite, vous pouvez l’utiliser comme un module normal:

```python
from usocket import usocket
```

## Principe

- `fiabilite = 1.0` : aucun paquet perdu.
- `fiabilite = 0.7` : ~30% des envois UDP sont « perdus ».
- `taux_corruption = 0.02` : ~2% des messages UDP reçus sont altérés.
- La perte est simulée **côté envoi** pour UDP.
- La corruption est simulée **côté réception** pour UDP.
- `connect()` n’est pas rendu « peu fiable » : sur UDP, il sert surtout à fixer
  l’adresse distante par défaut.

## Exemple minimal (UDP)

```python
from socket import AF_INET, SOCK_DGRAM
from usocket import usocket

s = usocket(
    family=AF_INET,
    type=SOCK_DGRAM,
    fiabilite=0.7,
    taux_corruption=0.02,
)

message = b"bonjour"
s.sendto(message, ("127.0.0.1", 9999))
```

## Exemple avec UDP connecté

```python
from socket import AF_INET, SOCK_DGRAM
from usocket import usocket

s = usocket(
    family=AF_INET,
    type=SOCK_DGRAM,
    fiabilite=0.85,
    taux_corruption=0.05,
)

s.connect(("127.0.0.1", 9999))
s.send(b"segment 1")
reponse = s.recv(1024)
```

## Notes importantes

- Les méthodes UDP courantes redéfinies sont `send`, `sendto`, `sendall`, `recv`,
  `recvfrom`, `recv_into` et `recvfrom_into`.
- `send()` / `sendto()` renvoient `len(data)` même si l’envoi UDP est perdu.
- `sendall()` renvoie toujours `None`. Si vous l’utilisez sur un socket UDP
  connecté, une perte peut aussi être simulée.
- `recv()` et `recvfrom()` peuvent altérer les données selon `taux_corruption`.
- Le fichier `usocket.pyi` sert à afficher les bonnes signatures dans
  l’autocomplétion. Le texte d’aide provient des docstrings compilées dans
  `usocket.pyc`.

## Quand l’utiliser

- Tester la logique de retransmission.
- Vérifier les timeouts et la gestion d’erreurs.
- Simuler un réseau instable sans infrastructure externe.
