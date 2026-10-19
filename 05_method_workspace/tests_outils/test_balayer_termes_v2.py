"""Tests de balayer_termes_v2 (lexique fictif : aucun terme réel n'est écrit dans les tests) : toute la suite de la v1 rejouée sur
la v2 (sans les options nouvelles, même comportement), plus les acceptations relues (--acceptes) et le mode --strict :
un constat « à revoir » accepté sort du décompte avec son motif ; une acceptation qui ne sert à rien est signalée ; un constat
bloquant ne s'accepte jamais ; une acceptation sans motif est refusée (code 2) ; --strict rend 1 tant qu'un constat n'est ni
corrigé ni accepté. Témoin (LC-032) : la v1 ne connaît pas --strict (le prend pour un chemin : code 2), et un constat « à revoir »
seul y rend 0 — le défaut corrigé par la v2 est donc bien présent dans la v1."""
import os, sys, json, subprocess, unittest
from unittest import mock
from aide_tests_v2 import dossier_essai, chemin_version, importer_version
import test_balayer_termes_v1 as T1
OUTIL = chemin_version('balayer_termes', 2); BT = importer_version('balayer_termes', 2)
OUTIL1 = chemin_version('balayer_termes', 1)
LEX, ecrire, lex = T1.LEX, T1.ecrire, T1.lex
def run(outil, *a): r = subprocess.run([sys.executable, outil] + list(a), capture_output=True, text=True, timeout=120); return r.returncode, r.stdout + r.stderr
class _SurV2:
    def setUp(self):
        p = mock.patch.multiple(T1, OUTIL=OUTIL, BT=BT); p.start(); self.addCleanup(p.stop); super().setUp()
class BalayageV1SurV2(_SurV2, T1.Balayage): pass
class LigneDeCommandeV1SurV2(_SurV2, T1.LigneDeCommande): pass
class Acceptations(unittest.TestCase):
    def setUp(self):
        self.d = dossier_essai('balayer_termes_v2_' + self._testMethodName[5:30]); self.cible = os.path.join(self.d, 'cible'); self.L = lex(self.d)
        ecrire(self.cible, 'garde/a.md', 'un satellite espion ; un autre satellite')
    def acceptes(self, A, nom='acceptes_v1.json'):
        p = os.path.join(self.d, nom); json.dump(A, open(p, 'x', encoding='utf-8'), ensure_ascii=False); return p
    def test_constat_a_revoir_accepte_avec_motif(self):
        A = self.acceptes([dict(chemin='garde/a\\.md$', categorie='X3', terme='SATELLITE', motif='sens courant, relu')])
        j = os.path.join(self.d, 'r_v1.json')
        c, s = run(OUTIL, self.L, self.cible, '--acceptes', A, '--json', j, '--strict'); self.assertEqual(c, 0, s)
        R = json.load(open(j, encoding='utf-8'))
        self.assertEqual(R['constats'], []); self.assertEqual(len(R['acceptes']), 2); self.assertEqual(R['acceptes'][0]['accepte'], 'sens courant, relu')
        self.assertIn('2 constat(s) accepté(s)', s)
    def test_strict_exige_relecture(self):
        c, s = run(OUTIL, self.L, self.cible); self.assertEqual(c, 0, s)                      # sans --strict : « à revoir » ne bloque pas
        c, s = run(OUTIL, self.L, self.cible, '--strict'); self.assertEqual(c, 1, s)           # avec --strict : non relu = non propre
    def test_acceptation_sans_objet_signalee(self):
        A = self.acceptes([dict(chemin='garde/a\\.md$', categorie='*', terme='satellite', motif='relu'),
                           dict(chemin='ailleurs\\.md$', categorie='X3', terme='satellite', motif='périmée')])
        j = os.path.join(self.d, 'r_v1.json'); c, s = run(OUTIL, self.L, self.cible, '--acceptes', A, '--json', j, '--strict')
        self.assertEqual(c, 0, s); self.assertIn('1 acceptation(s) sans objet', s)
        self.assertEqual([x['motif'] for x in json.load(open(j, encoding='utf-8'))['acceptations_sans_objet']], ['périmée'])
    def test_bloquant_jamais_accepte(self):
        ecrire(self.cible, 'garde/b.md', 'zorglub')
        A = self.acceptes([dict(chemin='b\\.md$', categorie='X1', terme='zorglub', motif='tentative')])
        c, s = run(OUTIL, self.L, self.cible, '--acceptes', A); self.assertEqual(c, 1, s); self.assertIn('1 acceptation(s) refusée(s)', s)
        C, _ = BT.balayer(LEX, [self.cible]); R, acc, ref, sans = BT.appliquer_acceptes(C, json.load(open(A, encoding='utf-8')))
        self.assertEqual([c['terme'] for c in R if c['gravite'] == 'bloquant'], ['zorglub']); self.assertEqual(len(ref), 1)
    def test_acceptation_incomplete_refusee(self):
        A = self.acceptes([dict(chemin='a\\.md$', categorie='X3', terme='satellite', motif='  ')])
        c, s = run(OUTIL, self.L, self.cible, '--acceptes', A); self.assertEqual(c, 2, s); self.assertIn('incomplète', s)
        c, s = run(OUTIL, self.L, self.cible, '--acceptes', os.path.join(self.d, 'absent.json')); self.assertEqual(c, 2, s)
    def test_temoin_v1_sans_strict(self):
        c, s = run(OUTIL1, self.L, self.cible); self.assertEqual(c, 0, s)                     # défaut : « à revoir » non relus, code 0
        c, s = run(OUTIL1, self.L, self.cible, '--strict'); self.assertEqual(c, 2, s)          # la v1 ne connaît pas l'option
if __name__ == '__main__':
    unittest.main()
