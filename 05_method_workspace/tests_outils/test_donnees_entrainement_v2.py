"""Tests unitaires de donnees_entrainement v2 (registre central des dossiers, cc_lib_v4.chemin). (a) Non-régression : cas de la
suite v1 réécrits avec chemin() (collecte immuable sans doublon, or > argent, utilisateur > Claude, classe inconnue ignorée),
règles en bronze, état, redirection historique par D.E toujours suivie. (b) Registre : espace fictif dont le registre renomme les
dossiers ; l'outil y lit et écrit le dossier renommé, et son événement va dans le journal renommé. Chaque essai tourne dans un
espace d'essai (tests/_test_execution/) : la racine vue par cc_lib_v4 est remplacée le temps du test, rien n'est écrit ailleurs."""
import os, io, json, glob, contextlib, unittest
from aide_tests_v2 import dossier_essai, importer_version, chemin, chemins
import cc_lib_v4 as L4
V = 2                                                       # version essayée (candidate tant qu'elle n'est pas adoptée)
SPEC = dict(tache='t', entree=['texte'], traits=['ngrammes'], classes=['x', 'y'], poids={'or': 1.0, 'argent': 0.4, 'bronze': 0.1})


def espace(nom, renommer=False):
    """Racine d'un espace d'essai ; renommer : registre outils/_gestion/chemins_v1.json qui renomme chaque dossier en <clé>_renomme."""
    r = dossier_essai(nom)
    if renommer:
        g = os.path.join(r, 'outils', '_gestion'); os.makedirs(g)
        with open(os.path.join(g, 'chemins_v1.json'), 'w', encoding='utf-8') as f:
            json.dump({'chemins': {k: k + '_renomme' for k in chemins() if k != 'outils'}}, f)
    return r


class Base(unittest.TestCase):
    renommer = False

    def setUp(self):
        self.r = espace('de_registre' if self.renommer else 'de_defaut', self.renommer)
        sauve = L4.RACINE_CC; L4.RACINE_CC = self.r; self.addCleanup(setattr, L4, 'RACINE_CC', sauve)   # racine vue par l'outil et son journal
        self.D = importer_version('donnees_entrainement', V)
        self.ecrire_spec(self.D.E)
        self.w = dossier_essai('de_travail'); self.mt = os.path.join(self.w, 'mt.jsonl')
        with open(self.mt, 'w', encoding='utf-8') as f:
            for i in ('a', 'b'): f.write(json.dumps(dict(id=i, texte='texte ' + i)) + '\n')

    def ecrire_spec(self, rep):
        os.makedirs(os.path.join(rep, self.D.SPECS))
        with open(os.path.join(rep, self.D.SPECS, 't_v1.json'), 'w', encoding='utf-8') as f: json.dump(SPEC, f)

    def collecte(self, etiq, q, src, *plus):
        f = os.path.join(self.w, f'{src}_{len(os.listdir(self.w))}.json')
        with open(f, 'w', encoding='utf-8') as g: json.dump(etiq, g)
        with contextlib.redirect_stdout(io.StringIO()) as s:
            self.D.collecter(['t', '--taches', self.mt, '--etiquettes', f, '--qualite', q, '--source', src, '--travail', 'essai', *plus])
        return s.getvalue()

    def lots(self): return sorted(glob.glob(os.path.join(self.D.E, 'donnees', 't', 'lot_*.jsonl')))


class NonRegression(Base):
    def test_or_prime_et_pas_de_doublon(self):
        self.collecte({'a': 'x', 'b': 'x'}, 'argent', 'modele')
        self.assertIn('aucun exemple nouveau', self.collecte({'a': 'x', 'b': 'x'}, 'argent', 'modele'))   # même source : rien de nouveau
        self.collecte({'a': 'y'}, 'or', 'reference')
        S, J = self.D.charger_jeu('t'); J = {x['origines'][0]: x for x in J}
        self.assertEqual(J['a']['etiquette'], 'y'); self.assertEqual(J['a']['qualite'], 'or'); self.assertEqual(J['b']['qualite'], 'argent')
        self.assertEqual(len(self.lots()), 2)

    def test_utilisateur_prime_sur_claude(self):
        self.collecte({'a': 'x'}, 'or', 'reference')
        self.collecte({'a': 'y'}, 'or', 'utilisateur')
        S, J = self.D.charger_jeu('t'); self.assertEqual(J[0]['etiquette'], 'y')

    def test_classe_inconnue_ignoree(self):
        self.collecte({'a': 'z'}, 'or', 'reference'); self.assertFalse(os.path.isdir(os.path.join(self.D.E, 'donnees', 't')))

    def test_regle_en_bronze(self):
        self.collecte({'a': {'final': 'x', 'regle': 'R1'}, 'b': {'final': 'y', 'regle': 'R2'}}, 'argent', 'modele', '--regles', 'R1')
        X = {x['origine']['id']: x for x in self.D.exemples('t')}
        self.assertEqual((X['a']['qualite'], X['a']['source']), ('bronze', 'regle:R1'))
        self.assertEqual((X['b']['qualite'], X['b']['source']), ('argent', 'modele'))

    def test_etat(self):
        self.collecte({'a': 'x', 'b': 'y'}, 'or', 'reference')
        with contextlib.redirect_stdout(io.StringIO()) as s: self.D.etat(['t'])
        self.assertIn('t : 2 entrées distinctes', s.getvalue()); self.assertIn('lots : 1', s.getvalue())

    def test_dossier_par_defaut_et_evenement(self):
        self.assertEqual(self.D.E, chemin('entrainement', racine=self.r))
        self.collecte({'a': 'x'}, 'or', 'reference')
        self.assertEqual(len(glob.glob(chemin('journal', '*', '*_donnees_entrainement_v2_*.json', racine=self.r))), 1)

    def test_redirection_par_E_toujours_suivie(self):          # mécanisme de la suite v1 (D.E remplacé), rejouée sur la v2 à l'adoption
        autre = dossier_essai('de_redirige'); self.ecrire_spec(autre); self.D.E = autre
        self.collecte({'a': 'x'}, 'or', 'reference')
        self.assertEqual(len(glob.glob(os.path.join(autre, 'donnees', 't', 'lot_*.jsonl'))), 1)
        self.assertFalse(os.path.isdir(os.path.join(chemin('entrainement', racine=self.r), 'donnees')))


class Registre(Base):
    renommer = True

    def test_lit_et_ecrit_le_dossier_renomme(self):
        E = chemin('entrainement', racine=self.r)
        self.assertEqual(self.D.E, E); self.assertTrue(os.path.basename(E).endswith('_renomme'))
        self.collecte({'a': 'x', 'b': 'y'}, 'or', 'reference')                                     # lit la spécification renommée
        self.assertEqual(len(glob.glob(os.path.join(E, 'donnees', 't', 'lot_*.jsonl'))), 1)           # écrit le lot dans le dossier renommé
        S, J = self.D.charger_jeu('t'); self.assertEqual(len(J), 2)                                    # relit le dossier renommé
        self.assertEqual(len(glob.glob(chemin('journal', '*', '*_donnees_entrainement_v2_*.json', racine=self.r))), 1)
        self.assertEqual(sorted(d for d in os.listdir(self.r) if d != 'outils' and not d.endswith('_renomme')), [])   # aucun nom par défaut

    def test_specification_absente_nomme_le_dossier_renomme(self):
        with self.assertRaises(SystemExit) as e: self.D.spec('inconnue')
        self.assertIn(os.path.relpath(chemin('entrainement', racine=self.r), self.r), str(e.exception))


if __name__ == '__main__':
    unittest.main()
