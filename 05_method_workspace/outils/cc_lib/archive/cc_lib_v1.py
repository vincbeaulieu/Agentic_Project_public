"""
OUTIL: cc_lib
VERSION: 1
RESUME: Bibliothèque commune de l'espace de compétences : empreintes, analyse des noms et versions, exemptions, en-têtes d'outils, journal d'apprentissage immuable, écriture versionnée sans écrasement.
USAGE: from cc_lib_v1 import h16, analyser_nom, est_exempt, evenement, lire_entete, ecrire_versionne
ENTREES: -
SORTIES: -
CATEGORIE: bibliotheque
BANC: -
REMPLACE: -
"""
import os, re, json, hashlib, datetime, socket

RACINE_CC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../00_competences_claude
JOURNAL = os.path.join(RACINE_CC, 'journal')

# ---------- empreintes
def h16(chemin):
    h = hashlib.sha256()
    with open(chemin, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()[:16]

def sha256(chemin):
    h = hashlib.sha256()
    with open(chemin, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()

# ---------- noms et versions (règles N1 à N5)
# nom_vN.ext | Nom_vX.Y.Z[a|c][_variante].ext | nom_AAAAMMJJ_HHMM[SS].ext (horodatage = version)
RE_VERSION = re.compile(
    r'^(?P<nom>[^/\\]+)_v(?P<ver>\d+(?:\.\d+){0,2})(?P<qui>[ac])?'
    r'(?:_(?P<variante>[A-Za-z0-9][A-Za-z0-9\-]*(?:_[A-Za-z0-9][A-Za-z0-9\-]*)*))?\.(?P<ext>[A-Za-z0-9]+)$')
# nom gourmand : la version d'un fichier est le DERNIER jeton _v<n> (plan_v8_fusion_v5.py -> version 5)
RE_HORODATE = re.compile(r'^(?P<nom>[^/\\]+?)_(?P<ts>\d{8}_\d{4}(?:\d{2})?)(?:_(?P<variante>[A-Za-z0-9_\-]+))?\.(?P<ext>[A-Za-z0-9]+)$')
RE_SANS_ACCENT = re.compile(r'^[A-Za-z0-9_.\-]+$')

def analyser_nom(fichier):
    """Retourne dict(nom, ver, qui, variante, ext, forme) ou None si le nom ne porte pas de version."""
    m = RE_VERSION.match(fichier)
    if m:
        d = m.groupdict(); d['forme'] = 'semver' if d['ver'].count('.') == 2 else 'entier' if '.' not in d['ver'] else 'xy'
        return d
    m = RE_HORODATE.match(fichier)
    if m:
        d = m.groupdict(); d.update(ver=d.pop('ts'), qui=None, forme='horodatage'); return d
    return None

def version_tuple(ver):
    return tuple(int(x) for x in re.split(r'[._]', ver) if x.isdigit())

# ---------- exemptions (dossiers techniques et jetables, caches)
DOSSIERS_EXEMPTS = re.compile(r'^(00_sources|essais|_essais.*|_verif.*|_rendu.*|_profil.*|__pycache__|\.config|\.cache|_copie_cloud.*|_test.*|journal|bancs|e\d+)$')
FICHIERS_EXEMPTS = re.compile(r'^(__init__\.py|\.DS_Store|~\$.*|\.~lock.*)$')

def est_exempt(chemin_relatif):
    parts = chemin_relatif.replace('\\', '/').split('/')
    if any(DOSSIERS_EXEMPTS.match(p) for p in parts[:-1]): return True
    return bool(FICHIERS_EXEMPTS.match(parts[-1]))

# ---------- en-têtes d'outils (catalogue)
CHAMPS_ENTETE = ('OUTIL', 'VERSION', 'RESUME', 'USAGE', 'ENTREES', 'SORTIES', 'CATEGORIE', 'BANC', 'REMPLACE')
def lire_entete(chemin):
    """Lit le bloc d'en-tête « CLE: valeur » du docstring de tête d'un script Python. Retourne dict (vide si absent)."""
    try: src = open(chemin, encoding='utf-8').read(8000)
    except Exception: return {}
    m = re.match(r'\s*(?:#![^\n]*\n)?\s*[rRuU]?"""(.*?)"""', src, re.S)
    if not m: return {}
    d = {}
    for ligne in m.group(1).splitlines():
        mm = re.match(r'^([A-Z_]{4,}):\s*(.*)$', ligne.strip())
        if mm and mm.group(1) in CHAMPS_ENTETE: d[mm.group(1)] = mm.group(2).strip()
    return d

# ---------- journal d'apprentissage : un fichier immuable par événement
def evenement(outil, version, type_, donnees):
    now = datetime.datetime.now(datetime.timezone.utc)
    jour = os.path.join(JOURNAL, now.strftime('%Y-%m-%d')); os.makedirs(jour, exist_ok=True)
    if os.environ.get('CC_BANC'): donnees = dict(donnees, banc=True)   # exécution sous banc d'essai
    corps = dict(date=now.strftime('%Y-%m-%dT%H:%M:%SZ'), outil=outil, version=version, type=type_, donnees=donnees)
    brut = json.dumps(corps, ensure_ascii=False, sort_keys=True, default=str)
    nom = f"{now.strftime('%Y%m%d_%H%M%S')}_{outil}_v{version}_{hashlib.sha256(brut.encode()).hexdigest()[:8]}.json"
    chemin = os.path.join(jour, nom)
    if os.path.exists(chemin): return chemin
    with open(chemin, 'x', encoding='utf-8') as f: f.write(brut)
    return chemin

# ---------- écriture versionnée : nouvelle version seulement si le contenu change
def ecrire_versionne(dossier, base, ext, contenu):
    """Écrit <base>_v<N>.<ext> avec N = dernière version + 1, sauf si la dernière version a déjà ce contenu.
    Retourne (chemin, cree:bool). Ne réécrit jamais un fichier existant."""
    os.makedirs(dossier, exist_ok=True)
    rx = re.compile(r'^' + re.escape(base) + r'_v(\d+)\.' + re.escape(ext) + r'$')
    vers = sorted((int(m.group(1)), f) for f in os.listdir(dossier) for m in [rx.match(f)] if m)
    data = contenu.encode('utf-8') if isinstance(contenu, str) else contenu
    if vers:
        dern = os.path.join(dossier, vers[-1][1])
        if open(dern, 'rb').read() == data: return dern, False
    n = (vers[-1][0] + 1) if vers else 1
    chemin = os.path.join(dossier, f'{base}_v{n}.{ext}')
    with open(chemin, 'xb') as f: f.write(data)
    return chemin, True

def derniere_version(dossier, base, ext):
    rx = re.compile(r'^' + re.escape(base) + r'_v(\d+)\.' + re.escape(ext) + r'$')
    vers = sorted((int(m.group(1)), f) for f in os.listdir(dossier) for m in [rx.match(f)] if m) if os.path.isdir(dossier) else []
    return os.path.join(dossier, vers[-1][1]) if vers else None
