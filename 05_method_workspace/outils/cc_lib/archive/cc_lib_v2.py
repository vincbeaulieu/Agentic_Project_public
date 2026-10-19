"""
OUTIL: cc_lib
VERSION: 2
RESUME: Bibliothèque commune (reprend toute cc_lib_v1) + accès aux outils par le registre : version courante d'un outil, chemin d'une version (outils/ ou outils/archive/<outil>/), import de la version courante ou d'une version donnée ; les nouveaux outils dépendent ainsi de « la version courante » plutôt que d'un numéro figé.
USAGE: from cc_lib_v2 import courant, chemin_outil, importer   (puis : DR = importer('detecteurs_rapport'))
ENTREES: outils/registre_outils_vN.json (ranger_outils)
SORTIES: -
CATEGORIE: bibliotheque
BANC: -
REMPLACE: cc_lib_v1 (+ registre des outils ; cc_lib_v1 reste importée telle quelle)
"""
import os, sys, json, glob, importlib
from cc_lib_v1 import *                      # noqa : fonctions communes inchangées (empreintes, journal, versions…)
from cc_lib_v1 import RACINE_CC, derniere_version
OUTILS = os.path.join(RACINE_CC, 'outils'); ARCHIVE = os.path.join(OUTILS, 'archive')


def registre():
    f = derniere_version(OUTILS, 'registre_outils', 'json')
    return json.load(open(f, encoding='utf-8'))['outils'] if f else {}


def courant(nom):
    """Version courante (adoptée) d'un outil d'après le registre ; à défaut, la plus haute présente dans outils/."""
    R = registre()
    if nom in R and R[nom].get('courant'): return int(R[nom]['courant'])
    v = [int(os.path.basename(f)[len(nom) + 2:].split('.')[0]) for f in glob.glob(os.path.join(OUTILS, f'{nom}_v*.*'))
         if os.path.basename(f)[len(nom) + 2:].split('.')[0].isdigit()]
    if not v: raise SystemExit(f'outil inconnu : {nom}')
    return max(v)


def chemin_outil(nom, version=None, ext='py'):
    v = version or courant(nom)
    for d in (OUTILS, os.path.join(ARCHIVE, nom)):
        f = os.path.join(d, f'{nom}_v{v}.{ext}')
        if os.path.exists(f): return f
    raise SystemExit(f'{nom}_v{v}.{ext} introuvable (outils/ ni archive/{nom}/)')


def importer(nom, version=None):
    f = chemin_outil(nom, version); d = os.path.dirname(f)
    if d not in sys.path: sys.path.insert(0, d)
    return importlib.import_module(os.path.basename(f)[:-3])
