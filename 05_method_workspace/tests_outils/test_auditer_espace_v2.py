"""Tests de auditer_espace_v2 : comparaison d'arbres (ajouts, suppressions, modifications, déplacements), réemploi des empreintes,
contrôles de fichier, suivi des constats (« depuis »), écriture sans écrasement ; puis, sur un espace fictif isolé (copie de l'outil,
faux evaluer_travail et organiser_outils), audits successifs : premier audit complet, audit sans changement (tout repris, rien
réexaminé), changements (seuls les éléments modifiés réexaminés ; constats résolus et nouveaux), nouvelle version sans suite
de tests ajoutée depuis la précédente (A24), seul l'outil modifié réexaminé, dossiers intouchables et copies non jugés, tests en échec (bloquant, code 1), option --complet."""
import os, re, sys, json, glob, time, shutil, subprocess, unittest, importlib.util
from aide_tests_v1 import dossier_essai, chemin_outil

SRC = chemin_outil('auditer_espace', 2)
spec = importlib.util.spec_from_file_location('auditer_espace_v2_essai', SRC); AE = importlib.util.module_from_spec(spec); spec.loader.exec_module(AE)
ENT = '"""\nOUTIL: {o}\nVERSION: {v}\nRESUME: essai\nUSAGE: -\nENTREES: -\nSORTIES: -\nCATEGORIE: essai\nBANC: -\nREMPLACE: -\n"""\n'
FAUX_EVAL = ("import sys, os\nd = sys.argv[1]\nopen(os.path.join(os.path.dirname(d), 'appels_evaluer.log'), 'a').write(os.path.basename(d) + '\\n')\n"
             "print('Verdict : NON CONFORME' if os.path.exists(os.path.join(d, 'NC')) else 'Verdict : CONFORME')\n")


def lire(chemin):
    with open(chemin, encoding='utf-8') as g: return g.read()


def w(chemin, texte):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, 'w', encoding='utf-8') as g: g.write(texte)


class Fonctions(unittest.TestCase):
    def test_comparer(self):
        B = {'a': [1, 1, 'h1'], 'b': [1, 1, 'h2'], 'c': [1, 1, 'h3'], 'd': [1, 1, 'h4']}
        A = {'a': [1, 1, 'h1'], 'b': [2, 2, 'h2x'], 'c2': [1, 1, 'h3'], 'e': [1, 1, 'h5']}
        D = AE.comparer(A, B)
        self.assertFalse(D['premier']); self.assertEqual(D['modifies'], ['b']); self.assertEqual(D['deplaces'], [['c', 'c2']])
        self.assertEqual(D['supprimes'], ['d']); self.assertEqual(D['ajoutes'], ['e'])
        self.assertTrue(AE.comparer(A, None)['premier'])

    def test_arbre_reemploie_les_empreintes(self):
        R = dossier_essai('audit_arbre'); cc = os.path.join(R, '00_competences_claude')
        w(os.path.join(cc, 'a.txt'), 'un'); w(os.path.join(R, '11_t', 'b.md'), 'deux'); w(os.path.join(cc, 'revues', 'x.json'), '{}')
        w(os.path.join(cc, '__pycache__', 'z.pyc'), 'x')
        n = [0]; orig_cc, orig_h = AE.CC, AE.h16
        def compte(f): n[0] += 1; return orig_h(f)
        AE.CC, AE.h16 = cc, compte
        try:
            A1 = AE.arbre(R, None, ['00_competences_claude/revues'])
            self.assertEqual(sorted(A1), ['00_competences_claude/a.txt', '11_t/b.md']); self.assertEqual(n[0], 2)   # revues et __pycache__ exclus
            n[0] = 0; A2 = AE.arbre(R, A1, ['00_competences_claude/revues']); self.assertEqual(n[0], 0); self.assertEqual(A1, A2)
            w(os.path.join(R, '11_t', 'b.md'), 'deux, modifié'); n[0] = 0
            A3 = AE.arbre(R, A2, ['00_competences_claude/revues']); self.assertEqual(n[0], 1)
            self.assertEqual(AE.comparer(A3, A2)['modifies'], ['11_t/b.md'])
        finally: AE.CC, AE.h16 = orig_cc, orig_h

    def test_controles_fichier(self):
        npj = re.compile(AE.NE_PAS_JUGER + '|^10_revision_01\\.1(/|$)')
        m = AE.collections.Counter({'lu.txt': 1})
        codes = lambda p, t=5: [k[0] for k in AE.controles_fichier(p, [t, 0, 'h'], m, npj)]
        self.assertEqual(codes('11_t/seul.txt'), ['A01']); self.assertEqual(codes('11_t/lu.txt'), [])
        self.assertEqual(codes('11_t/vide.md', 0), ['A03']); self.assertEqual(codes('11_t/~$doc.docx'), ['A04'])
        for p in ('11_t/archive/seul.txt', '10_revision_01.1/seul.txt', '00_espace_cloud_claude/racine/seul.txt', '11_t/_copie_cloud_20261015/seul.txt'):
            self.assertEqual(codes(p), [], p)

    def test_suivi_depuis(self):
        k = lambda m: dict(code='A01', gravite='mineur', message=m, chemin='x', portee='fichier', cle='x')
        E0 = dict(date='20261014_100000', constats=[dict(k('artefact a.txt'), depuis='20261013_100000'), k('artefact b.txt')])
        C = [k('artefact a.txt'), k('artefact c.txt')]
        nv, res = AE.suivre(C, E0, '20261015_100000')
        self.assertEqual(C[0]['depuis'], '20261013_100000'); self.assertEqual(C[1]['depuis'], '20261015_100000')
        self.assertEqual([x['message'] for x in nv], ['artefact c.txt']); self.assertEqual([x['message'] for x in res], ['artefact b.txt'])
        self.assertEqual(AE.age_j('20261013_100000', '20261015_100000'), 2)

    def test_ecrire_sans_ecraser(self):
        d = dossier_essai('audit_ecrire'); f = os.path.join(d, 'r.md')
        self.assertEqual(AE.ecrire(f, 'a'), f); f2 = AE.ecrire(f, 'b')
        self.assertTrue(f2.endswith('r_2.md')); self.assertEqual(lire(f), 'a')


def espace(nom):
    R = dossier_essai(nom); cc = os.path.join(R, '00_competences_claude'); o = os.path.join(cc, 'outils')
    os.makedirs(os.path.join(o, 'auditer_espace')); shutil.copy(SRC, os.path.join(o, 'auditer_espace', 'auditer_espace_v2.py'))
    w(os.path.join(o, 'evaluer_travail.py'), FAUX_EVAL); w(os.path.join(o, 'organiser_outils.py'), "print('conforme')\n")
    w(os.path.join(o, 'x', 'x_v1.py'), ENT.format(o='x', v=1) + "print('x')\n")
    w(os.path.join(o, 'y', 'y_v1.py'), ENT.format(o='y', v=1) + "print('y1')\n")
    w(os.path.join(o, 'y', 'y_v2.py'), '"""\nOUTIL: y\nVERSION: 2\n"""\nB = \'/home/claude/donnees\'\n')
    w(os.path.join(o, 'z', 'z_v1.cmd'), '@echo off\r\n')
    w(os.path.join(o, 'README_q', 'README_q_v1.md'), '# lisez-moi\n')
    w(os.path.join(o, 'v', 'v_v1.py'), ENT.format(o='v', v=1))
    w(os.path.join(o, '_gestion', 'adoption_outils_v1.json'), json.dumps(dict(decisions=dict(v=dict(courant=None, statut='abandonné')))))
    w(os.path.join(cc, 'tests', 'test_x_v1.py'), "import unittest\n")
    w(os.path.join(cc, 'tests', 'test_u_v1.py'), "import unittest\n"); w(os.path.join(o, 'u', 'archive', 'u_v1.py'), ENT.format(o='u', v=1))
    w(os.path.join(o, 'u', 'u_v2.py'), ENT.format(o='u', v=2) + "print('u2')\n"); t0 = time.time()
    os.utime(os.path.join(cc, 'tests', 'test_u_v1.py'), (t0 - 100, t0 - 100)); os.utime(os.path.join(o, 'u', 'archive', 'u_v1.py'), (t0 - 50, t0 - 50))
    w(os.path.join(cc, 'tests', 'test_divers_v1.py'), "OUTIL = 'auditer_espace'\n")          # couvre un outil en le citant
    time.sleep(0.05); w(os.path.join(cc, 'tests', 'rapports', 'rapport_tests_1.json'), json.dumps(dict(verdict='conforme')))
    w(os.path.join(R, '11_essai', 'notes.txt'), 'notes jamais lues\n'); w(os.path.join(R, '11_essai', 'vide.md'), '')
    w(os.path.join(R, '11_essai', 'lisez.md'), 'voir lu.txt\n'); w(os.path.join(R, '11_essai', 'lu.txt'), 'lu\n')
    doublon = 'contenu identique ' * 20
    w(os.path.join(R, '11_essai', 'doublon1.md'), doublon); w(os.path.join(R, '12_autre', 'doublon2.md'), doublon); w(os.path.join(R, '12_autre', 'NC'), 'x')
    w(os.path.join(R, '10_revision_01.1', 'orphelin.txt'), 'ne pas juger\n'); w(os.path.join(R, '10_revision_01.1', 'NC'), 'x')
    w(os.path.join(R, '00_espace_cloud_claude', 'racine', 'copie.txt'), 'copie\n')
    return R, os.path.join(o, 'auditer_espace', 'auditer_espace_v2.py'), os.path.join(cc, 'revues')


def auditer(R, outil, rev, *opts):
    r = subprocess.run([sys.executable, outil, '--racine', R, '--espace', 'essai'] + list(opts), capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=''))
    f = max(glob.glob(os.path.join(rev, 'audit_essai_*.json')), key=os.path.getmtime)
    return r.returncode, r.stdout + r.stderr, json.loads(lire(f))


def appels(R):
    f = os.path.join(R, 'appels_evaluer.log'); return lire(f).split() if os.path.exists(f) else []


def codes(J, chemin=None):
    return sorted((k['code'], k['gravite']) for k in J['constats'] if chemin is None or (k['chemin'] or '').startswith(chemin))


class AuditsSuccessifs(unittest.TestCase):
    def test_cycle(self):
        R, outil, rev = espace('audit_cycle')
        # 1. premier audit : tout examiné
        c, s, J1 = auditer(R, outil, rev); self.assertEqual(c, 0, s)
        self.assertTrue(J1['arbre']['premier']); self.assertIsNone(J1['precedent'])
        self.assertEqual(J1['reexamines'], dict(outils=6, outils_repris=0, travaux=2, travaux_repris=0))   # v abandonné ; 00_* et intouchable exclus
        self.assertEqual(sorted(appels(R)), ['11_essai', '12_autre'])
        O = '00_competences_claude/outils/'
        self.assertEqual(codes(J1, O + 'y'), [('A06', 'majeur'), ('A07', 'info'), ('A23', 'majeur'), ('A23', 'majeur'), ('A23', 'mineur')])
        self.assertEqual(codes(J1, O + 'z'), [('A06', 'mineur')]); self.assertEqual(codes(J1, O + 'README_q'), [])
        self.assertNotIn('A06', [k for k, _ in codes(J1, O + 'x')]); self.assertNotIn('A06', [k for k, _ in codes(J1, O + 'auditer_espace')])
        a01 = sorted(k['chemin'] for k in J1['constats'] if k['code'] == 'A01'); self.assertEqual(a01, ['11_essai/notes.txt'])
        self.assertIn(('A03', 'mineur'), codes(J1, '11_essai/vide.md')); self.assertIn(('A13', 'majeur'), codes(J1, '12_autre'))
        self.assertTrue(any(k['code'] == 'A02' and 'doublon' in k['message'] for k in J1['constats']))
        self.assertIn(('A24', 'mineur'), codes(J1, O + 'u')); self.assertNotIn('A24', [k for k, _ in codes(J1, O + 'y')])
        self.assertFalse(any((k['chemin'] or '').startswith(('10_revision_01.1', '00_espace_cloud_claude')) for k in J1['constats']))
        self.assertFalse(any(p.startswith('00_competences_claude/revues') for p in J1['arbre']['ajoutes']))
        md = lire(max(glob.glob(os.path.join(rev, 'audit_essai_*.md')), key=os.path.getmtime))
        for t in ('## 1. Arbre', '## 2. Nouveaux constats', '## 3. Constats persistants', '## 4. Résolus', '## 5. Recommandations'): self.assertIn(t, md)
        # 2. sans changement : rien réexaminé, tout repris, rien de nouveau
        c, s, J2 = auditer(R, outil, rev); self.assertEqual(c, 0, s)
        self.assertEqual(J2['precedent'], J1['date'])
        self.assertEqual({k: len(J2['arbre'][k]) for k in ('ajoutes', 'supprimes', 'modifies', 'deplaces')}, dict(ajoutes=0, supprimes=0, modifies=0, deplaces=0))
        self.assertEqual(J2['reexamines'], dict(outils=0, outils_repris=6, travaux=0, travaux_repris=2)); self.assertEqual(len(appels(R)), 2)
        self.assertEqual(J2['nouveaux'], []); self.assertEqual(J2['resolus'], [])
        self.assertEqual(sorted(AE.ident(k) for k in J2['constats']), sorted(AE.ident(k) for k in J1['constats']))
        self.assertTrue(all(k['depuis'] == J1['date'] for k in J2['constats']))
        # 3. changements : tests de y ajoutés, fichier renommé, dossier 12 corrigé
        cc = os.path.join(R, '00_competences_claude')
        w(os.path.join(cc, 'tests', 'test_y_v1.py'), 'import unittest\n'); time.sleep(0.05)
        w(os.path.join(cc, 'tests', 'rapports', 'rapport_tests_2.json'), json.dumps(dict(verdict='conforme')))
        os.rename(os.path.join(R, '11_essai', 'notes.txt'), os.path.join(R, '11_essai', 'notes_renommees.txt'))
        os.rename(os.path.join(R, '12_autre', 'NC'), os.path.join(R, '12_autre', 'corrige.md'))
        c, s, J3 = auditer(R, outil, rev); self.assertEqual(c, 0, s)
        self.assertIn('00_competences_claude/tests/test_y_v1.py', J3['arbre']['ajoutes'])
        self.assertIn(['11_essai/notes.txt', '11_essai/notes_renommees.txt'], J3['arbre']['deplaces'])
        self.assertEqual(J3['reexamines']['travaux'], 2); self.assertEqual(len(appels(R)), 4)
        res = {(k['code'], k['chemin']) for k in J3['resolus']}
        self.assertIn(('A06', O + 'y'), res); self.assertIn(('A13', '12_autre'), res); self.assertIn(('A01', '11_essai/notes.txt'), res)
        self.assertIn('A01|11_essai/notes_renommees.txt|artefact notes_renommees.txt : rien ne le lit ni ne le cite', J3['nouveaux'])
        self.assertNotIn('A24', [k for k, _ in codes(J3, O + 'y')])
        # 4. seul l'outil modifié est réexaminé ; outil modifié après le dernier rapport de tests : A25
        for i, r in enumerate(sorted(glob.glob(os.path.join(cc, 'tests', 'rapports', '*.json')))): os.utime(r, (time.time() - 30 + i, time.time() - 30 + i))
        w(os.path.join(cc, 'outils', 'y', 'y_v2.py'), lire(os.path.join(cc, 'outils', 'y', 'y_v2.py')) + '# ajout\n')
        c, s, J4 = auditer(R, outil, rev); self.assertEqual(c, 0, s)
        self.assertEqual(J4['arbre']['modifies'], ['00_competences_claude/outils/y/y_v2.py'])
        self.assertEqual(J4['reexamines'], dict(outils=1, outils_repris=5, travaux=0, travaux_repris=2))
        self.assertTrue(any(k['code'] == 'A25' for k in J4['constats']))
        self.assertIn(('A24', 'mineur'), codes(J4, O + 'u'))                               # repris sans réexamen
        # 5. nouvelle suite de tests pour u v2 : A24 résolu
        w(os.path.join(cc, 'tests', 'test_u_v2.py'), 'import unittest\n')
        c, s, J5 = auditer(R, outil, rev); self.assertEqual(c, 0, s)
        self.assertIn(('A24', O + 'u'), {(k['code'], k['chemin']) for k in J5['resolus']})
        # 6. tests en échec : bloquant, code 1
        w(os.path.join(cc, 'tests', 'rapports', 'rapport_tests_3.json'), json.dumps(dict(verdict='echec', unitaires=dict(echecs=2), fumee=dict(echecs=0))))
        c, s, J6 = auditer(R, outil, rev); self.assertEqual(c, 1, s)
        self.assertIn(('A16', 'bloquant'), codes(J6))
        # 7. --complet : tout réexaminé, comme un premier audit
        c, s, J7 = auditer(R, outil, rev, '--complet'); self.assertEqual(c, 1, s)
        self.assertTrue(J7['arbre']['premier']); self.assertEqual(J7['reexamines']['outils'], 6); self.assertEqual(J7['reexamines']['travaux'], 2)
        self.assertEqual(len(glob.glob(os.path.join(rev, 'etat', 'etat_audit_essai_*.json'))), 7)
        self.assertNotIn('\n', ''.join(k['message'] for k in J7['constats']))


if __name__ == '__main__':
    unittest.main()
