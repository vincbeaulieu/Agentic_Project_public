"""Tests de memoire_v2 sur un espace fictif isolé (tests/_test_execution/, par dossier_essai). (a) Non-régression : le cas de
test_memoire_v1 réécrit avec chemin() (une version non approuvée n'est jamais courante ; approbation avec citation obligatoire ;
alerte si le texte approuvé change) ; état ; dernière version approuvée ; refus (hors du dossier, non proposée, modifiée depuis la
proposition, citation vide) ; fichiers de statut immuables ; événements du journal. (b) Registre central des dossiers : tous les
dossiers de l'espace fictif (sauf outils) renommés par outils/_gestion/chemins_v1.json ; les mêmes cas rejoués : versions,
statuts et journal dans les dossiers renommés, aucun dossier créé sous son ancien nom. La racine de cc_lib_v4 (racine de l'outil
et du journal) est celle de l'espace fictif le temps de chaque test : aucune écriture hors de tests/_test_execution/."""
import os, sys, io, glob, json, hashlib, itertools, contextlib, unittest
from aide_tests_v2 import dossier_essai, importer_version, chemin, chemins
import cc_lib_v4 as L4

OUTIL, V = 'memoire', 2
_n = itertools.count()


def lire(f):
    with open(f, encoding='utf-8') as g: return g.read()


class NonRegression(unittest.TestCase):
    renommer = False

    def setUp(self):
        self.cc = dossier_essai(f'{OUTIL}_v{V}'); self.defaut = chemins(self.cc)   # noms par défaut (espace sans registre)
        if self.renommer:
            g = os.path.join(self.cc, 'outils', '_gestion'); os.makedirs(g)
            with open(os.path.join(g, 'chemins_v1.json'), 'w', encoding='utf-8') as f:
                json.dump(dict(chemins={k: v + '_renomme' for k, v in self.defaut.items() if k != 'outils'}), f)
        sauve = (L4.RACINE_CC, sys.path[:], sys.argv)

        def restaurer(): L4.RACINE_CC = sauve[0]; sys.path[:] = sauve[1]; sys.argv = sauve[2]
        self.addCleanup(restaurer)
        L4.RACINE_CC = self.cc                                                    # avant l'import : l'outil y lit sa racine
        self.M = importer_version(OUTIL, V, alias=f'essai_{OUTIL}_{next(_n)}')
        self.D = chemin('memoire', racine=self.cc); self.ST = os.path.join(self.D, 'statut')

    def version(self, n, texte):
        os.makedirs(self.D, exist_ok=True); f = os.path.join(self.D, f'MEMOIRE_METHODOLOGIE_v{n}.md')
        with open(f, 'w', encoding='utf-8') as g: g.write(texte)
        return f

    def lancer(self, *a):
        """main() avec ces arguments ; renvoie (code, sortie + message d'arrêt éventuel)."""
        sys.argv = [OUTIL] + list(a); out = io.StringIO(); msg = ''
        with contextlib.redirect_stdout(out):
            try: self.M.main(); code = 0
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
                if not isinstance(e.code, int) and e.code is not None: msg = str(e.code)
        return code, out.getvalue() + msg

    def test_cycle(self):                                                        # cas de test_memoire_v1
        f = self.version(1, '# v1\n')
        self.assertEqual(self.lancer('courant')[0], 1)                             # rien d'approuvé
        self.lancer('proposer', f); self.assertEqual(self.lancer('courant')[0], 1)
        self.assertNotEqual(self.lancer('approuver', '1')[0], 0)                   # citation obligatoire
        self.lancer('approuver', '1', '--citation', 'oui, approuvé'); code, out = self.lancer('courant')
        self.assertEqual(code, 0); self.assertEqual(out.strip(), f)
        with open(f, 'a', encoding='utf-8') as g: g.write('modifié\n')
        code, out = self.lancer('courant'); self.assertEqual(code, 2); self.assertIn('ALERTE', out)   # empreinte changée

    def test_etat(self):
        self.assertIn('aucune version', self.lancer('etat')[1])
        f1 = self.version(1, '# v1\n'); self.assertIn('v1 : non enregistrée — MEMOIRE_METHODOLOGIE_v1.md', self.lancer('etat')[1])
        self.lancer('proposer', f1); self.version(2, '# v2\n'); out = self.lancer('etat')[1]
        self.assertIn('v1 : proposée le ', out); self.assertIn('v2 : non enregistrée', out)
        self.lancer('approuver', '1', '--citation', 'oui'); self.assertIn('v1 : approuvée le ', self.lancer('etat')[1])

    def test_derniere_version_approuvee(self):
        f1, f2 = self.version(1, '# v1\n'), self.version(2, '# v2\n')
        self.lancer('proposer', f1); self.lancer('approuver', '1', '--citation', 'oui'); self.lancer('proposer', f2)
        self.assertEqual(self.lancer('courant')[1].strip(), f1)                    # v2 seulement proposée : jamais courante
        self.lancer('approuver', '2', '--citation', 'oui'); self.assertEqual(self.lancer('courant')[1].strip(), f2)

    def test_refus(self):
        dehors = os.path.join(self.cc, 'MEMOIRE_METHODOLOGIE_v5.md')
        with open(dehors, 'w', encoding='utf-8') as g: g.write('x\n')
        code, out = self.lancer('proposer', dehors); self.assertEqual(code, 1); self.assertIn(self.D, out)   # hors du dossier
        f = self.version(1, '# v1\n')
        code, out = self.lancer('approuver', '1', '--citation', 'oui'); self.assertEqual(code, 1); self.assertIn('non enregistrée', out)
        self.lancer('proposer', f)
        self.assertEqual(self.lancer('approuver', '1', '--citation', '   ')[0], 1)                         # citation vide
        with open(f, 'a', encoding='utf-8') as g: g.write('modifié\n')
        code, out = self.lancer('approuver', '1', '--citation', 'oui'); self.assertEqual(code, 1); self.assertIn('a changé', out)
        self.assertFalse(os.path.exists(os.path.join(self.ST, 'v1_approbation.json')))

    def test_statut_immuable_et_journal(self):
        f = self.version(1, '# v1\n')
        with open(f, 'rb') as g: h = hashlib.sha256(g.read()).hexdigest()
        self.lancer('proposer', f); self.lancer('approuver', '1', '--citation', 'oui, approuvé mot pour mot')
        P = json.loads(lire(os.path.join(self.ST, 'v1_proposition.json'))); A = json.loads(lire(os.path.join(self.ST, 'v1_approbation.json')))
        self.assertEqual((P['version'], P['fichier'], P['sha256']), (1, 'MEMOIRE_METHODOLOGIE_v1.md', h))
        self.assertEqual((A['sha256'], A['citation']), (h, 'oui, approuvé mot pour mot'))
        avant = lire(os.path.join(self.ST, 'v1_proposition.json'))
        with self.assertRaises(FileExistsError): self.lancer('proposer', f)         # statut immuable : jamais réécrit
        self.assertEqual(lire(os.path.join(self.ST, 'v1_proposition.json')), avant)
        E = [json.loads(lire(x)) for x in glob.glob(chemin('journal', '*', '*.json', racine=self.cc))]
        self.assertEqual(sorted((e['outil'], e['version'], e['type'], e['donnees']['version']) for e in E),
                         [(OUTIL, V, 'approbation', 1), (OUTIL, V, 'proposition', 1)])
        self.assertTrue(all(e['donnees'].get('banc') for e in E))


class RegistreCentral(NonRegression):
    """Mêmes cas, chaque dossier de l'espace renommé (clé -> <nom par défaut>_renomme)."""
    renommer = True

    def tearDown(self):
        anciens = set(self.defaut.values()) - {'outils'}
        self.assertEqual(sorted(d for d in os.listdir(self.cc) if d in anciens), [])          # rien sous un ancien nom

    def test_dossiers_renommes(self):
        self.assertTrue(os.path.basename(self.M.D).endswith('_renomme'))
        self.assertEqual((self.M.D, self.M.ST), (self.D, self.ST))
        f = self.version(1, '# v1\n'); self.lancer('proposer', f); self.lancer('approuver', '1', '--citation', 'oui')
        self.assertEqual(sorted(os.listdir(self.ST)), ['v1_approbation.json', 'v1_proposition.json'])
        self.assertEqual(self.lancer('courant'), (0, f + '\n'))
        J = chemin('journal', racine=self.cc); self.assertTrue(os.path.basename(J).endswith('_renomme'))
        self.assertEqual(len(glob.glob(os.path.join(J, '*', '*.json'))), 2)                  # journal renommé


if __name__ == '__main__':
    unittest.main()
