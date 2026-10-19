"""Tests de suivre_propositions_v1 sur un espace fictif isolé : événements et statut, refus d'un événement inconnu ; détection des
skills (brouillon identique à la skill enregistrée : acceptée ; version antérieure : remplacée ; skill enregistrée différente de
tous les brouillons : à confirmer, une seule fois) ; leçons (statut du fichier) et mémoire (fichier d'approbation) ; rapports
versionnés seulement si leur contenu change ; importation sans doublon."""
import os, json, unittest, importlib.util
from aide_tests_v1 import dossier_essai, chemin_outil

spec = importlib.util.spec_from_file_location('suivre_propositions_essai', chemin_outil('suivre_propositions', 1))
SP = importlib.util.module_from_spec(spec); spec.loader.exec_module(SP)
SKILL = '---\nname: {n}\ndescription: essai\n---\n\n# {n}\n\n{c}\n'


def w(chemin, texte):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, 'w', encoding='utf-8') as g: g.write(texte)


class Espace(unittest.TestCase):
    def setUp(self):
        self.cc = dossier_essai('suivre_propositions'); self._sauve = (SP.CC, SP.DOSSIER)
        SP.CC, SP.DOSSIER = self.cc, os.path.join(self.cc, 'propositions_a_reviser')
        self.br = os.path.join(self.cc, 'skills_propositions'); self.inst = os.path.join(self.cc, 'installees')

    def tearDown(self): SP.CC, SP.DOSSIER = self._sauve

    def test_evenements_et_statut(self):
        R = dict(propositions={})
        SP.ajouter(R, 'X-1', 'proposee', 'guide', 'un guide'); self.assertEqual(SP.statut(R['propositions']['X-1']), 'proposee')
        SP.ajouter(R, 'X-1', 'modification_demandee', note='plus court'); self.assertEqual(SP.statut(R['propositions']['X-1']), 'modification_demandee')
        SP.ajouter(R, 'X-1', 'presentee'); self.assertEqual(SP.statut(R['propositions']['X-1']), 'modification_demandee')   # présenter ne clôt rien
        SP.ajouter(R, 'X-1', 'acceptee'); self.assertEqual(SP.statut(R['propositions']['X-1']), 'acceptee')
        with self.assertRaises(SystemExit): SP.ajouter(R, 'X-1', 'approuvee_par_claude')
        self.assertFalse(SP.ajouter(R, 'X-1', 'acceptee', unique=True))

    def test_detection_des_skills(self):
        w(os.path.join(self.br, 'a_SKILL_v1.md'), SKILL.format(n='a', c='un'))
        w(os.path.join(self.br, 'a_SKILL_v2.md'), SKILL.format(n='a', c='deux'))
        w(os.path.join(self.br, 'b_SKILL_v1.md'), SKILL.format(n='b', c='brouillon'))
        w(os.path.join(self.br, 'c_SKILL_v1.md'), SKILL.format(n='c', c='jamais enregistrée'))
        w(os.path.join(self.inst, 'a', 'SKILL.md'), SKILL.format(n='a', c='deux').replace('description: essai', 'description: autre'))   # en-tête différent : ignoré
        w(os.path.join(self.inst, 'b', 'SKILL.md'), SKILL.format(n='b', c='modifiée par l’utilisateur'))
        R = dict(propositions={}); SP.detecter_skills(R, self.br, [self.inst]); P = R['propositions']
        self.assertEqual(SP.statut(P['S-a-v2']), 'acceptee'); self.assertEqual(SP.statut(P['S-a-v1']), 'remplacee')
        self.assertEqual(SP.statut(P['S-b-v1']), 'a_confirmer'); self.assertEqual(SP.statut(P['S-c-v1']), 'proposee')
        n = SP.detecter_skills(R, self.br, [self.inst]); self.assertEqual(n, 0)                     # deuxième passage : rien de nouveau

    def test_lecons_et_memoire(self):
        w(os.path.join(self.cc, 'lecons', 'LC-001_v1.json'), json.dumps(dict(id='LC-001', titre='t', statut='validee', date='2026-10-01')))
        w(os.path.join(self.cc, 'lecons', 'LC-001_v2.json'), json.dumps(dict(id='LC-001', titre='t2', statut='proposee', date='2026-10-02')))
        w(os.path.join(self.cc, 'memoire', 'MEMOIRE_METHODOLOGIE_v1.md'), 'm1'); w(os.path.join(self.cc, 'memoire', 'MEMOIRE_METHODOLOGIE_v2.md'), 'm2')
        w(os.path.join(self.cc, 'memoire', 'statut', 'v2_approbation.json'), '{}')
        R = dict(propositions={}); SP.detecter_fichiers(R); P = R['propositions']
        self.assertEqual(SP.statut(P['L-LC-001-v1']), 'remplacee'); self.assertEqual(SP.statut(P['L-LC-001-v2']), 'proposee')
        self.assertEqual(SP.statut(P['M-v1']), 'remplacee'); self.assertEqual(SP.statut(P['M-v2']), 'acceptee')

    def test_rapports_et_importation(self):
        f = os.path.join(self.cc, 'amorce.json')
        w(f, json.dumps([dict(id='G-1', evenement='proposee', type='guide', objet='guide', date='2026-10-15 10:00'),
                         dict(id='G-1', evenement='modification_demandee', note='« plus court »', date='2026-10-15 11:00')]))
        self.assertEqual(SP.main(['importer', f]), 0); self.assertEqual(SP.main(['importer', f]), 0)        # sans doublon
        R = SP.charger(); self.assertEqual(len(R['propositions']['G-1']['evenements']), 2)
        (fi, c1), (fa, c2) = SP.rapport(R); self.assertTrue(c1 and c2)
        self.assertIn('modification demandée', open(fi, encoding='utf-8').read())
        (fi2, c3), (fa2, c4) = SP.rapport(R); self.assertFalse(c3 or c4); self.assertEqual(fi, fi2)   # contenu inchangé : pas de nouvelle version
        SP.ajouter(R, 'G-1', 'acceptee'); SP.sauver(R); (fi3, c5), _ = SP.rapport(SP.charger())
        self.assertTrue(c5); self.assertNotEqual(fi3, fi); self.assertNotIn('G-1', open(fi3, encoding='utf-8').read())   # clos : hors de l'index
        self.assertEqual(SP.main([]), 2)


if __name__ == '__main__':
    unittest.main()
