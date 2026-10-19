"""
OUTIL: _raccourci
VERSION: 3
RESUME: Moteur des raccourcis du dossier principal outils/ : un raccourci (fichier de contenu constant, généré une fois) exécute ou importe la version courante d'un outil, c'est-à-dire l'unique version présente dans outils/<outil>/ (les autres sont dans outils/<outil>/archive/) ; les raccourcis versionnés de outils/_compat/ chargent une version précise, où qu'elle soit rangée, pour que les anciens imports « <outil>_vN » fonctionnent encore ; correctifs de compatibilité des anciennes bibliothèques (racine de l'espace, registre).
USAGE: (interne) depuis un raccourci : from _raccourci_v3 import charger ; charger(__name__, '<outil>')   |   charger(__name__, '<outil>', version=N)
ENTREES: outils/<outil>/<outil>_vN.py, outils/<outil>/archive/<outil>_vK.py
SORTIES: module chargé (sys.modules) ou exécution comme programme principal
CATEGORIE: bibliotheque
BANC: tests/test_raccourci_v3.py
REMPLACE: _raccourci_v2 (journal des anciennes bibliothèques cc_lib_v1/v2 placé dans le dossier désigné par le registre central des chemins, outils/_gestion/chemins_vN.json, et non plus dans « journal » écrit en dur ; les brouillons de outils/<outil>/candidat/ ne sont jamais pris pour la version courante) ; v2 : _raccourci_v1 (+ PYTHONPATH propagé aux sous-processus : un outil lancé par un raccourci peut lancer d'autres outils, d'anciennes versions comprises, sans réglage) ; v1 : nouvelle organisation (un dossier par outil, archive par outil, raccourcis sans doublon)
"""
import os, re, sys, glob, runpy, importlib.util
OUTILS = os.path.dirname(os.path.abspath(__file__)); RACINE_CC = os.path.dirname(OUTILS)
for _p in (os.path.join(OUTILS, '_compat'), OUTILS):
    if _p not in sys.path: sys.path.insert(0, _p)
_pp = [p for p in os.environ.get('PYTHONPATH', '').split(os.pathsep) if p]
os.environ['PYTHONPATH'] = os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS] + [p for p in _pp if p not in (OUTILS, os.path.join(OUTILS, '_compat'))])


def versions(outil, ext='py'):
    """{version: chemin} : versions courantes (dossier de l'outil) et archivées."""
    V = {}
    for d, arch in ((os.path.join(OUTILS, outil), False), (os.path.join(OUTILS, outil, 'archive'), True)):
        for f in glob.glob(os.path.join(d, f'{outil}_v*.{ext}')):
            m = re.match(re.escape(outil) + r'_v(\d+)\.' + ext + '$', os.path.basename(f))
            if m: V.setdefault(int(m.group(1)), (f, arch))
    return V


def courante(outil, ext='py'):
    c = [(v, f) for v, (f, arch) in versions(outil, ext).items() if not arch]
    if not c: raise ImportError(f'aucune version courante de {outil} dans outils/{outil}/')
    return max(c)


def _dossier(cle):
    """Dossier de l'espace désigné par sa clé logique dans le registre central (dernière version de _gestion/chemins_vN.json)."""
    V = sorted(glob.glob(os.path.join(OUTILS, '_gestion', 'chemins_v*.json')), key=lambda f: int(re.search(r'_v(\d+)\.json$', f).group(1)))
    C = {}
    if V:
        import json
        with open(V[-1], encoding='utf-8') as g: C = json.load(g).get('chemins', {})
    return os.path.join(RACINE_CC, C.get(cle, cle))


def _correctifs(nom, m):
    """Anciennes bibliothèques chargées depuis leur nouveau rangement : racine de l'espace et registre corrigés."""
    if nom.startswith('cc_lib_v') and hasattr(m, 'RACINE_CC'):
        m.RACINE_CC = RACINE_CC; m.JOURNAL = _dossier('journal')
        if hasattr(m, 'OUTILS'): m.OUTILS = OUTILS
        if nom != 'cc_lib_v1' and hasattr(m, 'chemin_outil'):
            for f in ('courant', 'chemin_outil', 'importer', 'registre'):
                setattr(m, f, getattr(sys.modules[__name__], f))


def _charger_module(nom, chemin):
    if nom in sys.modules and getattr(sys.modules[nom], '__file__', None) == chemin: return sys.modules[nom]
    s = importlib.util.spec_from_file_location(nom, chemin); m = importlib.util.module_from_spec(s)
    sys.modules[nom] = m; s.loader.exec_module(m); _correctifs(nom, m); return m


def charger(appelant, outil, version=None):
    """Depuis un raccourci : exécute (appelant == '__main__') ou importe la version courante (ou la version donnée)."""
    if version is None: version, chemin = courante(outil)
    else:
        V = versions(outil)
        if version not in V: raise ImportError(f'{outil}_v{version}.py introuvable (outils/{outil}/ ni archive/)')
        chemin = V[version][0]
    if appelant == '__main__':
        sys.argv[0] = chemin; d = os.path.dirname(chemin)
        if d not in sys.path: sys.path.insert(0, d)
        runpy.run_path(chemin, run_name='__main__'); return None
    m = _charger_module(f'{outil}_v{version}', chemin); sys.modules[appelant] = m; return m


# --- accès aux outils pour les bibliothèques et les tests (même logique que les raccourcis)
def courant(nom): return courante(nom)[0]
def chemin_outil(nom, version=None, ext='py'):
    if version is None: return courante(nom, ext)[1]
    V = versions(nom, ext)
    if int(version) not in V: raise SystemExit(f'{nom}_v{version}.{ext} introuvable')
    return V[int(version)][0]
def importer(nom, version=None):
    v = version or courant(nom); return _charger_module(f'{nom}_v{v}', chemin_outil(nom, v))
def registre():
    import json
    f = sorted(glob.glob(os.path.join(OUTILS, '_gestion', 'registre_outils_v*.json')), key=lambda x: int(re.search(r'_v(\d+)\.json$', x).group(1)))
    return json.load(open(f[-1], encoding='utf-8'))['outils'] if f else {}
