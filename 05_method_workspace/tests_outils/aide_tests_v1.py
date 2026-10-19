"""Aide commune aux tests unitaires (stdlib unittest, sans dépendance) : chemins, dossier d'essai unique sous
tests/_test_execution/ (jamais d'espace temporaire hors du dossier de travail), import de la version courante d'un outil,
événements du journal marqués « banc » (CC_BANC)."""
import os, sys, datetime, itertools
TESTS = os.path.dirname(os.path.abspath(__file__)); RACINE_CC = os.path.dirname(TESTS); OUTILS = os.path.join(RACINE_CC, 'outils')
if OUTILS not in sys.path: sys.path.insert(0, OUTILS)
os.environ.setdefault('CC_BANC', 'tests')
_n = itertools.count()
from cc_lib_v2 import importer, chemin_outil   # noqa: E402


def dossier_essai(nom):
    d = os.path.join(TESTS, '_test_execution', datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f') + f'_{next(_n)}_{nom}')
    os.makedirs(d); return d
