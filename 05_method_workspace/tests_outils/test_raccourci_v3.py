"""Tests du moteur _raccourci_v3 : la version courante ignore les brouillons de candidat/ ; le dossier d'une clé vient du
registre central des chemins (journal des anciennes bibliothèques) ; versions archivées retrouvées. (Le changement de moteur
et le journal des anciennes bibliothèques sont aussi testés dans test_organiser_outils_v7.)"""
import os, sys, json, shutil, unittest, importlib.util
from aide_tests_v2 import dossier_essai, OUTILS


def moteur_dans(rc):
    o = os.path.join(rc, 'outils'); os.makedirs(os.path.join(o, '_gestion'), exist_ok=True); shutil.copy(os.path.join(OUTILS, '_raccourci_v3.py'), o)
    s = importlib.util.spec_from_file_location(f'moteur_essai_{os.path.basename(rc)}', os.path.join(o, '_raccourci_v3.py')); m = importlib.util.module_from_spec(s)
    chemins = list(sys.path); s.loader.exec_module(m); sys.path[:] = chemins; return m, o


class Moteur(unittest.TestCase):
    def test_candidat_ignore_et_archive(self):
        m, o = moteur_dans(dossier_essai('moteur3'))
        for rel in ('x/x_v2.py', 'x/archive/x_v1.py', 'x/candidat/x_v3.py'):
            os.makedirs(os.path.dirname(os.path.join(o, rel)), exist_ok=True); open(os.path.join(o, rel), 'w').close()
        self.assertEqual(m.courante('x')[0], 2); self.assertEqual(sorted(m.versions('x')), [1, 2])

    def test_dossier_du_registre(self):
        rc = dossier_essai('moteur3_registre'); m, o = moteur_dans(rc)
        self.assertEqual(m._dossier('journal'), os.path.join(rc, 'journal'))
        with open(os.path.join(o, '_gestion', 'chemins_v1.json'), 'w', encoding='utf-8') as g: json.dump(dict(chemins=dict(journal='journal_des_evenements')), g)
        self.assertEqual(m._dossier('journal'), os.path.join(rc, 'journal_des_evenements'))


if __name__ == '__main__':
    unittest.main()
