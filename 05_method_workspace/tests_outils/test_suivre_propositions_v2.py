"""Tests de suivre_propositions_v2 sur un espace fictif isolé (tests/_test_execution/, par dossier_essai) : le candidat est copié
dans l'arbre fictif (outils/suivre_propositions/) et son amorce y prend la racine de l'espace. (a) Non-régression : les cas de
test_suivre_propositions_v1 réécrits avec chemin() (événements et statut, refus d'un événement inconnu ; détection des skills ;
leçons et mémoire ; rapports versionnés seulement si leur contenu change ; importation sans doublon) ; commandes consigner,
detecter (brouillons par défaut), rapport, etat et leurs événements du journal ; amorce depuis candidat/. (b) Registre central des
dossiers : tous les dossiers de l'espace fictif (sauf outils) renommés par outils/_gestion/chemins_v1.json ; les mêmes cas rejoués :
propositions, brouillons de skills, leçons, mémoire et journal dans les dossiers renommés, aucun dossier créé sous son ancien nom.
La racine de cc_lib_v4 (journal) est celle de l'espace fictif le temps de chaque test : aucune écriture hors de tests/_test_execution/."""
import os, sys, io, glob, json, shutil, itertools, contextlib, importlib.util, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, chemin, chemins, RACINE_CC
import cc_lib_v4 as L4

OUTIL, V = 'suivre_propositions', 2
CANDIDAT = chemin_version(OUTIL, V); _n = itertools.count()
SKILL = '---\nname: {n}\ndescription: essai\n---\n\n# {n}\n\n{c}\n'


def w(f, texte):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, 'w', encoding='utf-8') as g: g.write(texte)


def lire(f):
    with open(f, encoding='utf-8') as g: return g.read()


def rel(f, cc): return os.path.relpath(f, cc).replace(os.sep, '/')


def charger(cc):
    """Copie le candidat dans l'arbre fictif (outils/<outil>/) et l'importe : son amorce prend cet espace pour racine."""
    d = os.path.join(cc, 'outils', OUTIL); os.makedirs(d, exist_ok=True)
    f = os.path.join(d, os.path.basename(CANDIDAT)); shutil.copyfile(CANDIDAT, f)
    s = importlib.util.spec_from_file_location(f'essai_{OUTIL}_{next(_n)}', f); m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m); return m


class NonRegression(unittest.TestCase):
    renommer = False

    def setUp(self):
        self.cc = dossier_essai(f'{OUTIL}_v{V}'); self.defaut = chemins(self.cc)   # noms par défaut (espace sans registre)
        if self.renommer:
            w(os.path.join(self.cc, 'outils', '_gestion', 'chemins_v1.json'),
              json.dumps(dict(chemins={k: v + '_renomme' for k, v in self.defaut.items() if k != 'outils'})))
        sauve = (L4.RACINE_CC, sys.path[:], sys.argv)

        def restaurer(): L4.RACINE_CC = sauve[0]; sys.path[:] = sauve[1]; sys.argv = sauve[2]
        self.addCleanup(restaurer)
        L4.RACINE_CC = self.cc                                                    # journal de cc_lib_v4 dans l'espace fictif
        self.SP = charger(self.cc)
        self.br = chemin('skills_atelier', racine=self.cc); self.inst = os.path.join(self.cc, 'installees')

    def main(self, *a):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): code = self.SP.main(list(a))
        return code, out.getvalue()

    def fichiers_suivis(self):
        """Leçons (v1 validée, v2 proposée), mémoire (v1, v2 approuvée) : cas de test_suivre_propositions_v1."""
        w(chemin('lecons', 'LC-001_v1.json', racine=self.cc), json.dumps(dict(id='LC-001', titre='t', statut='validee', date='2026-10-01')))
        w(chemin('lecons', 'LC-001_v2.json', racine=self.cc), json.dumps(dict(id='LC-001', titre='t2', statut='proposee', date='2026-10-02')))
        w(chemin('memoire', 'MEMOIRE_METHODOLOGIE_v1.md', racine=self.cc), 'm1')
        w(chemin('memoire', 'MEMOIRE_METHODOLOGIE_v2.md', racine=self.cc), 'm2')
        w(chemin('memoire', 'statut', 'v2_approbation.json', racine=self.cc), '{}')

    def test_evenements_et_statut(self):
        R = dict(propositions={}); SP = self.SP
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
        R = dict(propositions={}); self.SP.detecter_skills(R, self.br, [self.inst]); P = R['propositions']; st = self.SP.statut
        self.assertEqual(st(P['S-a-v2']), 'acceptee'); self.assertEqual(st(P['S-a-v1']), 'remplacee')
        self.assertEqual(st(P['S-b-v1']), 'a_confirmer'); self.assertEqual(st(P['S-c-v1']), 'proposee')
        self.assertEqual(P['S-a-v2']['fichier'], rel(os.path.join(self.br, 'a_SKILL_v2.md'), self.cc))
        self.assertEqual(self.SP.detecter_skills(R, self.br, [self.inst]), 0)                        # deuxième passage : rien de nouveau

    def test_lecons_et_memoire(self):
        self.fichiers_suivis(); R = dict(propositions={}); self.SP.detecter_fichiers(R); P = R['propositions']; st = self.SP.statut
        self.assertEqual(st(P['L-LC-001-v1']), 'remplacee'); self.assertEqual(st(P['L-LC-001-v2']), 'proposee')
        self.assertEqual(st(P['M-v1']), 'remplacee'); self.assertEqual(st(P['M-v2']), 'acceptee')
        self.assertEqual(P['L-LC-001-v1']['fichier'], rel(chemin('lecons', 'LC-001_v1.json', racine=self.cc), self.cc))
        self.assertEqual(P['M-v2']['fichier'], rel(chemin('memoire', 'MEMOIRE_METHODOLOGIE_v2.md', racine=self.cc), self.cc))
        self.assertEqual(self.SP.detecter_fichiers(R), 0)

    def test_rapports_et_importation(self):
        SP = self.SP; f = os.path.join(self.cc, 'amorce.json')
        w(f, json.dumps([dict(id='G-1', evenement='proposee', type='guide', objet='guide', date='2026-10-15 10:00'),
                         dict(id='G-1', evenement='modification_demandee', note='« plus court »', date='2026-10-15 11:00')]))
        self.assertEqual(self.main('importer', f)[0], 0); self.assertEqual(self.main('importer', f)[0], 0)   # sans doublon
        R = SP.charger(); self.assertEqual(len(R['propositions']['G-1']['evenements']), 2)
        (fi, c1), (fa, c2) = SP.rapport(R); self.assertTrue(c1 and c2)
        self.assertEqual({os.path.dirname(fi), os.path.dirname(fa)}, {chemin('propositions', racine=self.cc)})
        self.assertIn('modification demandée', lire(fi))
        (fi2, c3), (fa2, c4) = SP.rapport(R); self.assertFalse(c3 or c4); self.assertEqual(fi, fi2)   # contenu inchangé : pas de nouvelle version
        SP.ajouter(R, 'G-1', 'acceptee'); SP.sauver(R); (fi3, c5), _ = SP.rapport(SP.charger())
        self.assertTrue(c5); self.assertNotEqual(fi3, fi); self.assertNotIn('G-1', lire(fi3))   # clos : hors de l'index
        self.assertEqual(self.main()[0], 2)

    def test_commandes_et_journal(self):
        w(os.path.join(self.br, 'a_SKILL_v1.md'), SKILL.format(n='a', c='un')); w(os.path.join(self.inst, 'a', 'SKILL.md'), SKILL.format(n='a', c='un'))
        self.fichiers_suivis(); P = chemin('propositions', racine=self.cc)
        code, out = self.main('detecter', '--skills', self.inst)                                   # brouillons : dossier par défaut
        self.assertEqual(code, 0); self.assertIn(os.path.join(P, 'registre_propositions_v1.json'), out)
        R = self.SP.charger()['propositions']; st = self.SP.statut
        self.assertEqual((st(R['S-a-v1']), st(R['L-LC-001-v1']), st(R['M-v2'])), ('acceptee', 'remplacee', 'acceptee'))
        self.assertEqual(self.main('consigner', 'G-1', 'proposee', '--type', 'guide', '--objet', 'un guide')[0], 0)
        self.assertEqual(self.main('rapport'), (0, os.path.join(P, 'INDEX_v1.md') + '\n' + os.path.join(P, 'AUDIT_v1.md') + '\n'))
        self.assertIn('G-1', self.main('etat')[1])
        E = [json.loads(lire(x)) for x in glob.glob(chemin('journal', '*', '*.json', racine=self.cc))]
        self.assertEqual(sorted(e['type'] for e in E), ['consigner', 'detecter', 'etat', 'rapport'])
        self.assertEqual({(e['outil'], e['version']) for e in E}, {(OUTIL, V)})

    def test_amorce_depuis_candidat(self):
        m = importer_version(OUTIL, V, alias=f'essai_{OUTIL}_{next(_n)}')                        # rien n'est écrit à l'import
        self.assertEqual((m.CC, m.DOSSIER, m.VERSION), (RACINE_CC, chemin('propositions', racine=RACINE_CC), V))


class RegistreCentral(NonRegression):
    """Mêmes cas, chaque dossier de l'espace renommé (clé -> <nom par défaut>_renomme)."""
    renommer = True

    def tearDown(self):
        anciens = set(self.defaut.values()) - {'outils'}
        self.assertEqual(sorted(d for d in os.listdir(self.cc) if d in anciens), [])          # rien sous un ancien nom

    def test_dossiers_renommes(self):
        self.assertEqual(self.SP.CC, self.cc); self.assertEqual(self.SP.DOSSIER, chemin('propositions', racine=self.cc))
        for d in (self.SP.DOSSIER, self.br, chemin('lecons', racine=self.cc), chemin('memoire', racine=self.cc), chemin('journal', racine=self.cc)):
            self.assertTrue(os.path.basename(d).endswith('_renomme'), d)
        w(os.path.join(self.br, 'a_SKILL_v1.md'), SKILL.format(n='a', c='un')); self.fichiers_suivis()
        self.main('detecter', '--skills', self.inst); self.main('rapport')
        R = self.SP.charger()['propositions']
        self.assertEqual(sorted(R), ['L-LC-001-v1', 'L-LC-001-v2', 'M-v1', 'M-v2', 'S-a-v1'])        # lus dans les dossiers renommés
        self.assertTrue(all(p['fichier'].split('/')[0].endswith('_renomme') for p in R.values()))
        self.assertEqual(sorted(os.listdir(self.SP.DOSSIER)), ['AUDIT_v1.md', 'INDEX_v1.md', 'registre_propositions_v1.json'])
        self.assertEqual(len(glob.glob(chemin('journal', '*', '*.json', racine=self.cc))), 2)


if __name__ == '__main__':
    unittest.main()
