"""Tests de preclasser_revision_v1 (pré-classement déterministe des points d'une réévaluation de révision Word), sur des entrées minimales écrites
dans le dossier d'essai (points_<bloc>_v1.json, dossier_<bloc>_v1.md, vue_rev1_complete_v1.txt, alignement du transcript). Testés :
- chaque règle dure sur un bloc : AUTO-TDM (lignes de table des matières), AUTO-AUTEUR, AUTO-NOTE-AUTEUR, AUTO-REPERE (doublon d'un segment),
  AUTO-PERIME (signalement dont les formes n'existent plus), AUTO-COUVERTURE (--couverture) ; le résidu (points non classés) n'est pas touché ;
- modules auto_<bloc>_v1.py exécutables (POINTS, OPS, REPONSES), décompte preclassement_v1.json (par règle, par bloc, part automatique), résumé
  imprimé identique au fichier, événement du journal redirigé vers le dossier d'essai ;
- couverture par défaut (23) ; absence de table des matières dans la vue ;
- refus : sortie déjà présente (jamais écrasée), bloc sans fichier de points ; ligne de commande sans argument (échec) ;
- défauts connus (expectedFailure) : option --auteur ignorée, texte altéré par la conversion JSON -> Python, événement écrit dans un dossier
  de journal figé au lieu de celui du registre des chemins."""
import os, sys, io, re, json, glob, contextlib, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, OUTILS
import cc_lib_v1 as L1
import cc_lib_v4 as L4

PR = importer_version('preclasser_revision', 1); OUTIL = chemin_version('preclasser_revision', 1)
COLLEGUE = 'Collègue A'
# Étiquette d'auteur que la règle AUTO-AUTEUR reconnaît : elle est écrite en dur dans l'outil, on la lit là plutôt que de la recopier ici.
AUTEUR = re.search(r"get\('auteurs'\) == \['([^']+)'\]", open(OUTIL, encoding='utf-8').read()).group(1)
BLOCS = ['B%d' % k for k in range(1, 10)]

VUE = ['Rapport d’essai', 'Statut : brouillon', 'Préambule', 'Table des matières', '1. Contexte\t3', '2. Méthode\t4', 'Contexte',
       'Le taux est de 5 % selon la mesure.', 'Texte révisé par l’auteur seul.', 'Texte révisé par un collègue.', 'Texte avec commentaire.']
ALIGNEMENT = [dict(id='S1', debut='00:01:00', fin='00:02:00'), dict(id='S2', debut='00:05:00', fin='00:06:00')]


def pts_b1():
    return [dict(id='B1-P01', type='paragraphe_revise', index=0, auteurs=[COLLEGUE]),                       # couverture (--couverture 1)
            dict(id='B1-P02', type='paragraphe_revise', index=1, auteurs=[COLLEGUE]),                       # couverture
            dict(id='B1-P03', type='paragraphe_revise', index=4, auteurs=[COLLEGUE]),                       # ligne de table des matières
            dict(id='B1-P04', type='paragraphe_revise', index=5, auteurs=[COLLEGUE, AUTEUR]),               # ligne de table des matières
            dict(id='B1-P05', type='paragraphe_revise', index=8, auteurs=[AUTEUR]),                         # révision de l'auteur seul
            dict(id='B1-P06', type='paragraphe_revise', index=9, auteurs=[COLLEGUE]),                       # résidu : autre auteur
            dict(id='B1-P07', type='paragraphe_revise', index=10, auteurs=[AUTEUR], commentaires=['c1']),   # résidu : l'auteur, mais avec un commentaire
            dict(id='B1-F21', type='fil_auteur', fil='21'),                                                 # note de l'auteur sans réponse
            dict(id='B1-F22', type='fil_auteur', fil='22'),                                                 # résidu : réponse « CC-rev1 » dans le fil
            dict(id='B1-F23', type='fil_auteur', fil='23', reponse_rev1='Traité'),                          # résidu : réponse fournie dans le point
            dict(id='B1-S1', type='segment_transcript', index=None),                                        # segment (aucune règle)
            dict(id='B1-R31', type='repere_transcript', fil='31'),                                          # repère dans le segment S1, présent
            dict(id='B1-R32', type='repere_transcript', fil='32'),                                          # résidu : hors de tout segment
            dict(id='B1-R33', type='repere_transcript', fil='33'),                                          # résidu : segment S2 absent du bloc
            dict(id='B1-G41', type='signalement_rev1', fil='41', index=7),                                  # signalement périmé
            dict(id='B1-G42', type='signalement_rev1', fil='42', index=7)]                                  # résidu : la forme signalée existe encore


def fils(num, role, texte): return f'### Fil {num} ({role}) fil de test\n{texte}\n\n'


DOSSIER_B1 = ('## Bloc B1\n\n' + fils(21, 'auteur', 'Note sans réponse.') + fils(22, 'auteur', 'Note avec réponse. CC-rev1 : traité.')
              + fils(23, 'auteur', 'Note.') + fils(31, 'repere', 'Repère : transcript 00:01:30 — fragment.')
              + fils(32, 'repere', 'Repère : transcript 00:03:00 — fragment.') + fils(33, 'repere', 'Repère : transcript 00:05:30 — fragment.')
              + fils(41, 'signalement', 'Signalement : « 4 % » → « 5 % » dans la mesure.')
              + fils(42, 'signalement', 'Signalement : « 5 % » → « 6 % » dans la mesure.') + '## Fin\n')


class Preclasser(unittest.TestCase):
    def setUp(self):
        self.d = dossier_essai('preclasser_revision_v1'); self.cc = os.path.join(self.d, 'espace')
        sauve = (L4.RACINE_CC, L1.JOURNAL, os.environ.get('CC_BANC'))

        def restaurer():
            L4.RACINE_CC, L1.JOURNAL = sauve[0], sauve[1]
            if sauve[2] is None: os.environ.pop('CC_BANC', None)
            else: os.environ['CC_BANC'] = sauve[2]
        self.addCleanup(restaurer)
        L4.RACINE_CC = self.cc; L1.JOURNAL = os.path.join(self.cc, 'evenements')     # événements : dans le dossier d'essai
        self.dd = self.entrees()

    def entrees(self, nom='dossiers_agents', vue=VUE, b1_pts=None, b1_fils=DOSSIER_B1, manque=None):
        dd = os.path.join(self.d, nom); os.makedirs(dd)
        with open(os.path.join(dd, 'vue_rev1_complete_v1.txt'), 'w', encoding='utf-8') as f:
            f.write(''.join(f'{i} | PID{i:04d} | Section | {t}\n' for i, t in enumerate(vue)))
        pts = {B: [] for B in BLOCS}
        pts['B1'] = pts_b1() if b1_pts is None else b1_pts
        pts['B2'] = [dict(id='B2-P01', type='paragraphe_revise', index=8, auteurs=[AUTEUR]), dict(id='B2-P02', type='paragraphe_revise', index=9, auteurs=[COLLEGUE])]
        for B in BLOCS:
            if B == manque: continue
            with open(os.path.join(dd, f'points_{B}_v1.json'), 'w', encoding='utf-8') as f: json.dump(pts[B], f, ensure_ascii=False)
            with open(os.path.join(dd, f'dossier_{B}_v1.md'), 'w', encoding='utf-8') as f: f.write(b1_fils if B == 'B1' else '## Fin\n')
        self.al = os.path.join(self.d, 'alignement_transcript.json')
        with open(self.al, 'w', encoding='utf-8') as f: json.dump(ALIGNEMENT, f)
        return dd

    def lancer(self, *extra, sortie='modules', dd=None):
        sauve = sys.argv; sys.argv = [OUTIL, dd or self.dd, self.al, os.path.join(self.d, sortie), *extra]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out): PR.main()
        finally: sys.argv = sauve
        return out.getvalue()

    def module(self, B, sortie='modules'):
        ns = {}
        with open(os.path.join(self.d, sortie, f'auto_{B}_v1.py'), encoding='utf-8') as f: exec(f.read(), ns)
        return ns

    def bilan(self, sortie='modules'):
        with open(os.path.join(self.d, sortie, 'preclassement_v1.json'), encoding='utf-8') as f: return json.load(f)

    def test_regles_dures_du_bloc(self):
        self.lancer('--couverture', '1'); ns = self.module('B1'); P = ns['POINTS']
        self.assertEqual([p['regle_auto'] for p in P], ['AUTO-TDM', 'AUTO-TDM', 'AUTO-AUTEUR', 'AUTO-NOTE-AUTEUR', 'AUTO-REPERE', 'AUTO-PERIME', 'AUTO-COUVERTURE'])
        self.assertEqual([p['id'] for p in P], [f'B1-A{k:03d}' for k in range(1, 8)])
        par = {p['regle_auto']: p for p in P}
        self.assertEqual([p['sources'] for p in P[:2]], [['B1-P03'], ['B1-P04']]); self.assertEqual(P[0]['verdict'], 'SANS_OBJET')
        self.assertIn(f'{COLLEGUE}, {AUTEUR}', P[1]['point'])                        # auteurs listés dans l'énoncé du point
        self.assertEqual((par['AUTO-AUTEUR']['sources'], par['AUTO-AUTEUR']['verdict']), (['B1-P05'], 'CONFORME'))
        self.assertEqual((par['AUTO-NOTE-AUTEUR']['sources'], par['AUTO-NOTE-AUTEUR']['verdict']), (['B1-F21'], 'SANS_OBJET'))
        self.assertEqual((par['AUTO-REPERE']['sources'], par['AUTO-REPERE']['verdict']), (['B1-R31'], 'SANS_OBJET'))
        self.assertIn('segment S1', par['AUTO-REPERE']['raison']); self.assertEqual(par['AUTO-REPERE']['demande'], 'Voir B1-S1.')
        self.assertEqual((par['AUTO-PERIME']['sources'], par['AUTO-PERIME']['verdict']), (['B1-G41'], 'SANS_OBJET'))
        self.assertIn('« 4 % » → « 5 % »', par['AUTO-PERIME']['point'])
        c = par['AUTO-COUVERTURE']
        self.assertEqual((c['sources'], c['verdict']), (['B1-P01', 'B1-P02'], 'DECISION_AUTEUR')); self.assertIn('¶0 à 1', c['point']); self.assertTrue(c['question'])
        classes = {s for p in P for s in p['sources']}                             # le résidu n'est pas classé
        for residu in ('B1-P06', 'B1-P07', 'B1-F22', 'B1-F23', 'B1-S1', 'B1-R32', 'B1-R33', 'B1-G42'): self.assertNotIn(residu, classes, residu)
        self.assertTrue(all(p['ops'] == [] and p['statut_rev1_vrai'] == 'sans_objet' for p in P))

    def test_bilan_modules_resume_et_journal(self):
        out = self.lancer('--couverture', '1'); b = self.bilan()
        for B in BLOCS:
            ns = self.module(B); self.assertEqual((ns['OPS'], ns['REPONSES']), ([], {}), B)    # module de points exécutable
        self.assertEqual(self.module('B3')['POINTS'], [])
        self.assertEqual(b['par_regle'], {'AUTO-TDM': 2, 'AUTO-AUTEUR': 2, 'AUTO-NOTE-AUTEUR': 1, 'AUTO-REPERE': 1, 'AUTO-PERIME': 1, 'AUTO-COUVERTURE': 2})
        self.assertEqual(b['par_bloc']['B1'], dict(points=16, auto=8)); self.assertEqual(b['par_bloc']['B2'], dict(points=2, auto=1))
        self.assertEqual(b['par_bloc']['B9'], dict(points=0, auto=0))
        self.assertEqual((b['total_points'], b['total_auto'], b['part_automatique']), (18, 9, 0.5))
        self.assertEqual(json.loads(out), b)                                       # résumé imprimé = fichier de décompte
        self.assertEqual(sorted(os.listdir(os.path.join(self.d, 'modules'))), sorted([f'auto_{B}_v1.py' for B in BLOCS] + ['preclassement_v1.json']))
        evts = glob.glob(os.path.join(self.cc, '*', '*', '*_preclasser_revision_v1_*.json')); self.assertEqual(len(evts), 1)
        with open(evts[0], encoding='utf-8') as f: e = json.load(f)
        self.assertEqual((e['outil'], e['version'], e['type']), ('preclasser_revision', 1, 'preclassement')); self.assertEqual(e['donnees']['total_auto'], 9)

    def test_couverture_par_defaut(self):
        self.lancer(); P = self.module('B1')['POINTS']; b = self.bilan()               # seuil 23 : tous les paragraphes révisés (¶0 à ¶10) sont de la couverture
        c = [p for p in P if p['regle_auto'] == 'AUTO-COUVERTURE']; self.assertEqual(len(c), 1)
        self.assertEqual(c[0]['sources'], [f'B1-P0{k}' for k in range(1, 8)]); self.assertIn('¶0 à 23', c[0]['point'])
        self.assertEqual(sorted(p['regle_auto'] for p in P if p is not c[0]), ['AUTO-NOTE-AUTEUR', 'AUTO-PERIME', 'AUTO-REPERE'])   # TDM et auteur absorbés
        self.assertEqual(b['par_regle']['AUTO-COUVERTURE'], 7 + 2); self.assertNotIn('AUTO-TDM', b['par_regle'])

    def test_sans_table_des_matieres(self):
        dd = self.entrees('dossiers_sans_tdm', vue=[('Sommaire' if t == 'Table des matières' else t) for t in VUE])
        self.lancer('--couverture', '1', dd=dd, sortie='modules_sans_tdm'); b = self.bilan('modules_sans_tdm')
        self.assertNotIn('AUTO-TDM', b['par_regle'])                               # sans repère « Table des matières », ses lignes restent au résidu
        self.assertEqual(b['par_bloc']['B1']['auto'], 6)

    def test_refus_ecrasement_et_bloc_manquant(self):
        self.lancer('--couverture', '1')
        avant = {f: open(os.path.join(self.d, 'modules', f), 'rb').read() for f in os.listdir(os.path.join(self.d, 'modules'))}
        with self.assertRaises(FileExistsError): self.lancer('--couverture', '1')    # les sorties existantes ne sont jamais réécrites
        self.assertEqual(avant, {f: open(os.path.join(self.d, 'modules', f), 'rb').read() for f in os.listdir(os.path.join(self.d, 'modules'))})
        dd = self.entrees('dossiers_incomplets', manque='B5')
        with self.assertRaises(FileNotFoundError): self.lancer(dd=dd, sortie='modules_incomplets')

    def env(self): return dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS]))

    def test_ligne_de_commande_sans_argument(self):
        r = subprocess.run([sys.executable, OUTIL], capture_output=True, text=True, env=self.env())
        self.assertNotEqual(r.returncode, 0); self.assertIn('IndexError', r.stderr)   # état actuel : trace Python (pas de message d'usage)

    @unittest.expectedFailure
    def test_option_auteur(self):
        # Défaut : l'option --auteur est lue mais jamais utilisée ; la règle AUTO-AUTEUR compare à une étiquette écrite en dur dans l'outil.
        self.lancer('--couverture', '1', '--auteur', COLLEGUE); P = self.module('B1')['POINTS']
        self.assertIn('AUTO-AUTEUR', [p['regle_auto'] for p in P if p['sources'] == ['B1-P06']])

    @unittest.expectedFailure
    def test_texte_non_altere_par_la_conversion(self):
        # Défaut : le module est produit par remplacement de texte (': true' -> ': True', ': null' -> ': None') sur tout le JSON, y compris
        # dans le contenu des phrases : un signalement citant « état: true » est réécrit « état: True ».
        pts = pts_b1() + [dict(id='B1-G43', type='signalement_rev1', fil='43', index=7)]
        dd = self.entrees('dossiers_litteral', b1_pts=pts, b1_fils=DOSSIER_B1.replace('## Fin\n', fils(43, 'signalement', 'Signalement : « état: true » → « 5 % ».') + '## Fin\n'))
        self.lancer('--couverture', '1', dd=dd, sortie='modules_litteral'); P = self.module('B1', 'modules_litteral')['POINTS']
        self.assertIn('« état: true » → « 5 % »', [p['point'] for p in P if p['sources'] == ['B1-G43']][0])

    @unittest.expectedFailure
    def test_journal_du_registre(self):
        # Défaut : evenement vient de cc_lib_v1 et écrit dans son dossier de journal figé (ancien nom), pas dans celui du registre des chemins (cc_lib_v4).
        sonde = L4.evenement('sonde', 0, 'essai', {}); registre = os.path.dirname(os.path.dirname(sonde))
        self.lancer('--couverture', '1')
        self.assertTrue(glob.glob(os.path.join(registre, '*', '*_preclasser_revision_v1_*.json')))


if __name__ == '__main__':
    unittest.main()
