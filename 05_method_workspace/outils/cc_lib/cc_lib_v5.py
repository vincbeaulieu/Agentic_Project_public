"""
OUTIL: cc_lib
VERSION: 5
RESUME: Bibliothèque commune (reprend toute cc_lib_v4, donc v3, v2 et v1) ; v5 : la racine de l'espace se trouve d'elle-même et toute racine fausse échoue bruyamment — RACINE_CC est le premier dossier parent qui porte le marqueur de l'espace (outils/_gestion/, registre central) ; si aucun parent ne le porte, ou si la chaîne v1→v4 a été chargée hors raccourci et donne une autre racine (cas du 16 oct. 2026 : bibliothèque importée depuis outils/cc_lib/archive, racine = outils/cc_lib, « 0 délégation » sans erreur), l'import lève ImportError avec la marche à suivre.
USAGE: from cc_lib_v5 import chemin, chemins, evenement, racine_espace, verifier_racine, analyser_nom, version_attendue, chemin_outil, importer   (comme cc_lib_v4)
ENTREES: outils/_gestion/chemins_vN.json (registre des dossiers, comme v4) ; le dossier outils/_gestion/ sert aussi de marqueur de la racine
SORTIES: -
CATEGORIE: bibliotheque
BANC: tests/test_cc_lib_v5.py
REMPLACE: cc_lib_v4 (racine calculée par dirname(dirname(__file__)) dans cc_lib_v1 : fausse dès que la bibliothèque est rangée dans outils/cc_lib/ ou archive/ et importée sans le raccourci de compatibilité, qui la corrigeait après coup ; l'erreur restait silencieuse — dossiers introuvables, listes vides) ; v4 : cc_lib_v3 (noms de dossiers écrits en dur) ; v3 : cc_lib_v2 (« -revN » non reconnu, version des livrables non calculée)
"""
import os, json, hashlib, datetime
MARQUEUR = os.path.join('outils', '_gestion')   # présent à la racine de l'espace, dans le cloud comme sur le PC


def racine_espace(depart):
    """Premier dossier (depart compris, en remontant) qui contient outils/_gestion/ ; ImportError si aucun."""
    d = os.path.abspath(depart)
    while True:
        if os.path.isdir(os.path.join(d, MARQUEUR)): return d
        p = os.path.dirname(d)
        if p == d: raise ImportError(f'cc_lib_v5 : racine de l’espace introuvable en remontant depuis {depart} (aucun dossier parent ne contient {MARQUEUR}/)')
        d = p


def verifier_racine(r):
    """Lève ImportError si r ne porte pas le marqueur de l'espace ; rend r."""
    if not os.path.isdir(os.path.join(r, MARQUEUR)):
        raise ImportError(f'cc_lib_v5 : {r} n’est pas la racine de l’espace (pas de {MARQUEUR}/) ; appeler les outils par outils/<outil>.py, jamais en ajoutant outils/<outil>/ ou archive/ au chemin de recherche')
    return r


_RACINE = racine_espace(os.path.dirname(os.path.abspath(__file__)))
import cc_lib_v4 as _v4                            # chaîne v4 → v1 (par les raccourcis de compatibilité de outils/_compat)
from cc_lib_v4 import *                            # noqa : toutes les fonctions précédentes (y compris le RACINE_CC de v1, remplacé ci-dessous)
from cc_lib_v4 import analyser_nom, version_livrable, version_attendue, chemin_outil, importer, courant, registre, CLES, DEFAUT   # noqa: F401
RACINE_CC = _RACINE                                # après l'import * : sinon la racine de la chaîne v1 écraserait celle de v5
if os.path.abspath(_v4.RACINE_CC) != RACINE_CC:
    raise ImportError(f'cc_lib_v5 : la chaîne cc_lib_v4 → v1 a été chargée hors raccourci et donne la racine {_v4.RACINE_CC} au lieu de {RACINE_CC} ; '
                      'appeler les outils par outils/<outil>.py (ou importer par outils/_compat), jamais en ajoutant outils/cc_lib/ ou archive/ à PYTHONPATH')


def chemins(racine=None):
    """Comme cc_lib_v4.chemins, à partir de la racine vérifiée de v5."""
    return _v4.chemins(racine or RACINE_CC)


def chemin(cle, *parties, racine=None):
    """Comme cc_lib_v4.chemin, à partir de la racine vérifiée de v5."""
    r = racine or RACINE_CC
    return os.path.join(r, chemins(r).get(cle, cle), *parties)


def evenement(outil, version, type_, donnees):
    """Comme cc_lib_v4.evenement, dans le dossier du journal de la racine vérifiée de v5."""
    now = datetime.datetime.now(datetime.timezone.utc)
    jour = chemin('journal', now.strftime('%Y-%m-%d')); os.makedirs(jour, exist_ok=True)
    if os.environ.get('CC_BANC'): donnees = dict(donnees, banc=True)
    corps = dict(date=now.strftime('%Y-%m-%dT%H:%M:%SZ'), outil=outil, version=version, type=type_, donnees=donnees)
    brut = json.dumps(corps, ensure_ascii=False, sort_keys=True, default=str)
    f = os.path.join(jour, f"{now.strftime('%Y%m%d_%H%M%S')}_{outil}_v{version}_{hashlib.sha256(brut.encode()).hexdigest()[:8]}.json")
    if os.path.exists(f): return f
    with open(f, 'x', encoding='utf-8') as g: g.write(brut)
    return f
