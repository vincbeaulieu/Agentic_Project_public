"""Tests de renommer_v1 : renommage de fichiers et de dossiers d'après un plan JSON (même fichier, même contenu, dossiers parents créés,
événement de journal redirigé vers le dossier d'essai) ; essai à blanc (rien ne bouge, aucun événement) ; refus d'écraser une cible
existante ; rejeu d'un plan déjà appliqué (« déjà fait ») ; source absente (refus, ou ignorée avec --ignorer-absents) ; arguments
manquants ou plan invalide ; essai à blanc infidèle sur deux sources visant la même cible (défaut signalé par un test en échec attendu)."""
import os, sys, glob, json, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, OUTILS

OUTIL = chemin_version('renommer', 1)
# L'outil écrit un événement dans le journal de l'espace : le lanceur en redirige la racine vers le dossier d'essai (argument 1).
LANCEUR = ("import sys, runpy, cc_lib_v1; cc_lib_v1.JOURNAL = sys.argv[1]; sys.argv[:] = sys.argv[2:]; "
           "runpy.run_path(sys.argv[0], run_name='__main__')")


def lire(chemin):
    with open(chemin, encoding='utf-8') as f: return f.read()


class Base(unittest.TestCase):
    def setUp(self):
        self.d = dossier_essai('renommer'); self.racine = os.path.join(self.d, 'racine'); self.journal = os.path.join(self.d, 'evenements_essai')
        os.makedirs(self.racine)

    def ecrire(self, rel, contenu='x'):
        f = os.path.join(self.racine, rel); os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, 'w', encoding='utf-8') as g: g.write(contenu)
        return f

    def plan(self, *paires):
        f = os.path.join(self.d, 'plan_v1.json')
        with open(f, 'w', encoding='utf-8') as g: json.dump({'renommages': [list(p) for p in paires]}, g, ensure_ascii=False)
        return f

    def lancer(self, *args):
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS]))
        return subprocess.run([sys.executable, '-c', LANCEUR, self.journal, OUTIL, *args], capture_output=True, text=True, env=env)

    def appliquer(self, *paires, options=()):
        return self.lancer(self.racine, self.plan(*paires), *options)

    def existe(self, rel):
        return os.path.exists(os.path.join(self.racine, rel))

    def evenements(self):
        return [json.loads(lire(f)) for f in sorted(glob.glob(os.path.join(self.journal, '*', '*.json')))]


class Renommage(Base):
    def test_renomme_fichier_et_dossier_avec_parents_crees(self):
        a = self.ecrire('a.txt', 'contenu A'); self.ecrire('dossier_x/f.txt', 'contenu F'); inode = os.stat(a).st_ino
        r = self.appliquer(('a.txt', 'b.txt'), ('dossier_x', 'neuf/profond/dossier_y'))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('renommé a.txt -> b.txt', r.stdout); self.assertIn('2 renommage(s) fait(s) ; 0 déjà fait(s)', r.stdout)
        self.assertFalse(self.existe('a.txt')); self.assertFalse(self.existe('dossier_x'))
        b = os.path.join(self.racine, 'b.txt')
        self.assertEqual((lire(b), os.stat(b).st_ino), ('contenu A', inode))             # déplacé, non copié
        self.assertEqual(lire(os.path.join(self.racine, 'neuf', 'profond', 'dossier_y', 'f.txt')), 'contenu F')
        ev = self.evenements()
        self.assertEqual([(e['outil'], e['type']) for e in ev], [('renommer', 'renommage')])
        self.assertEqual((ev[0]['donnees']['racine'], ev[0]['donnees']['n']), ('racine', 2))

    def test_essai_a_blanc_ne_change_rien(self):
        self.ecrire('a.txt'); self.ecrire('dossier_x/f.txt')
        r = self.appliquer(('a.txt', 'b.txt'), ('dossier_x', 'neuf/dossier_y'), options=('--essai',))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('à renommer a.txt -> b.txt', r.stdout); self.assertIn('2 renommage(s) prévu(s)', r.stdout)
        self.assertTrue(self.existe('a.txt') and self.existe('dossier_x/f.txt'))
        self.assertFalse(self.existe('b.txt')); self.assertFalse(self.existe('neuf'))      # ni cible ni dossier parent créés
        self.assertEqual(self.evenements(), [])                                          # aucun événement pour un essai

    def test_rejeu_du_plan_deja_applique(self):
        self.ecrire('a.txt'); self.ecrire('dossier_x/f.txt'); paires = (('a.txt', 'b.txt'), ('dossier_x', 'dossier_y'))
        self.assertEqual(self.appliquer(*paires).returncode, 0)
        r = self.appliquer(*paires)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('déjà fait a.txt -> b.txt', r.stdout); self.assertIn('0 renommage(s) fait(s) ; 2 déjà fait(s)', r.stdout)
        self.assertTrue(self.existe('b.txt') and self.existe('dossier_y/f.txt'))


class Refus(Base):
    def test_refuse_d_ecraser_une_cible_existante(self):
        self.ecrire('a.txt', 'A'); self.ecrire('b.txt', 'B'); self.ecrire('c.txt', 'C'); os.makedirs(os.path.join(self.racine, 'rep'))
        for options in ((), ('--essai',)):                                               # l'essai à blanc refuse comme l'exécution
            r = self.appliquer(('a.txt', 'b.txt'), options=options)
            self.assertEqual(r.returncode, 1); self.assertIn('CIBLE EXISTE : b.txt', r.stderr)
        r = self.appliquer(('c.txt', 'rep'))                                             # cible : un dossier existant
        self.assertEqual(r.returncode, 1); self.assertIn('CIBLE EXISTE : rep', r.stderr)
        self.assertEqual((lire(os.path.join(self.racine, 'a.txt')), lire(os.path.join(self.racine, 'b.txt')), lire(os.path.join(self.racine, 'c.txt'))),
                         ('A', 'B', 'C'))
        self.assertEqual(self.evenements(), [])

    def test_source_absente(self):
        self.ecrire('a.txt')
        r = self.appliquer(('absent.txt', 'autre.txt'), ('a.txt', 'b.txt'))
        self.assertEqual(r.returncode, 1); self.assertIn('ABSENT : absent.txt', r.stderr)
        self.assertTrue(self.existe('a.txt') and not self.existe('b.txt'))                  # arrêt au premier absent
        r = self.appliquer(('absent.txt', 'autre.txt'), ('a.txt', 'c.txt'), options=('--ignorer-absents',))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('absent (ignoré) absent.txt', r.stdout); self.assertIn('1 renommage(s) fait(s)', r.stdout)
        self.assertTrue(self.existe('c.txt') and not self.existe('autre.txt'))

    def test_arguments_manquants_ou_plan_invalide(self):
        self.assertNotEqual(self.lancer().returncode, 0)                                 # sans argument
        self.assertNotEqual(self.lancer(self.racine, os.path.join(self.d, 'plan_inexistant.json')).returncode, 0)
        sans_cle = os.path.join(self.d, 'plan_sans_cle.json')
        with open(sans_cle, 'w', encoding='utf-8') as g: json.dump({'autre': []}, g)
        r = self.lancer(self.racine, sans_cle)
        self.assertNotEqual(r.returncode, 0); self.assertIn('renommages', r.stderr)

    @unittest.expectedFailure
    def test_essai_a_blanc_detecte_deux_sources_vers_une_cible(self):
        # Défaut : l'essai à blanc contrôle chaque cible contre le disque seulement ; deux sources visant la même cible passent l'essai
        # (code 0), alors que l'exécution réelle renomme la première puis s'arrête sur « CIBLE EXISTE » (plan appliqué à moitié).
        self.ecrire('a.txt'); self.ecrire('b.txt')
        r = self.appliquer(('a.txt', 'c.txt'), ('b.txt', 'c.txt'), options=('--essai',))
        self.assertEqual(r.returncode, 1, r.stdout)


if __name__ == '__main__':
    unittest.main()
