"""Tests de balayer_termes_v3 (lexique fictif : aucun terme réel n'est écrit dans les tests) : toute la suite de la v2 rejouée sur
la v3 (dont la suite v1), plus la lecture de tous les membres texte d'une archive zip : un terme dans un .py, un .ps1 ou un
fichier sans extension d'une archive est relevé, avec le membre comme partie ; les balises ne sont retirées que pour .xml et
.rels ; un membre binaire (octet nul) n'est pas lu mais compté au bilan et dans le JSON. Témoin (LC-032) : la v2 ne relève pas
le terme placé dans le .py de l'archive (défaut du 19 oct. 2026 : archive de l'édition publique balayée sans ses .py)."""
import os, sys, json, zipfile, subprocess, unittest
from unittest import mock
from aide_tests_v2 import dossier_essai, chemin_version, importer_version
import test_balayer_termes_v1 as T1, test_balayer_termes_v2 as T2
OUTIL = chemin_version('balayer_termes', 3); BT = importer_version('balayer_termes', 3)
BT2 = importer_version('balayer_termes', 2)
LEX, ecrire, lex = T1.LEX, T1.ecrire, T1.lex
def run(*a): r = subprocess.run([sys.executable, OUTIL] + list(a), capture_output=True, text=True, timeout=120); return r.returncode, r.stdout + r.stderr
class _SurV3:
    def setUp(self):
        p1 = mock.patch.multiple(T1, OUTIL=OUTIL, BT=BT); p1.start(); self.addCleanup(p1.stop)
        p2 = mock.patch.multiple(T2, OUTIL=OUTIL, BT=BT); p2.start(); self.addCleanup(p2.stop)
        super().setUp()
class BalayageV1SurV3(_SurV3, T1.Balayage): pass
class LigneDeCommandeV1SurV3(_SurV3, T1.LigneDeCommande): pass
class AcceptationsV2SurV3(_SurV3, T2.Acceptations):
    def test_temoin_v1_sans_strict(self): pass                     # témoin propre à la v2 (la v1 comparée à la v2), sans objet ici
class ArchivesDeCode(unittest.TestCase):
    def setUp(self):
        self.d = dossier_essai('balayer_termes_v3_' + self._testMethodName[5:30]); self.cible = os.path.join(self.d, 'cible')
        os.makedirs(self.cible); self.z = os.path.join(self.cible, 'edition_v1.zip')
        with zipfile.ZipFile(self.z, 'w') as z:
            z.writestr('espace/outils/a_v1.py', "MESSAGE = 'un zorglub caché dans le code'\n")
            z.writestr('espace/outils/b_v1.ps1', 'Write-Host "satellite espion"\n')
            z.writestr('espace/LISEZMOI', 'alpha un deux omega\n')
            z.writestr('espace/word/document.xml', '<w:t>zorg</w:t><w:t>lub</w:t>')                  # balises retirées : « zorg lub »
            z.writestr('espace/notes_v1.txt', '<b>éléphant rose</b>')                                # .txt : balises gardées, terme lu
            z.writestr('espace/img/logo.png', b'\x89PNG\r\n\x1a\n\x00\x00zorglub')                    # binaire : non lu
    def test_membres_texte_lus(self):
        C, n = BT.balayer(LEX, [self.cible]); self.assertEqual(n, 1)
        T = sorted((c['partie'], c['terme']) for c in C)
        self.assertIn(('espace/outils/a_v1.py', 'zorglub'), T); self.assertIn(('espace/outils/b_v1.ps1', 'satellite'), T)
        self.assertIn(('espace/notes_v1.txt', 'éléphant rose'), T); self.assertIn(('espace/LISEZMOI', 'alpha un deux omega'), T)
        self.assertNotIn('espace/img/logo.png', [c['partie'] for c in C]); self.assertNotIn('espace/word/document.xml', [c['partie'] for c in C])
        self.assertEqual(BT.NON_LUS, [self.z + '#espace/img/logo.png'])
    def test_bilan_et_json(self):
        j = os.path.join(self.d, 'r_v1.json'); c, s = run(lex(self.d), self.cible, '--json', j)
        self.assertEqual(c, 1, s); self.assertIn('1 membre(s) d’archive non lu(s) (binaires)', s)
        self.assertEqual(json.load(open(j, encoding='utf-8'))['membres_non_lus'], [self.z + '#espace/img/logo.png'])
    def test_temoin_v2_saute_le_code(self):
        C2, _ = BT2.balayer(LEX, [self.cible]); P2 = {c['partie'] for c in C2}
        self.assertNotIn('espace/outils/a_v1.py', P2); self.assertIn('espace/notes_v1.txt', P2)          # défaut présent en v2
        C3, _ = BT.balayer(LEX, [self.cible]); self.assertIn('espace/outils/a_v1.py', {c['partie'] for c in C3})
if __name__ == '__main__':
    unittest.main()
