"""Tests de croiser_demandes_v4 (contrôle des leçons LC-008 et LC-009). (a) Non-régression : toute la suite v3 (écarts E1 à E6 et D1 selon le type
de la demande, le statut annoncé et l'auteur de la passe, sortie versionnée, refus d'une demande absente des microtâches) est rejouée sur la
version 4. (b) Corrections de la v4 : sans argument (ou avec moins de cinq), l'outil affiche la ligne USAGE de son en-tête et sort avec le code 2,
sans trace (la v3 s'arrêtait sur une trace « ValueError », code 1) ; l'en-tête SORTIES décrit les clés réellement écrites (« dele » et non
« del », clé inchangée car lue par d'autres outils). L'événement du journal porte la version 4."""
import os, re, sys, glob, json, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, OUTILS
import test_croiser_demandes_v3 as T3

CD4 = importer_version('croiser_demandes', 4, 'croiser_demandes_v4_essai'); OUTIL4 = chemin_version('croiser_demandes', 4)


class SurV4:
    """Rejoue la classe de la suite v3 avec la version 4 (module et exécutable), puis restaure."""
    @classmethod
    def setUpClass(cls):
        cls._sauve = (T3.CD, T3.OUTIL); T3.CD, T3.OUTIL = CD4, OUTIL4

    @classmethod
    def tearDownClass(cls):
        T3.CD, T3.OUTIL = cls._sauve


class CroiserV3SurV4(SurV4, T3.Croiser):
    def test_sortie_versionnee_resume_et_journal(self): pass   # remplacé par Corrige.test_sortie_versionnee_resume_et_journal (événement de la v4)
    def test_ligne_de_commande_usage(self): pass               # remplacé par Corrige.test_ligne_de_commande_usage


def ligne_usage():
    """Ligne USAGE de l'en-tête du brouillon, telle qu'elle est écrite dans le fichier."""
    with open(OUTIL4, encoding='utf-8') as f:
        return next(l.rstrip('\n') for l in f if l.startswith('USAGE: '))


def sorties_entete():
    with open(OUTIL4, encoding='utf-8') as f:
        return next(l.rstrip('\n') for l in f if l.startswith('SORTIES: '))


class Corrige(SurV4, unittest.TestCase):
    setUp = T3.Croiser.setUp; ecrire = T3.Croiser.ecrire; lancer = T3.Croiser.lancer; resultat = T3.Croiser.resultat; env = T3.Croiser.env

    def test_ligne_de_commande_usage(self):
        r = subprocess.run([sys.executable, OUTIL4], capture_output=True, text=True, env=self.env(), timeout=120)
        self.assertEqual(r.returncode, 2, r.stderr); self.assertEqual(r.stdout, ligne_usage() + '\n')
        self.assertNotIn('Traceback', r.stderr); self.assertEqual(r.stderr, '')

    def test_arguments_insuffisants(self):
        for args in (['rapport_v1.docx'], ['rapport_v1.docx', 'classement.json', 'microtaches.jsonl', 'dossiers'], ['--auteur', 'Collègue A']):
            with self.subTest(args=args):
                r = subprocess.run([sys.executable, OUTIL4, *args], capture_output=True, text=True, env=self.env(), timeout=120)
                self.assertEqual(r.returncode, 2, r.stderr); self.assertEqual(r.stdout, ligne_usage() + '\n'); self.assertNotIn('Traceback', r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.d, 'sortie')))            # rien n'est écrit

    def test_appel_complet_sans_usage(self):
        out = self.lancer()
        self.assertNotIn('USAGE', out.upper()); self.assertIn('11 demandes', out)

    def test_entete_decrit_les_cles_ecrites(self):
        self.lancer(); R = self.resultat(); s = sorties_entete()
        ancre = re.search(r'ancre:\{([^}]*)\}', s).group(1); section = re.search(r'section:\{([^}]*)\}', s).group(1)
        self.assertEqual(set(ancre.split(',')), set(R['d01']['ancre']))             # clés de « ancre » : celles du code
        self.assertEqual(set(section.split(',')), set(R['d01']['section']))         # clés de « section » : celles du code
        haut = re.sub(r':\{[^}]*\}|:\[[^\]]*\]', '', re.search(r'\{id: \{(.*)\}\}', s).group(1))
        self.assertEqual({k.strip() for k in haut.split(',')}, set(R['d01']))       # clés de premier niveau : celles du code
        self.assertIn('dele', ancre.split(',')); self.assertNotIn('del', ancre.split(',')); self.assertNotIn('del', section.split(','))

    def test_cle_dele_inchangee(self):
        self.lancer(); R = self.resultat()
        for r in R.values():
            self.assertIn('dele', r['ancre']); self.assertIn('dele', r['section'])
            self.assertNotIn('del', r['ancre']); self.assertNotIn('del', r['section'])
        self.assertGreater(R['d01']['ancre']['dele'], 0)                             # la valeur reste le nombre de caractères supprimés

    def test_sortie_versionnee_resume_et_journal(self):
        out = self.lancer()
        self.assertIn('croisement_demandes_v1.json', out); self.assertIn('11 demandes', out)
        for code, n in (('E1', 1), ('E2', 1), ('E3', 1), ('E4', 1), ('E5', 1), ('E6', 2), ('D1', 1)): self.assertIn(f'{code} {n} (', out, code)
        self.lancer()                                                               # même contenu : pas de nouvelle version
        self.assertEqual(sorted(os.listdir(os.path.join(self.d, 'sortie'))), ['croisement_demandes_v1.json'])
        self.lancer('--seuil-deplace', '1.1')                                       # contenu différent : v2, la v1 reste intacte
        self.assertEqual(sorted(os.listdir(os.path.join(self.d, 'sortie'))), ['croisement_demandes_v1.json', 'croisement_demandes_v2.json'])
        evts = sorted(glob.glob(os.path.join(self.cc, '*', '*', '*_croiser_demandes_v4_*.json')))
        self.assertEqual(len(evts), 2)                                              # un événement par exécution, dans l'espace d'essai
        with open(evts[0], encoding='utf-8') as f: e = json.load(f)
        self.assertEqual((e['outil'], e['version'], e['type']), ('croiser_demandes', 4, 'croisement'))
        self.assertEqual(e['donnees']['demandes'], 11); self.assertEqual(e['donnees']['ecarts']['E6'], 2)

    def test_entete_a_jour(self):
        with open(OUTIL4, encoding='utf-8') as f: s = f.read()
        self.assertIn('VERSION: 4\n', s); self.assertIn('BANC: tests/test_croiser_demandes_v4.py\n', s); self.assertNotIn('À DÉCRIRE', s)
        self.assertTrue(ligne_usage().startswith('USAGE: python3 croiser_demandes_v4.py '))


if __name__ == '__main__':
    unittest.main()
