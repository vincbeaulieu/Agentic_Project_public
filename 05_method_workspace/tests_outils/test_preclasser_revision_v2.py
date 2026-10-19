"""Tests de preclasser_revision_v2. (a) Non-régression : toute la suite v1 (règles dures AUTO-TDM, AUTO-AUTEUR, AUTO-NOTE-AUTEUR, AUTO-REPERE,
AUTO-PERIME, AUTO-COUVERTURE, modules, décompte, refus) est rejouée sur la version 2 (module et exécutable remplacés, puis rétablis) ; la règle
AUTO-AUTEUR dépend désormais de --auteur, que la rejouée passe d'office avec une étiquette d'essai. Les trois tests de défaut connu (expectedFailure)
et les deux tests qui figeaient l'état d'avant (trace Python sans argument, événement nommé v1) sont remplacés par leurs versions corrigées.
(b) Corrections de la v2 : --auteur utilisée (et règle inactive sans lui, aucune étiquette de personne dans l'outil) ; module POINTS écrit par repr()
sans altérer les phrases citées (« état: true », « sortie: null », « test: false ») et en gardant les types Python (None) ; événement écrit par
cc_lib_v4 dans le dossier du registre des chemins ; sans argument : ligne USAGE de l'en-tête et code 2."""
import os, re, sys, glob, json, subprocess, unittest
from aide_tests_v2 import chemin_version, importer_version
import test_preclasser_revision_v1 as T1

PR2 = importer_version('preclasser_revision', 2, 'preclasser_revision_v2_essai'); OUTIL2 = chemin_version('preclasser_revision', 2)
AUTEUR = 'Auteur d’essai'                    # étiquette d'auteur d'essai, transmise par --auteur


class SurV2:
    """Rejoue une classe de la suite v1 avec la version 2 (module, exécutable, étiquette d'auteur), puis restaure."""
    @classmethod
    def setUpClass(cls):
        cls._sauve = (T1.PR, T1.OUTIL, T1.AUTEUR); T1.PR, T1.OUTIL, T1.AUTEUR = PR2, OUTIL2, AUTEUR

    @classmethod
    def tearDownClass(cls):
        T1.PR, T1.OUTIL, T1.AUTEUR = cls._sauve

    def lancer(self, *extra, **kw):
        if '--auteur' not in extra: extra += ('--auteur', T1.AUTEUR)
        return super().lancer(*extra, **kw)


class PreclasserV1SurV2(SurV2, T1.Preclasser):
    def test_option_auteur(self): pass                               # remplacé par Corrige.test_option_auteur
    def test_texte_non_altere_par_la_conversion(self): pass          # remplacé par Corrige.test_texte_non_altere_par_la_conversion
    def test_journal_du_registre(self): pass                         # remplacé par Corrige.test_journal_du_registre
    def test_ligne_de_commande_sans_argument(self): pass             # remplacé par Corrige.test_ligne_de_commande_sans_argument
    def test_bilan_modules_resume_et_journal(self): pass             # remplacé par Corrige.test_bilan_modules_resume_et_journal (événement v2)


class Corrige(SurV2, T1.Preclasser):
    def test_option_auteur(self):
        self.lancer('--couverture', '1', '--auteur', T1.COLLEGUE); P = self.module('B1')['POINTS']
        regle = {tuple(p['sources']): p['regle_auto'] for p in P}
        self.assertEqual(regle[('B1-P06',)], 'AUTO-AUTEUR')                      # la valeur de --auteur fait foi
        self.assertNotEqual(regle.get(('B1-P05',)), 'AUTO-AUTEUR')                # l'ancienne étiquette n'est plus reconnue
        p06 = next(p for p in P if p['sources'] == ['B1-P06']); self.assertIn(T1.COLLEGUE, p06['point']); self.assertEqual(p06['verdict'], 'CONFORME')
        self.assertNotIn(('B1-P07',), regle)                                    # avec un commentaire : reste au résidu

    def test_sans_option_auteur_la_regle_est_inactive(self):
        T1.Preclasser.lancer(self, '--couverture', '1')                           # sans --auteur (la rejouée en ajoute d'office)
        P = self.module('B1')['POINTS']; b = self.bilan()
        self.assertNotIn('AUTO-AUTEUR', [p['regle_auto'] for p in P]); self.assertNotIn('AUTO-AUTEUR', b['par_regle'])
        self.assertIn('AUTO-NOTE-AUTEUR', b['par_regle'])                       # les autres règles ne dépendent pas de --auteur
        self.assertTrue(all('None' not in p['point'] and 'None' not in p['raison'] for p in P))

    def test_aucune_etiquette_de_personne_dans_l_outil(self):
        with open(OUTIL2, encoding='utf-8') as f: src = f.read()
        self.assertIsNone(re.search(r"get\('auteurs'\) == \['", src))           # plus de comparaison à un libellé écrit en dur
        self.assertIsNone(re.search(r"--auteur\s+\"[A-ZÉ][a-zé]+ [A-ZÉ]{3,}\"", src))   # ni exemple nominatif dans USAGE

    def test_texte_non_altere_par_la_conversion(self):
        pts = T1.pts_b1() + [dict(id='B1-G43', type='signalement_rev1', fil='43', index=7), dict(id='B1-G44', type='signalement_rev1', fil='44', index=7)]
        fils = T1.fils(43, 'signalement', 'Signalement : « état: true » → « 5 % ».') + T1.fils(44, 'signalement', 'Signalement : « sortie: null » → « 5 % » ; « test: false » → « 5 % ».')
        dd = self.entrees('dossiers_litteral', b1_pts=pts, b1_fils=T1.DOSSIER_B1.replace('## Fin\n', fils + '## Fin\n'))
        self.lancer('--couverture', '1', dd=dd, sortie='modules_litteral'); P = self.module('B1', 'modules_litteral')['POINTS']
        self.assertIn('« état: true » → « 5 % »', [p['point'] for p in P if p['sources'] == ['B1-G43']][0])
        self.assertIn('« sortie: null » → « 5 % » ; « test: false » → « 5 % »', [p['point'] for p in P if p['sources'] == ['B1-G44']][0])

    def test_types_python_conserves(self):
        self.lancer('--couverture', '1'); P = self.module('B1')['POINTS']
        self.assertTrue(all(p['question'] is None for p in P if p['regle_auto'] != 'AUTO-COUVERTURE'))      # null JSON -> None, pas le texte « null »
        with open(os.path.join(self.d, 'modules', 'auto_B1_v1.py'), encoding='utf-8') as f: src = f.read()
        self.assertNotIn(': null', src); self.assertNotIn(': true', src)       # source Python valide, sans reste de syntaxe JSON

    def test_journal_du_registre(self):
        sonde = T1.L4.evenement('sonde', 0, 'essai', {}); registre = os.path.dirname(os.path.dirname(sonde))
        self.lancer('--couverture', '1')
        self.assertTrue(glob.glob(os.path.join(registre, '*', '*_preclasser_revision_v2_*.json')))

    def test_bilan_modules_resume_et_journal(self):
        out = self.lancer('--couverture', '1'); b = self.bilan()
        for B in T1.BLOCS:
            ns = self.module(B); self.assertEqual((ns['OPS'], ns['REPONSES']), ([], {}), B)
        self.assertEqual(self.module('B3')['POINTS'], [])
        self.assertEqual(b['par_regle'], {'AUTO-TDM': 2, 'AUTO-AUTEUR': 2, 'AUTO-NOTE-AUTEUR': 1, 'AUTO-REPERE': 1, 'AUTO-PERIME': 1, 'AUTO-COUVERTURE': 2})
        self.assertEqual((b['total_points'], b['total_auto'], b['part_automatique']), (18, 9, 0.5))
        self.assertEqual(json.loads(out), b)
        self.assertEqual(sorted(os.listdir(os.path.join(self.d, 'modules'))), sorted([f'auto_{B}_v1.py' for B in T1.BLOCS] + ['preclassement_v1.json']))
        evts = glob.glob(os.path.join(self.cc, '*', '*', '*_preclasser_revision_v2_*.json')); self.assertEqual(len(evts), 1)
        with open(evts[0], encoding='utf-8') as f: e = json.load(f)
        self.assertEqual((e['outil'], e['version'], e['type']), ('preclasser_revision', 2, 'preclassement')); self.assertEqual(e['donnees']['total_auto'], 9)

    def test_ligne_de_commande_sans_argument(self):
        r = subprocess.run([sys.executable, OUTIL2], capture_output=True, text=True, env=self.env())
        self.assertEqual(r.returncode, 2); self.assertNotIn('Traceback', r.stderr)
        with open(OUTIL2, encoding='utf-8') as f: usage = re.search(r'(?m)^USAGE: .*$', f.read()).group(0)
        self.assertEqual(r.stdout.strip(), usage)
        r = subprocess.run([sys.executable, OUTIL2, 'a', 'b'], capture_output=True, text=True, env=self.env())      # moins de trois arguments
        self.assertEqual((r.returncode, r.stdout.strip()), (2, usage))


for _n in dir(T1.Preclasser):                       # Corrige hérite des aides de la suite v1, pas de ses tests (déjà rejoués ci-dessus)
    if _n.startswith('test_') and _n not in Corrige.__dict__: setattr(Corrige, _n, None)


if __name__ == '__main__':
    unittest.main()
