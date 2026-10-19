# Compatibilité : l'ancien moteur des raccourcis _raccourci_v2 est rangé dans _raccourci/archive/ ; les anciennes versions
# d'outils qui l'importent par son nom (« import _raccourci_v2 ») reçoivent le moteur courant, de même interface.
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _raccourci_v3 import *                                   # noqa: F401,F403
from _raccourci_v3 import charger, courante, versions, chemin_outil, importer, registre, courant   # noqa: F401
