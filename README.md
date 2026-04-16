# Transfert fiable de fichiers sur UDP

## Auteur

- Nom : Achour Messaoudi
- Date : Avril 2026
- Contexte : Travail de session – Les sockets : Teleinformatique

## Objectif

Ce projet implemente un protocole applicatif fiable au-dessus de UDP a l'aide
du module `usocket`, qui simule un reseau non fiable avec pertes et
corruptions.

Le systeme permet :

- d'ouvrir une connexion logique client/serveur
- de lister les fichiers disponibles sur le serveur
- de televerser un fichier vers le serveur
- de reprendre un televersement interrompu
- de detecter les paquets corrompus
- de negocier la taille maximale des segments (`MSS`) et le fenetrage

Le transport reel reste UDP, mais le protocole ajoute :

- des numeros de sequence
- des ACK
- des retransmissions apres timeout
- une verification d'integrite par checksum
- une gestion des doublons

## Structure du projet

```text
Travail-de-session-Les-sockets/
|-- client.py
|-- serveur.py
|-- protocole.py
|-- config.ini
|-- README.md
|-- usocket.pyc
|-- usocket.pyi
|-- usocket.tar
|-- uploads/
|-- transfert_state.json        # cree automatiquement si un transfert est interrompu
|-- test_upload.txt             # exemple de petit fichier
|-- test_300k.bin               # exemple de gros fichier
```

## Description des fichiers

- `client.py`
  Interface console du client. Gere `open`, `ls`, `put`, `resume`, `bye`.

- `serveur.py`
  Serveur UDP qui ecoute sur le port `4242`, gere les requetes et sauvegarde
  les fichiers recus dans `uploads/`.

- `protocole.py`
  Definitions communes du protocole :
  - types de messages
  - format de l'en-tete
  - checksum CRC32
  - payloads de negotiation et de reprise

- `config.ini`
  Parametres reseau et protocole.

- `usocket.pyc` / `usocket.pyi`
  Module fourni permettant de simuler un reseau peu fiable.

- `uploads/`
  Dossier ou le serveur ecrit les fichiers recus.

- `transfert_state.json`
  Fichier cree par le client pour memoriser l'etat d'un transfert en cours
  ou interrompu.

## Prerequis

- Python 3.11 recommande
- Windows / PowerShell (mais le code Python reste portable)
- le fichier `usocket.pyc` compatible avec la version Python utilisee

## Installation

Placez les fichiers du projet dans un meme dossier.

Verifiez que `usocket.pyc` et `usocket.pyi` sont presents dans ce dossier.

Si vous utilisez un environnement virtuel :

```powershell
.\.venv\Scripts\activate
```

## Configuration

Le fichier `config.ini` contient deux sections :

```ini
[RESEAU]
fiabilite = 0.99
taux_corruption = 0.01
timeout = 2.0
max_reprises = 10

[PROTOCOLE]
mss = 1024
fenetrage = 1
```

### Signification

- `fiabilite`
  Probabilite qu'un paquet UDP soit effectivement envoye.

- `taux_corruption`
  Probabilite qu'un paquet recu soit altere.

- `timeout`
  Delai d'attente avant retransmission.

- `max_reprises`
  Nombre maximal de tentatives pour un meme segment.

- `mss`
  Nombre maximal d'octets de fichier transmis par segment.

- `fenetrage`
  Valeur negociee pendant `OPEN / OPEN_ACK`.
  Dans l'etat actuel du projet, le transfert effectif reste en `stop-and-wait`
  avec fenetre de taille 1.

## Lancement

### 1. Demarrer le serveur

```powershell
python .\serveur.py
```

Sortie attendue :

```text
Serveur en ecoute sur le port 4242
```

### 2. Demarrer le client

Dans un autre terminal :

```powershell
python .\client.py
```

## Commandes disponibles

### `open IP`

Ouvre une connexion logique avec le serveur et negocie :

- `mss`
- `window_size`

Exemple :

```text
open 127.0.0.1
```

Sortie typique :

```text
Connecte au serveur (mss=1024, window_size=1)
```

### `ls`

Retourne la liste des fichiers disponibles sur le serveur.

Exemple :

```text
ls
```

### `put nom_de_fichier`

Televerse un fichier local vers le serveur.

Exemple :

```text
put test_upload.txt
```

Le fichier est sauvegarde dans :

```text
uploads/test_upload.txt
```

### `resume nom_de_fichier`

Reprend un televersement interrompu.

Le client demande au serveur combien d'octets sont deja valides, puis reprend
l'envoi a partir de cet offset.

Exemple :

```text
resume test_300k.bin
```

### `bye`

Ferme proprement la session cote client.

## Format du protocole

### En-tete

L'en-tete binaire a le format suivant :

```python
!BBIIHI
```

Champs :

- `ver` : version du protocole
- `typ` : type du message
- `seq` : numero de sequence
- `ack` : numero acquitte
- `payload_len` : taille du payload
- `checksum` : CRC32 du payload

### Types de messages

- `MSG_OPEN = 1`
- `MSG_OPEN_ACK = 2`
- `MSG_BYE = 3`
- `MSG_DATA = 4`
- `MSG_ACK = 5`
- `MSG_LS = 6`
- `MSG_LS_RESP = 7`
- `MSG_RESUME = 8`
- `MSG_RESUME_ACK = 9`

## Handshake et negotiation

Pendant `OPEN`, le client envoie :

- `mss`
- `window_size`

Pendant `OPEN_ACK`, le serveur repond avec les valeurs negociees.

Le serveur peut donc limiter les parametres du client si besoin.

Le client utilise ensuite le `mss` negocie pour decouper les donnees.

## Televersement (`put`)

### Principe

Le televersement suit un modele `stop-and-wait` :

1. le client envoie un segment `DATA`
2. le serveur le traite
3. le serveur renvoie `ACK(seq)`
4. le client envoie le segment suivant

### Premier segment

Le premier segment contient :

- le nom du fichier
- les premiers octets du fichier

### Segments suivants

Chaque segment suivant contient uniquement des octets du fichier.

### Fin de transfert

La fin est signalee par un segment `DATA` avec payload vide.

Le serveur renvoie aussi un `ACK` pour ce segment `FIN`.

### Respect du MSS

Le serveur verifie que chaque bloc de donnees ne depasse pas le `mss` negocie.

## Reprise de transfert (`resume`)

### Principe

Si un transfert est interrompu :

- le serveur conserve le fichier partiel sur disque dans `uploads/`
- le client peut demander au serveur combien d'octets sont deja recus
- le client reprend l'envoi a partir de cet offset

### Etat client

Le client stocke un fichier `transfert_state.json` avec :

- `filename`
- `total_size`
- `last_seq_sent`
- `last_ack_recu`
- `bytes_confirmed`
- `timestamp`

Ce fichier est :

- mis a jour apres chaque ACK recu
- supprime automatiquement a la fin d'un transfert reussi

### Etat serveur

Le serveur n'utilise pas de JSON pour memoriser les segments.
Il ecrit directement le fichier partiel sur disque. Cela permet :

- de survivre a un redemarrage du serveur
- de simplifier la reprise
- d'eviter de stocker tous les segments en memoire

## Detection de corruption

Chaque paquet transporte un `checksum` CRC32 du payload.

Lorsqu'un paquet est recu :

- le checksum est recalcule
- si le checksum ne correspond pas, le paquet est ignore
- le client finira par retransmettre apres timeout

## Gestion des doublons

Le protocole gere les doublons de plusieurs manieres :

- si le serveur recoit un segment deja valide, il renvoie a nouveau son ACK
- si le client recoit un ancien ACK, il l'ignore
- si un ACK du segment `FIN` est perdu, le serveur peut re-ACKer le `FIN`

Cela evite :

- de reecrire plusieurs fois les memes donnees
- de bloquer sur un doublon
- de recommencer un transfert inutilement

## Journalisation / affichage

Le client et le serveur affichent les details des echanges :

- messages `OPEN`, `LS`, `DATA`, `ACK`, `BYE`, `RESUME`
- numeros de sequence
- tailles des segments
- retransmissions
- ACK recus

Exemple client :

```text
[SEND] DATA seq=12 taille=1024 vers 127.0.0.1:4242 (tentative 1)
[RECV] type=5 seq=0 ack=12 taille=0
[ACK] confirmation recue pour le segment 12
```

Exemple serveur :

```text
[RECV] DATA seq=12 depuis ('127.0.0.1', 54321) (1024 octets)
[SEND] ACK 12 vers ('127.0.0.1', 54321)
```

## Verification d'integrite

Apres un transfert, il est possible de comparer le hash du fichier source et du
fichier recu.

Exemple :

```powershell
certutil -hashfile .\test_300k.bin SHA256
certutil -hashfile .\uploads\test_300k.bin SHA256
```

Les deux empreintes doivent etre identiques.

## Exemple de tests

### Test simple

```text
open 127.0.0.1
ls
put test_upload.txt
bye
```

### Test gros fichier (>= 200 Kio)

Creation d'un fichier de 300 Kio :

```powershell
fsutil file createnew test_300k.bin 307200
```

Puis :

```text
open 127.0.0.1
put test_300k.bin
```

### Test de reprise

1. commencer un televersement
2. interrompre le client ou le serveur
3. relancer les programmes
4. executer :

```text
open 127.0.0.1
resume test_300k.bin
```

## Points forts du projet

- protocole applicatif propre au-dessus de UDP
- detection de corruption
- retransmissions avec timeout
- gestion des doublons
- ACK du segment final
- negotiation `MSS / window_size`
- transfert de gros fichiers
- reprise de transfert
- persistance d'etat client
- persistence implicite cote serveur via fichier partiel sur disque

## Limitations actuelles

- le fenetrage negocie est transporte, mais le transfert effectif reste en
  `stop-and-wait`
- il n'y a pas encore de commande `get`
- le serveur accepte un seul flux logique par adresse source a la fois
- en cas de reseau tres degrade, il peut etre necessaire d'augmenter
  `max_reprises`

## Ameliorations possibles

- implementer un vrai fenetrage glissant (`window_size > 1`)
- ajouter `get nom_de_fichier`
- ajouter une barre de progression pour les gros fichiers
- ajouter des tests automatises supplementaires
- journaliser les transferts dans un fichier log

## Resume

Ce projet montre comment construire un protocole fiable au-dessus de UDP non
fiable en ajoutant :

- segmentation
- ACK
- retransmission
- checksum
- reprise sur interruption
- ecriture reelle sur disque

Le resultat est un systeme client/serveur fonctionnel capable de transferer des
fichiers de petite et grande taille dans un environnement reseau degrade.
