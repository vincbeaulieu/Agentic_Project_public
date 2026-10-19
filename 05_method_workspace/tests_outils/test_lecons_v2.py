"""Tests de lecons_v2 sur un espace fictif isolé (tests/_test_execution/, par dossier_essai), sans suite précédente à reprendre.
(a) Non-régression : ajout versionné sans écrasement (inchangée, nouvelle version, champs manquants, liste de leçons), dernière
version de chaque leçon, registre lisible versionné seulement s'il change, vérification (validée sans contrôle, règle inconnue),
commande en ligne. (b) Registre central des dossiers : tous les dossiers de l'espace fictif (sauf outils) renommés par
outils/_gestion/chemins_v1.json ; les mêmes cas rejoués : leçons, règles et journal lus et écrits dans les dossiers renommés,
aucun dossier créé sous son ancien nom. La racine de cc_lib_v4 (racine de l'outil et du journal) est celle de l'espace fictif
le temps de chaque test : aucune écriture hors de tests/_test_execution/."""
import os, sys, io, glob, json, runpy, itertools, contextlib, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, chemin, chemins
import cc_lib_v4 as L4

OUTIL, V = 'lecons', 2
CANDIDAT = chemin_version(OUTIL, V); _n = itertools.count()
REGLES = 'regles_travail_v1.json'          # nom de fichier lu par l'outil (version figée), dans le dossier de la clé « regles »
LECON = dict(id='LC-001', titre='Une leçon fictive', date='2026-10-15', source='essai', regle='règle', application='application',
             preuve='preuve', controle='evaluer_travail:O1', statut='proposee', skills=['skill-fictive'])


def ecrire_json(f, obj):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, 'w', encoding='utf-8') as g: json.dump(obj, g, ensure_ascii=False)


def lire(f):
    with open(f, encoding='utf-8') as g: return g.read()


def sortie(fn, *a):
    out = io.StringIO()
    with contextlib.redirect_stdout(out): r = fn(*a)
    return r, out.getvalue()


def commande(*a):
    """Lance le candidat comme programme (runpy, même processus, donc même racine fictive) ; renvoie (code, sortie)."""
    sys.argv = [CANDIDAT] + list(a); out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try: runpy.run_path(CANDIDAT, run_name='__main__'); code = 0
        except SystemExit as e: code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return code, out.getvalue()


class NonRegression(unittest.TestCase):
    renommer = False

    def setUp(self):
        self.cc = dossier_essai(f'{OUTIL}_v{V}'); self.defaut = chemins(self.cc)   # noms par défaut (espace sans registre)
        if self.renommer:
            ecrire_json(os.path.join(self.cc, 'outils', '_gestion', 'chemins_v1.json'),
                        dict(chemins={k: v + '_renomme' for k, v in self.defaut.items() if k != 'outils'}))
        sauve = (L4.RACINE_CC, sys.path[:], sys.argv)

        def restaurer(): L4.RACINE_CC = sauve[0]; sys.path[:] = sauve[1]; sys.argv = sauve[2]
        self.addCleanup(restaurer)
        L4.RACINE_CC = self.cc                                                    # avant l'import : l'outil y lit sa racine
        self.L = importer_version(OUTIL, V, alias=f'essai_{OUTIL}_{next(_n)}')
        self.D = chemin('lecons', racine=self.cc)

    def saisie(self, nom, obj):
        f = os.path.join(self.cc, nom); ecrire_json(f, obj); return f

    def evenements(self):
        return [json.loads(lire(f)) for f in sorted(glob.glob(chemin('journal', '*', '*.json', racine=self.cc)))]

    def test_ajouter_versionne_sans_ecrasement(self):
        self.assertEqual(self.L.D, self.D)
        _, out = sortie(self.L.ajouter, self.saisie('saisie_1.json', LECON))
        f1 = os.path.join(self.D, 'LC-001_v1.json'); self.assertIn('ajoutée LC-001_v1.json', out)
        self.assertEqual(json.loads(lire(f1)), LECON); avant = lire(f1)
        _, out = sortie(self.L.ajouter, self.saisie('saisie_2.json', LECON))
        self.assertIn('inchangée LC-001_v1.json', out); self.assertFalse(os.path.exists(os.path.join(self.D, 'LC-001_v2.json')))
        _, out = sortie(self.L.ajouter, self.saisie('saisie_3.json', dict(LECON, statut='validee')))
        self.assertIn('ajoutée LC-001_v2.json', out); self.assertEqual(lire(f1), avant)            # v1 jamais réécrite
        E = self.evenements(); self.assertEqual(len(E), 2)                                          # rien pour « inchangée »
        self.assertEqual({(e['outil'], e['version'], e['type'], e['donnees']['statut']) for e in E},
                         {(OUTIL, V, 'lecon', 'proposee'), (OUTIL, V, 'lecon', 'validee')})
        self.assertTrue(all(e['donnees'].get('banc') for e in E))

    def test_champs_manquants_et_liste(self):
        deux = [LECON, dict(LECON, id='LC-002', titre='Deuxième')]
        _, out = sortie(self.L.ajouter, self.saisie('saisie_liste.json', deux))
        self.assertTrue(os.path.exists(os.path.join(self.D, 'LC-002_v1.json'))); self.assertEqual(out.count('ajoutée'), 2)
        incomplete = {k: v for k, v in dict(LECON, id='LC-003').items() if k != 'preuve'}
        with self.assertRaises(SystemExit) as e: self.L.ajouter(self.saisie('saisie_incomplete.json', incomplete))
        self.assertIn('champs manquants', str(e.exception)); self.assertIn('preuve', str(e.exception))
        self.assertEqual(glob.glob(os.path.join(self.D, 'LC-003_v*.json')), [])

    def test_toutes_derniere_version(self):
        for nom, obj in (('LC-001_v1.json', LECON), ('LC-001_v2.json', dict(LECON, titre='v2')), ('LC-002_v1.json', dict(LECON, id='LC-002')),
                         ('LC-003_v9.json', dict(LECON, id='LC-003', titre='v9')), ('LC-003_v10.json', dict(LECON, id='LC-003', titre='v10')),
                         ('LC-01_v1.json', dict(LECON, id='LC-01'))):                                # identifiant mal formé : ignoré
            ecrire_json(os.path.join(self.D, nom), obj)
        T = self.L.toutes()
        self.assertEqual(list(T), ['LC-001', 'LC-002', 'LC-003'])
        self.assertEqual(T['LC-001']['titre'], 'v2'); self.assertEqual(T['LC-003']['titre'], 'v10')   # ordre numérique des versions

    def test_lister_registre_versionne(self):
        sortie(self.L.ajouter, self.saisie('saisie.json', [LECON, dict(LECON, id='LC-002', titre='Deuxième', skills=['s1', 's2'])]))
        _, out = sortie(self.L.lister); f1 = os.path.join(self.D, 'registre_lecons_v1.md')
        self.assertIn('2 leçons ; registre_lecons_v1.md (nouvelle version)', out); t = lire(f1)
        self.assertIn('| LC-001 | Une leçon fictive | proposee | evaluer_travail:O1 | skill-fictive |', t)
        self.assertIn('| LC-002 | Deuxième | proposee | evaluer_travail:O1 | s1, s2 |', t); self.assertIn('## LC-001 — Une leçon fictive', t)
        _, out = sortie(self.L.lister); self.assertIn('registre_lecons_v1.md (inchangé)', out)
        self.assertFalse(os.path.exists(os.path.join(self.D, 'registre_lecons_v2.md')))
        sortie(self.L.ajouter, self.saisie('saisie_v.json', dict(LECON, statut='validee'))); sortie(self.L.lister)
        self.assertIn('| LC-001 | Une leçon fictive | validee |', lire(os.path.join(self.D, 'registre_lecons_v2.md')))
        self.assertEqual(lire(f1), t)

    def test_verifier(self):
        ecrire_json(chemin('regles', REGLES, racine=self.cc), dict(regles=[dict(id='O1'), dict(id='E1')]))
        sortie(self.L.ajouter, self.saisie('saisie.json', [
            dict(LECON, statut='validee'),                                                   # contrôle connu : rien à reprendre
            dict(LECON, id='LC-002', statut='validee', controle='manuel'),                   # validée sans contrôle automatique
            dict(LECON, id='LC-003', controle='evaluer_travail:ZZ9'),                        # règle inconnue
            dict(LECON, id='LC-004', statut='validee', controle='')]))
        pb, out = sortie(self.L.verifier)
        self.assertEqual(pb, 3); self.assertIn('LC-002 : validée sans contrôle automatique', out)
        self.assertIn('LC-003 : règle ZZ9 inconnue', out); self.assertIn('LC-004 : validée sans contrôle', out)
        self.assertNotIn('LC-001', out); self.assertIn('leçons vérifiées : 4 ; à reprendre : 3', out)

    def test_commande(self):
        ecrire_json(chemin('regles', REGLES, racine=self.cc), dict(regles=[dict(id='O1')]))
        code, out = commande('ajouter', self.saisie('saisie.json', LECON)); self.assertEqual(code, 0); self.assertIn('ajoutée LC-001_v1.json', out)
        code, out = commande('lister'); self.assertEqual(code, 0); self.assertTrue(os.path.exists(os.path.join(self.D, 'registre_lecons_v1.md')))
        self.assertEqual(commande('verifier')[0], 0)
        commande('ajouter', self.saisie('saisie_2.json', dict(LECON, statut='validee', controle='manuel')))
        self.assertEqual(commande('verifier')[0], 1)


class RegistreCentral(NonRegression):
    """Mêmes cas, chaque dossier de l'espace renommé (clé -> <nom par défaut>_renomme)."""
    renommer = True

    def tearDown(self):
        anciens = set(self.defaut.values()) - {'outils'}
        self.assertEqual(sorted(d for d in os.listdir(self.cc) if d in anciens), [])          # rien sous un ancien nom

    def test_dossiers_renommes(self):
        self.assertTrue(os.path.basename(self.L.D).endswith('_renomme')); self.assertEqual(self.L.D, self.D)
        ecrire_json(chemin('regles', REGLES, racine=self.cc), dict(regles=[dict(id='O1')]))
        sortie(self.L.ajouter, self.saisie('saisie.json', dict(LECON, statut='validee'))); sortie(self.L.lister)
        self.assertEqual(sorted(os.listdir(self.D)), ['LC-001_v1.json', 'registre_lecons_v1.md'])
        self.assertEqual(sortie(self.L.verifier)[0], 0)                                       # règles lues dans le dossier renommé
        J = chemin('journal', racine=self.cc); self.assertTrue(os.path.basename(J).endswith('_renomme'))
        self.assertEqual(len(glob.glob(os.path.join(J, '*', '*.json'))), 1)                  # journal renommé


if __name__ == '__main__':
    unittest.main()
