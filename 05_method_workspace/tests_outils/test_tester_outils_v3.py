"""Tests de tester_outils_v3 sur un espace fictif : le dossier des tests désigné par le registre central des chemins
(outils/_gestion/chemins_vN.json) est celui qui est lu et où le rapport est écrit ; une candidate rangée dans
outils/<outil>/candidat/ est testée par --candidat ; un test en échec rend le code de sortie non nul."""
import os, sys, json, glob, shutil, subprocess, unittest
from aide_tests_v2 import dossier_essai, OUTILS, chemin_version

ENT = '"""\nOUTIL: x\nVERSION: {v}\nRESUME: essai\nUSAGE: -\nENTREES: -\nSORTIES: -\nCATEGORIE: essai\nBANC: -\nREMPLACE: -\n"""\n'


def w(chemin, texte):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, 'w', encoding='utf-8') as g: g.write(texte)


def lancer(o, *a):
    r = subprocess.run([sys.executable] + list(a), capture_output=True, text=True, cwd=o, env=dict(os.environ, PYTHONPATH=''))
    return r.returncode, r.stdout + r.stderr


class Tester(unittest.TestCase):
    def setUp(self):
        self.rc = rc = dossier_essai('tester3'); self.o = o = os.path.join(rc, 'outils')
        os.makedirs(os.path.join(o, '_gestion')); shutil.copy(os.path.join(OUTILS, '_raccourci_v3.py'), o)
        os.makedirs(os.path.join(o, 'tester_outils')); shutil.copy(chemin_version('tester_outils', 3), os.path.join(o, 'tester_outils'))
        os.makedirs(os.path.join(o, 'organiser_outils')); shutil.copy(chemin_version('organiser_outils', 7), os.path.join(o, 'organiser_outils'))
        w(os.path.join(o, 'x', 'x_v1.py'), ENT.format(v=1) + 'VAL = 1\n')
        w(os.path.join(o, '_gestion', 'chemins_v1.json'), json.dumps(dict(chemins=dict(tests='tests_des_outils'))))
        self.t = os.path.join(rc, 'tests_des_outils')
        w(os.path.join(self.t, 'test_x_v1.py'), 'import unittest\nimport x\nclass T(unittest.TestCase):\n    def test_val(self): self.assertIn(x.VAL, (1, 2))\n')
        c, s = lancer(o, os.path.join('organiser_outils', 'organiser_outils_v7.py'), 'raccourcis'); assert c == 0, s

    def test_dossier_des_tests_du_registre(self):
        c, s = lancer(self.o, 'tester_outils.py'); self.assertEqual(c, 0, s); self.assertIn('conforme', s)
        self.assertTrue(glob.glob(os.path.join(self.t, 'rapports', 'rapport_tests_*.json')))
        self.assertFalse(os.path.exists(os.path.join(self.rc, 'tests')))

    def test_candidate_dans_candidat(self):
        w(os.path.join(self.o, 'x', 'candidat', 'x_v2.py'), ENT.format(v=2) + 'VAL = 3\n')                   # casse le test
        c, s = lancer(self.o, 'tester_outils.py', '--candidat', 'x=2'); self.assertNotEqual(c, 0, s)
        c, s = lancer(self.o, 'tester_outils.py'); self.assertEqual(c, 0, s)                                 # la version courante reste la v1


if __name__ == '__main__':
    unittest.main()
