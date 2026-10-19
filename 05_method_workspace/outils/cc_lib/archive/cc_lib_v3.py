"""
OUTIL: cc_lib
VERSION: 3
RESUME: Bibliothèque commune (reprend toute cc_lib_v2, qui reprend cc_lib_v1) ; v3 : noms de fichiers à qualificatif de passe de révision « -revN » (Rapport_v6.0.4-rev1.docx) reconnus par analyser_nom (champ rev) ; version d'un livrable : règle ou décision de l'utilisateur propre au document, consignée dans le TRAVAIL du dossier (decision_version), sinon convention générale v(X+1).0.0 (version_livrable, version_attendue).
USAGE: from cc_lib_v3 import analyser_nom, version_livrable, version_attendue, courant, chemin_outil, importer
ENTREES: outils/registre_outils_vN.json (ranger_outils)
SORTIES: -
CATEGORIE: bibliotheque
BANC: tests/test_cc_lib_v3.py
REMPLACE: cc_lib_v2 (« -revN » non reconnu : N1 « sans version » sur Rapport_v6.0.4-rev1.docx ; version des livrables ni calculée ni reliée à une décision de l'utilisateur, choisie à la main comme « prochain majeur libre », hors convention) ; v2 : cc_lib_v1 (+ registre des outils)
"""
import os, sys, re, json, glob, importlib
from cc_lib_v1 import *                      # noqa : fonctions communes inchangées (empreintes, journal, versions…)
from cc_lib_v1 import RACINE_CC, derniere_version
import cc_lib_v1 as _v1
RE_VERSION = re.compile(r'^(?P<nom>[^/\\]+)_v(?P<ver>\d+(?:\.\d+){0,2})(?P<qui>[ac])?(?P<rev>-rev\d+)?'
                        r'(?:_(?P<variante>[A-Za-z0-9][A-Za-z0-9\-]*(?:_[A-Za-z0-9][A-Za-z0-9\-]*)*))?\.(?P<ext>[A-Za-z0-9]+)$')


def analyser_nom(fichier):
    """Comme cc_lib_v1.analyser_nom, avec le qualificatif de passe « -revN » (champ rev, None sinon)."""
    m = RE_VERSION.match(fichier)
    if m:
        d = m.groupdict(); d['forme'] = 'semver' if d['ver'].count('.') == 2 else 'entier' if '.' not in d['ver'] else 'xy'
        return d
    d = _v1.analyser_nom(fichier)
    if d is not None: d.setdefault('rev', None)
    return d


def version_livrable(source):
    """Version par défaut d'un livrable d'après le nom de sa source (CLAUDE.md : « dans les livrables, toujours monter à
    v(X+1).0.0, X = version initiale »). Une règle propre à un document (par exemple le rapport : source v6.0.4-rev1 →
    v6.0.5-rev1) n'est pas une convention d'outil : elle est consignée dans le TRAVAIL du dossier (decision_version). None si illisible."""
    d = analyser_nom(os.path.basename(str(source or '')))
    if not d or d['forme'] == 'horodatage': return None
    return f"{int(d['ver'].split('.')[0]) + 1}.0.0"


def version_attendue(travail):
    """Version des livrables d'un dossier : règle ou décision de l'utilisateur propre au document, consignée dans TRAVAIL
    (decision_version : valeur, approuvee_par = « utilisateur », portee, citations), sinon version_livrable(source).
    Retourne (version, origine)."""
    dv = (travail or {}).get('decision_version') or {}
    if dv.get('approuvee_par') == 'utilisateur' and dv.get('valeur'): return str(dv['valeur']), 'decision'
    return version_livrable((travail or {}).get('source')), 'convention'
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
