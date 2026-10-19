"""Tests de balayer_termes_v1 (lexique fictif : aucun terme réel n'est écrit dans les tests). Termes littéraux sans casse ni accents,
mots entiers ; expressions régulières sensibles à la casse ; proximité de deux termes ; exceptions globales et par catégorie ;
noms de fichiers et parties texte d'un zip ; codes de sortie (0 : rien de bloquant, 1 : bloquant, 2 : appel invalide) ;
sorties JSON et Markdown jamais écrasées. Témoin (LC-032) : sans l'exception de catégorie, le constat exempté est bien relevé."""
import os, sys, json, zipfile, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version
OUTIL = chemin_version('balayer_termes', 1); BT = importer_version('balayer_termes', 1)
LEX = {"version": 1, "categories": [
    {"id": "X1", "nom": "fictif", "gravite": "bloquant", "termes": ["zorglub", "éléphant rose"], "regex": ["(?i)\\bflux\\w*"]},
    {"id": "X2", "nom": "codes", "gravite": "bloquant", "casse": True, "regex": ["\\bZX\\d+[AB]\\b"]},
    {"id": "X3", "nom": "à revoir", "gravite": "a_revoir", "termes": ["satellite"], "exceptions": ["satellite de communication"]}],
    "proximite": [{"id": "P1", "nom": "alpha près d'omega", "gravite": "bloquant", "a": ["alpha"], "b": ["omega"], "fenetre": 3}],
    "exceptions": [{"regex": "zorglub-autorise", "motif": "exemple d'exception globale"}]}
def ecrire(d, rel, t):
    p = os.path.join(d, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'w', encoding='utf-8').write(t); return p
def lex(d, L=LEX):
    p = os.path.join(d, 'lexique_v1.json'); json.dump(L, open(p, 'w', encoding='utf-8'), ensure_ascii=False); return p
def run(*a): r = subprocess.run([sys.executable, OUTIL] + list(a), capture_output=True, text=True, timeout=120); return r.returncode, r.stdout + r.stderr
class Balayage(unittest.TestCase):
    def setUp(self): self.d = dossier_essai('balayer_termes_v1_' + self._testMethodName[5:30]); self.cible = os.path.join(self.d, 'cible')
    def termes(self, C): return sorted((c['categorie'], c['terme']) for c in C)
    def test_litteral_sans_casse_ni_accents_et_mots_entiers(self):
        ecrire(self.cible, 'a.md', 'Un ZORGLUB ici ; un Elephant Rose là ; zorglubs non (mot entier).')
        C, n = BT.balayer(LEX, [self.cible]); self.assertEqual(n, 1)
        self.assertEqual(self.termes(C), [('X1', 'Elephant Rose'), ('X1', 'ZORGLUB')])
    def test_regex_sensible_a_la_casse(self):
        ecrire(self.cible, 'b.py', "code = 'ZX12A' ; autre = 'zx12a' ; flux et Fluxion")
        C, _ = BT.balayer(LEX, [self.cible])
        self.assertIn(('X2', 'ZX12A'), self.termes(C)); self.assertNotIn(('X2', 'zx12a'), self.termes(C))
        self.assertIn(('X1', 'Fluxion'), self.termes(C))
    def test_proximite(self):
        ecrire(self.cible, 'c.txt', "alpha un deux omega\nalpha un deux trois quatre omega")
        C, _ = BT.balayer(LEX, [self.cible]); P = [c for c in C if c['categorie'] == 'P1']
        self.assertEqual(len(P), 1); self.assertEqual(P[0]['ligne'], 1)
    def test_exceptions_globale_et_de_categorie_avec_temoin(self):
        ecrire(self.cible, 'd.md', 'zorglub-autorise ; satellite de communication ; satellite espion')
        C, _ = BT.balayer(LEX, [self.cible])
        self.assertEqual(self.termes(C), [('X3', 'satellite')])
        L2 = json.loads(json.dumps(LEX)); L2['categories'][2].pop('exceptions')
        C2, _ = BT.balayer(L2, [self.cible]); self.assertEqual(self.termes(C2), [('X3', 'satellite'), ('X3', 'satellite')])   # témoin : sans l'exception, relevé
    def test_nom_de_fichier_et_zip(self):
        ecrire(self.cible, 'rapport_zorglub_v1.txt', 'rien')
        z = os.path.join(self.cible, 'doc_v1.docx')
        with zipfile.ZipFile(z, 'w') as zz: zz.writestr('word/document.xml', '<w:t>un satellite espion</w:t>'); zz.writestr('word/media/i.png', b'\x89PNG')
        C, _ = BT.balayer(LEX, [self.cible])
        self.assertIn(('[nom]', 'zorglub'), [(c['partie'], c['terme']) for c in C])
        self.assertIn(('word/document.xml', 'satellite'), [(c['partie'], c['terme']) for c in C])
    def test_identifiants_de_code(self):
        ecrire(self.cible, 'e.py', "liste_zorglub = 1\nzorglubien = 2\nvaleur = 'ZX7B_total'")
        C, _ = BT.balayer(LEX, [self.cible]); T = self.termes(C)
        self.assertIn(('X1', 'zorglub'), T); self.assertEqual(sum(1 for x in T if x[1].lower() == 'zorglub'), 1)   # « zorglubien » non relevé
    def test_exclure_un_chemin(self):
        ecrire(self.cible, 'garde/a.md', 'zorglub'); ecrire(self.cible, 'ignore/b.md', 'zorglub')
        C, n = BT.balayer(LEX, [self.cible], exclure=[r'/ignore/']); self.assertEqual(n, 1); self.assertEqual(len(C), 1)
class LigneDeCommande(unittest.TestCase):
    def setUp(self): self.d = dossier_essai('balayer_termes_v1_cli_' + self._testMethodName[5:25]); self.cible = os.path.join(self.d, 'cible')
    def test_codes_de_sortie(self):
        L = lex(self.d); ecrire(self.cible, 'a.md', 'satellite espion')
        c, s = run(L, self.cible); self.assertEqual(c, 0, s)                                   # seulement « à revoir »
        ecrire(self.cible, 'b.md', 'zorglub'); c, s = run(L, self.cible); self.assertEqual(c, 1, s)
        c, s = run(L); self.assertEqual(c, 2, s); c, s = run(L, os.path.join(self.d, 'absent')); self.assertEqual(c, 2, s)
    def test_sorties_json_md_sans_ecrasement(self):
        L = lex(self.d); ecrire(self.cible, 'a.md', 'zorglub'); j, m = os.path.join(self.d, 'r_v1.json'), os.path.join(self.d, 'r_v1.md')
        c, s = run(L, self.cible, '--json', j, '--md', m); self.assertEqual(c, 1, s)
        self.assertEqual(json.load(open(j, encoding='utf-8'))['constats'][0]['terme'], 'zorglub'); self.assertIn('| bloquant | X1 |', open(m, encoding='utf-8').read())
        c, s = run(L, self.cible, '--json', j); self.assertEqual(c, 2, s); self.assertIn('existe déjà', s)
if __name__ == '__main__':
    unittest.main()
