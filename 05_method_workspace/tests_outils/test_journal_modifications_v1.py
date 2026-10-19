"""Tests de journal_modifications_v1 : réduction d'une modification aux mots qui changent, mots d'origine conservés (plus longue
sous-suite commune), entrée D14 par point (mandat, verdict, problème, solution, modification, paragraphe inséré, texte d'origine),
bilan (opérations par type, mots insérés et supprimés, verdicts), contrôles de l'essai, réponses aux fils, jugements des écarts,
questions pour l'auteur ; sortie versionnée sans nouvelle version si le contenu ne change pas ; usage sans argument (code 2)."""
import os, json, unittest, contextlib, io
from aide_tests_v2 import dossier_essai, importer_version
import cc_lib_v4 as L4

JM = importer_version('journal_modifications', 1)
MODULE = '''POINTS = [dict(id="X-P001", sources=["F12", "DR-02 ¶5"], point="Renvoi cassé vers le §2.5.", demande="Rediriger le renvoi.", verdict="A_CORRIGER",
                    raison="Le contenu est au §5.8.", ops=["X-M001", "X-M002"])]
OPS = [dict(id="X-M001", type="remplacer", point="X-P001", cible="AAAA0001", couples=[("(§2.5)", "(§5.8)")]),
       dict(id="X-M002", type="inserer_apres", point="X-P001", ref="AAAA0001", texte="Tableau 1. Légende.")]
REPONSES = {"12": "Fait : renvoi corrigé."}
'''


class Fonctions(unittest.TestCase):
    def test_reduire_et_conserves(self):
        self.assertEqual(JM.reduire('le renvoi (§2.5) reste', 'le renvoi (§5.8) reste'), ('(§2.5)', '(§5.8)'))
        self.assertEqual(JM.reduire('une phrase complète.', 'une phrase complète. Ajout.'), ('', 'Ajout.'))
        self.assertEqual(JM.conserves('a b c d', 'a x c d'), (3, 4))
        self.assertEqual(JM.conserves('', 'a'), (0, 0))


class Journal(unittest.TestCase):
    def setUp(self):
        self.d = dossier_essai('journal_modifications'); sauve = L4.RACINE_CC
        self.addCleanup(lambda: setattr(L4, 'RACINE_CC', sauve)); L4.RACINE_CC = self.d
        with open(os.path.join(self.d, 'ops_x_v1.py'), 'w', encoding='utf-8') as g: g.write(MODULE)
        self.j = os.path.join(self.d, 'essai_journal.json')
        with open(self.j, 'w', encoding='utf-8') as g:
            json.dump(dict(source='/x/Rapport_v1.docx', modules='ops_x_v1', auteur='Passe - Claude', date='2026-10-15T21:00:00Z',
                           operations=[dict(id='X-M001', type='remplacer', point='X-P001', paraId='AAAA0001', avant='Voir le détail (§2.5) ici.', apres='Voir le détail (§5.8) ici.'),
                                       dict(id='X-M002', type='inserer_apres', point='X-P001', paraId='BBBB0002', texte='Tableau 1. Légende.')],
                           reponses=[dict(fil='12', texte='Fait : renvoi corrigé.')]), g)
        for n, c in (('bilan.json', dict(ecarts=[], nouveaux_problemes=0, constats_rev1_resolus=3, bilan='conforme')),
                     ('jug.json', dict(jugements={'D-1': dict(verdict='conforme', motif='Données : déjà traité.')}))):
            with open(os.path.join(self.d, n), 'w', encoding='utf-8') as g: json.dump(c, g)
        with open(os.path.join(self.d, 'q.md'), 'w', encoding='utf-8') as g: g.write('- Renuméroter les sections ?')

    def lancer(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = JM.main([self.j, self.d, os.path.join(self.d, 'sortie', 'Journal_x.md'), '--titre', 'Journal X', '--bilan', os.path.join(self.d, 'bilan.json'),
                            '--jugements', os.path.join(self.d, 'jug.json'), '--questions', os.path.join(self.d, 'q.md')])
        return code, out.getvalue()

    def test_journal_complet(self):
        code, out = self.lancer(); self.assertEqual(code, 0)
        f = os.path.join(self.d, 'sortie', 'Journal_x_v1.md'); t = open(f, encoding='utf-8').read()
        for attendu in ('# Journal X', '#### X-P001', '*Mandat* : F12, DR-02 ¶5. *Verdict* : A_CORRIGER.', '- **Problème** : Renvoi cassé vers le §2.5.',
                        '- **Modification** : « (§2.5) » → « (§5.8) »', '- **Paragraphe inséré** : « Tableau 1. Légende. »',
                        "- **Texte d'origine** : 4 des 5 mots conservés (80 %)", '| Opérations | 2 (inserer_apres 1, remplacer 1) |',
                        '| Mots insérés / supprimés | 4 / 1 |', '| Bilan | conforme |', '| 12 | Fait : renvoi corrigé. |',
                        '| D-1 | conforme | Données : déjà traité. |', '- Renuméroter les sections ?'):
            self.assertIn(attendu, t)
        code, out = self.lancer(); self.assertIn('(inchangé)', out)
        self.assertFalse(os.path.exists(os.path.join(self.d, 'sortie', 'Journal_x_v2.md')))

    def test_usage(self):
        with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(JM.main([]), 2)


if __name__ == '__main__':
    unittest.main()
