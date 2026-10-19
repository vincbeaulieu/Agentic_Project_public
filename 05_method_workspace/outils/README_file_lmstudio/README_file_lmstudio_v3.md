# File de micro-tâches LM Studio — README (v3, 15 oct. 2026)

Ce dossier (`Revision\00_espace_cloud_claude\file_lmstudio\`) est une file d'attente :
- Claude y dépose des micro-tâches ;
- un ouvrier Windows les fait traiter par les modèles locaux de LM Studio ;
- les résultats reviennent en fichiers, sans transiter par la conversation.

## 1. Fonctionnement de l'ouvrier (`outil\worker_lmstudio_v3.ps1`)

Un seul processus PowerShell. Il ne demande ni installation ni droits d'administrateur, et ne touche à aucun réglage du système. Il boucle sur ces étapes :

1. **Écoute** sa page de gestion sur `http://127.0.0.1:8770/` : votre machine seulement, invisible du réseau.
2. **Regarde `entree\`** toutes les 2 s. Il prend chaque nouveau lot (`*.jsonl`) et le déplace vers `encours\`.
3. **Choisit la tâche suivante.** La priorité va de 0 (urgent) à 3 (fond) ; une tâche gagne une classe par 10 min d'attente, ce qui évite la famine. Il préfère le modèle déjà chargé, pour éviter de recharger LM Studio.
4. **Envoie la tâche à LM Studio** (`127.0.0.1:1234`), une seule à la fois, sans proxy. L'appel est asynchrone : pendant qu'il attend, la page de gestion répond, et un arrêt annule l'appel sur-le-champ.
5. **Écrit la réponse** en fin de `sortie\<lot>_resultats.jsonl` et l'état dans `journal\etat.json`. Le lot terminé passe dans `traite\`. Rien n'est jamais supprimé.

Ce que le script ne fait pas :
- il n'accède à aucun autre dossier ;
- il n'appelle aucune autre adresse que LM Studio ;
- il ne démarre pas tout seul après un redémarrage du PC ;
- il ne lance aucun autre programme.

## 2. Arrêter l'ouvrier (de la plus sûre à la plus simple)

| Moyen | Effet |
|---|---|
| **Le PC gèle ou redémarre** | Rien ne repart seul : l'ouvrier n'est ni un service ni une tâche planifiée. Au prochain lancement, il reprend sans refaire ce qui est fait. |
| **Arrêter le serveur LM Studio** (bouton *Stop* de l'onglet *Developer*, ou quitter LM Studio) | Le GPU est libéré tout de suite. L'ouvrier constate l'interruption, attend 3 min, puis s'arrête seul (code 2). |
| **Page de gestion** `http://127.0.0.1:8770/` : *Pause*, *Reprendre*, *Arrêter* | *Arrêter* annule l'appel en cours. La tâche reste en file. |
| **Fermer la fenêtre** de l'ouvrier, ou Ctrl+C | Arrêt immédiat. La tâche en cours est refaite au prochain lancement. |
| **Fichier `ARRET`** dans `file_lmstudio\` | Arrêt propre au plus tard 1 s après. |
| **Gestionnaire des tâches** : « Windows PowerShell » → Fin de tâche | En dernier recours. |

L'ouvrier s'arrête aussi seul quand la file reste vide 30 min (code 3).

## 3. Garde-fous contre le gel du PC

- **Une seule requête à la fois**, avec une courte pause entre deux tâches.
- **Délai de 180 s par appel.** Au-delà, l'appel est annulé, puis réessayé au plus 3 fois.
- **Pause automatique de 60 s** si la mémoire libre passe sous 1,5 Go.
- **Priorité « en dessous de la normale »** pour le processus de l'ouvrier.
- **Côté LM Studio** (conseillé) : activer le déchargement automatique des modèles inutilisés (*JIT TTL*), et garder une longueur de contexte modeste (4 096 à 8 192).

Les réglages se changent sans toucher au script, dans un fichier facultatif `config_worker.json` :

```
{"port": 8770, "delai_tache_s": 180, "arret_si_lmstudio_absent_min": 3, "arret_si_inactif_min": 30, "memoire_libre_min_mo": 1500, "pause_entre_taches_ms": 100}
```

## 4. API locale de gestion

| Requête | Effet |
|---|---|
| `GET /` | Page de gestion : statut toutes les 2 s, boutons |
| `GET /etat` | État en JSON : statut, traitées, erreurs, en attente, tâche en cours, modèle, LM Studio joignable |
| `POST /pause`, `POST /reprendre`, `POST /arreter` | Commandes |

Les commandes venant d'une autre page web sont refusées (contrôle de l'en-tête `Origin`). Claude peut lire la page de gestion par son navigateur intégré.

## 5. Démarrer

1. Ouvrez LM Studio et démarrez son serveur local (port 1234).
2. Double-cliquez `outil\lancer_worker_lmstudio_v3.cmd`.
3. Ouvrez `http://127.0.0.1:8770/` pour suivre le travail.

À l'arrêt, la fenêtre affiche le code de sortie :
- 0 : arrêt demandé ;
- 2 : LM Studio interrompu ;
- 3 : file vide ;
- 4 : port déjà pris (un ouvrier tourne déjà).

## 6. Dossiers et formats

| Dossier | Contenu |
|---|---|
| `entree\` | Lots déposés par Claude : `<lot>_vN.jsonl`, une tâche par ligne |
| `encours\` | Lots pris en charge |
| `traite\` | Lots terminés (déplacés, jamais supprimés) |
| `sortie\` | Résultats `<lot>_resultats.jsonl`, avec ajout ligne à ligne |
| `consignes\` | Consignes nommées (`MT-PRESENCE_v1.txt`…), citées par les tâches |
| `journal\` | `etat.json`, `worker.log` |
| `outil\` | Ouvrier et lanceur. Les versions précédentes restent pour l'historique ; seule la dernière est à lancer. |

**Une tâche** : `{"id", "prio", "modele", "consigne", "u", "valeurs": [...], "max_tokens"}`. Avec `"type": "embedding"`, elle demande un vecteur.

**Un résultat** : `{"id", "modele", "r", "ms", "tokens", "essai", "fin"}`, ou `"erreur"`.

**Réglages des appels** : température 0, réflexion coupée (`reasoning_effort: none`), réponse JSON limitée aux valeurs permises.

## 7. Côté Claude

`00_competences_claude\outils\file_lmstudio_vN.py` dépose et récolte (`installer`, `deposer`, `deposer-embeddings`, `recolter`).

Les résultats sont :
- combinés aux règles déterministes ;
- mesurés au banc avant tout usage ;
- versés au répertoire d'entraînement des classifieurs que Claude développe (`00_competences_claude\entrainement\`), comme étiquettes « argent » et embeddings.
