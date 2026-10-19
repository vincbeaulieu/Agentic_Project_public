"""Tests d'intégration (plus lents, mode --complet) : les bancs d'essai des outils courants passent (F1 1,0, cas exacts, déterministe)."""
import os, sys, json, subprocess, unittest
from aide_tests_v2 import OUTILS, RACINE_CC, chemin_outil, chemin
from cc_lib_v2 import courant
INTEGRATION = True


class Bancs(unittest.TestCase):
    def banc(self, outil):
        v = courant(outil); r = subprocess.run([sys.executable, chemin_outil('banc'), outil, str(v)], capture_output=True, text=True, cwd=OUTILS)
        self.assertEqual(r.returncode, 0, r.stdout[-500:] + r.stderr[-500:])
        d = chemin('bancs', outil, 'resultats'); f = sorted(x for x in os.listdir(d) if x.startswith(f'resultat_{outil}_v{v}_'))[-1]
        res = json.load(open(os.path.join(d, f), encoding='utf-8'))
        self.assertEqual(res['qualite']['f1'], 1.0); self.assertTrue(res['automatisation']['deterministe'])

    def test_detecteurs_rapport(self): self.banc('detecteurs_rapport')
    def test_evaluer_travail(self): self.banc('evaluer_travail')


if __name__ == '__main__':
    unittest.main()
