"""Aide commune aux tests unitaires, v2 (reprend aide_tests_v1) : + chemin_version(nom, v), qui trouve une version adoptée
(outils/<nom>/ ou archive/) ou encore en chantier (outils/<nom>/candidat/) ; + importer_version(nom, v) ; + chemin(cle, …) et
chemins() du registre central des dossiers (cc_lib_v4) : un test ne doit jamais écrire un nom de dossier de l'espace en dur."""
import os, importlib.util
from aide_tests_v1 import dossier_essai, chemin_outil, importer, TESTS, RACINE_CC, OUTILS   # noqa: F401
from cc_lib_v4 import chemin, chemins                                                        # noqa: F401


def chemin_version(nom, v, ext='py'):
    try: return chemin_outil(nom, v, ext)
    except SystemExit:
        f = os.path.join(OUTILS, nom, 'candidat', f'{nom}_v{v}.{ext}')
        if os.path.exists(f): return f
        raise


def importer_version(nom, v, alias=None):
    """Charge le module d'une version donnée (adoptée ou en chantier) sous un nom propre au test."""
    s = importlib.util.spec_from_file_location(alias or f'{nom}_v{v}_essai', chemin_version(nom, v)); m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m); return m
