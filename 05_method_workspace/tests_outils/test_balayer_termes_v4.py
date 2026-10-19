"""Tests de balayer_termes_v4 (lexique fictif : aucun terme réel n'est écrit dans les tests) : toute la suite de la v3 rejouée sur
la v4 (dont les suites v2 et v1), plus les acceptations appliquées aux membres d'une archive : l'expression « chemin » d'une
acceptation est cherchée dans « archive#membre » ; la même acceptation vaut pour l'arbre et pour son archive, si bien qu'un
balayage strict de l'archive rend 0 quand l'arbre a été relu ; une acceptation qui ne vise que l'arbre ne s'étend pas à un autre
membre. Témoin (LC-032) : avec la v3, la même acceptation reste sans objet sur l'archive et le balayage strict rend 1."""
import os, sys, json, zipfile, subprocess, unittest
from unittest import mock
from aide_tests_v2 import dossier_essai, chemin_version, importer_version
import test_balayer_termes_v1 as T1, test_balayer_termes_v2 as T2, test_balayer_termes_v3 as T3
OUTIL = chemin_version('balayer_termes', 4); BT = importer_version('balayer_termes', 4)
OUTIL3 = chemin_version('balayer_termes', 3)
LEX, ecrire, lex = T1.LEX, T1.ecrire, T1.lex
def run(outil, *a): r = subprocess.run([sys.executable, outil] + list(a), capture_output=True, text=True, timeout=120); return r.returncode, r.stdout + r.stderr
class _SurV4:
    def setUp(self):
        for M in (T1, T2, T3):
            p = mock.patch.multiple(M, OUTIL=OUTIL, BT=BT); p.start(); self.addCleanup(p.stop)
        super().setUp()
class BalayageV1SurV4(_SurV4, T1.Balayage): pass
class LigneDeCommandeV1SurV4(_SurV4, T1.LigneDeCommande): pass
class AcceptationsV2SurV4(_SurV4, T2.Acceptations):
    def test_temoin_v1_sans_strict(self): pass                     # témoin propre à la v2, sans objet ici
class ArchivesV3SurV4(_SurV4, T3.ArchivesDeCode):
    def test_temoin_v2_saute_le_code(self): pass                   # témoin propre à la v3, sans objet ici
class AcceptationsDansLesArchives(unittest.TestCase):
    def setUp(self):
        self.d = dossier_essai('balayer_termes_v4_' + self._testMethodName[5:30]); self.L = lex(self.d)
        self.arbre = os.path.join(self.d, 'edition', 'espace'); ecrire(self.arbre, 'outils/a_v1.py', "# un satellite de passage\n")
        ecrire(self.arbre, 'docs/b_v1.md', 'un satellite ici aussi')
        self.z = os.path.join(self.d, 'paquet', 'espace_v1.zip'); os.makedirs(os.path.dirname(self.z))
        with zipfile.ZipFile(self.z, 'w') as z:
            for b, _, fs in os.walk(self.arbre):
                for f in fs: z.write(os.path.join(b, f), 'espace/' + os.path.relpath(os.path.join(b, f), self.arbre))
        self.A = os.path.join(self.d, 'acceptes_v1.json')
        json.dump([dict(chemin=r'/outils/a_v\d+\.py$', categorie='X3', terme='satellite', motif='commentaire générique, relu')], open(self.A, 'x', encoding='utf-8'))
    def test_meme_acceptation_pour_l_arbre_et_l_archive(self):
        for cible in (os.path.join(self.arbre, 'outils'), self.z):
            j = os.path.join(self.d, f'r_{os.path.basename(cible)}_v1.json')
            c, s = run(OUTIL, self.L, cible, '--acceptes', self.A, '--json', j)
            R = json.load(open(j, encoding='utf-8'))
            self.assertEqual(len(R['acceptes']), 1, s); self.assertEqual(R['acceptations_sans_objet'], [], s)
        self.assertEqual([c['partie'] for c in R['constats']], ['espace/docs/b_v1.md'])          # l'autre membre reste à relire
    def test_strict_sur_l_archive(self):
        c, s = run(OUTIL, self.L, self.z, '--acceptes', self.A, '--strict'); self.assertEqual(c, 1, s)   # b_v1.md non relu
        A2 = os.path.join(self.d, 'acceptes_v2.json')
        json.dump(json.load(open(self.A, encoding='utf-8')) + [dict(chemin=r'#espace/docs/b_v1\.md$', categorie='X3', terme='satellite', motif='relu')],
                  open(A2, 'x', encoding='utf-8'))
        c, s = run(OUTIL, self.L, self.z, '--acceptes', A2, '--strict'); self.assertEqual(c, 0, s)
    def test_temoin_v3_acceptation_sans_objet_sur_l_archive(self):
        c, s = run(OUTIL3, self.L, self.z, '--acceptes', self.A, '--strict')
        self.assertEqual(c, 1, s); self.assertIn('1 acceptation(s) sans objet', s)
if __name__ == '__main__':
    unittest.main()
