"""
OUTIL: cc_lib
VERSION: 4
RESUME: Bibliothèque commune (reprend toute cc_lib_v3, donc v2 et v1) ; v4 : registre central des dossiers de l'espace de compétences — chaque outil désigne un dossier par sa clé logique (« lecons », « journal », « tests »…) et obtient son nom réel par chemin(cle, …) d'après la dernière version de outils/_gestion/chemins_vN.json ; renommer un dossier ne demande alors que de mettre à jour ce registre (et de rejouer le déplacement), sans nouvelle version des outils ; evenement() écrit dans le dossier du journal ainsi désigné.
USAGE: from cc_lib_v4 import chemin, chemins, evenement, analyser_nom, version_attendue, chemin_outil, importer   (chemin('lecons', 'LC-001_v1.json'))
ENTREES: outils/_gestion/chemins_vN.json {"chemins": {cle: dossier relatif à 00_competences_claude}} (facultatif : sans registre, le dossier porte le nom de la clé)
SORTIES: -
CATEGORIE: bibliotheque
BANC: tests/test_cc_lib_v4.py
REMPLACE: cc_lib_v3 (noms de dossiers écrits en dur dans chaque outil : un renommage aurait demandé une nouvelle version de chaque outil qui les cite) ; v3 : cc_lib_v2 (« -revN » non reconnu, version des livrables non calculée)
"""
import os, re, json, glob, hashlib, datetime
from cc_lib_v3 import *                      # noqa : toutes les fonctions précédentes
from cc_lib_v3 import RACINE_CC, analyser_nom, version_livrable, version_attendue, chemin_outil, importer, courant, registre   # noqa: F401
CLES = ('bancs', 'catalogue', 'delegations', 'entrainement', 'guides', 'journal', 'lecons', 'memoire', 'outils', 'procedures',
        'propositions', 'regles', 'revues', 'skills_atelier', 'skills_ressources', 'taches', 'tests')
DEFAUT = dict({k: k for k in CLES}, propositions='propositions_a_reviser', skills_atelier='skills_propositions', skills_ressources='skills_ressources_par_skill')


def _num(f):
    m = re.search(r'_v(\d+)\.json$', f); return int(m.group(1)) if m else -1


def chemins(racine=None):
    """{clé logique: dossier relatif} : valeurs par défaut, remplacées par la dernière version du registre outils/_gestion/chemins_vN.json."""
    r = racine or RACINE_CC; C = dict(DEFAUT)
    V = sorted(glob.glob(os.path.join(r, 'outils', '_gestion', 'chemins_v*.json')), key=_num)
    if V:
        with open(V[-1], encoding='utf-8') as g: C.update(json.load(g).get('chemins', {}))
    return C


def chemin(cle, *parties, racine=None):
    """Chemin absolu d'un dossier de l'espace désigné par sa clé logique (clé inconnue : prise comme nom de dossier)."""
    r = racine or RACINE_CC
    return os.path.join(r, chemins(r).get(cle, cle), *parties)


def evenement(outil, version, type_, donnees):
    """Comme cc_lib_v1.evenement, dans le dossier du journal désigné par le registre des chemins."""
    now = datetime.datetime.now(datetime.timezone.utc)
    jour = chemin('journal', now.strftime('%Y-%m-%d')); os.makedirs(jour, exist_ok=True)
    if os.environ.get('CC_BANC'): donnees = dict(donnees, banc=True)
    corps = dict(date=now.strftime('%Y-%m-%dT%H:%M:%SZ'), outil=outil, version=version, type=type_, donnees=donnees)
    brut = json.dumps(corps, ensure_ascii=False, sort_keys=True, default=str)
    f = os.path.join(jour, f"{now.strftime('%Y%m%d_%H%M%S')}_{outil}_v{version}_{hashlib.sha256(brut.encode()).hexdigest()[:8]}.json")
    if os.path.exists(f): return f
    with open(f, 'x', encoding='utf-8') as g: g.write(brut)
    return f
