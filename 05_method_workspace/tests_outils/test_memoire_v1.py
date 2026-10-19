"""Tests unitaires de memoire : une version non approuvée n'est jamais courante ; approbation avec citation obligatoire ; alerte si le texte approuvé change."""
import os, sys, io, contextlib, unittest
from aide_tests_v1 import importer, dossier_essai
M = importer('memoire')


def lancer(*a):
    sys.argv = ['memoire'] + list(a); out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try: M.main(); code = 0
        except SystemExit as e: code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue()


class Memoire(unittest.TestCase):
    def setUp(self):
        self.sauve = (M.D, M.ST); d = dossier_essai('memoire'); M.D, M.ST = d, os.path.join(d, 'statut')
        self.f = os.path.join(d, 'MEMOIRE_METHODOLOGIE_v1.md'); open(self.f, 'w').write('# v1\n')

    def tearDown(self): M.D, M.ST = self.sauve

    def test_cycle(self):
        self.assertEqual(lancer('courant')[0], 1)                 # rien d'approuvé
        lancer('proposer', self.f); self.assertEqual(lancer('courant')[0], 1)
        self.assertEqual(lancer('approuver', '1')[0] != 0, True)  # citation obligatoire
        lancer('approuver', '1', '--citation', 'oui, approuvé'); code, out = lancer('courant')
        self.assertEqual(code, 0); self.assertIn('MEMOIRE_METHODOLOGIE_v1.md', out)
        open(self.f, 'a').write('modifié\n'); self.assertEqual(lancer('courant')[0], 2)   # empreinte changée : alerte


if __name__ == '__main__':
    unittest.main()
