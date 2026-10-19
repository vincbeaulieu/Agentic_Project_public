"""Tests de renommer_v2. (a) Non-régression : toute la suite v1 (renommage de fichiers et de dossiers, essai à blanc, refus d'écraser,
rejeu d'un plan déjà appliqué, source absente, arguments manquants ou plan invalide) est rejouée sur la version 2.
(b) Corrections de la v2 : le plan entier est validé avant le premier renommage, essai à blanc compris (sources présentes, cibles
libres et distinctes) ; en cas d'écart, tous les écarts sont listés, le code est 1 et rien n'est renommé (plus de plan appliqué à
moitié) ; deux sources visant la même cible, ou la même source deux fois, sont refusées ; les plans qui s'enchaînent (une cible
réutilisée comme source, un chemin sous un dossier déplacé) restent acceptés ; sans argument, l'outil affiche USAGE et sort avec le code 2."""
import os, unittest
from aide_tests_v2 import chemin_version
import test_renommer_v1 as T1

OUTIL2 = chemin_version('renommer', 2)


class SurV2:
    """Rejoue une classe de la suite v1 avec la version 2 (exécutable), puis restaure."""
    @classmethod
    def setUpClass(cls):
        cls._sauve = T1.OUTIL; T1.OUTIL = OUTIL2

    @classmethod
    def tearDownClass(cls):
        T1.OUTIL = cls._sauve


class RenommageV1SurV2(SurV2, T1.Renommage):
    pass


class RefusV1SurV2(SurV2, T1.Refus):
    def test_essai_a_blanc_detecte_deux_sources_vers_une_cible(self): pass   # remplacé par Corrige.test_essai_a_blanc_detecte_deux_sources_vers_une_cible


class Corrige(SurV2, T1.Base):
    def ligne_usage(self):
        with open(OUTIL2, encoding='utf-8') as f:
            return next(l.rstrip('\n') for l in f if l.startswith('USAGE: '))

    def etat(self, *rels):
        return {rel: self.existe(rel) for rel in rels}

    def test_essai_a_blanc_detecte_deux_sources_vers_une_cible(self):
        self.ecrire('a.txt'); self.ecrire('b.txt')
        r = self.appliquer(('a.txt', 'c.txt'), ('b.txt', 'c.txt'), options=('--essai',))
        self.assertEqual(r.returncode, 1, r.stdout); self.assertIn('CIBLE EN DOUBLE : c.txt', r.stderr)
        self.assertEqual(r.stdout, '')                                           # aucune ligne « à renommer » sur un plan refusé
        self.assertEqual(self.etat('a.txt', 'b.txt', 'c.txt'), {'a.txt': True, 'b.txt': True, 'c.txt': False})

    def test_execution_deux_sources_vers_une_cible_ne_renomme_rien(self):
        self.ecrire('a.txt', 'A'); self.ecrire('b.txt', 'B')
        r = self.appliquer(('a.txt', 'c.txt'), ('b.txt', 'c.txt'))
        self.assertEqual(r.returncode, 1); self.assertIn('CIBLE EN DOUBLE : c.txt', r.stderr); self.assertIn('aucun renommage', r.stderr)
        self.assertEqual(self.etat('a.txt', 'b.txt', 'c.txt'), {'a.txt': True, 'b.txt': True, 'c.txt': False})
        self.assertEqual(self.evenements(), [])

    def test_ligne_en_echec_en_fin_de_plan_ne_renomme_rien(self):
        self.ecrire('a.txt'); self.ecrire('dossier_x/f.txt'); self.ecrire('pris.txt'); self.ecrire('autre.txt')
        paires = (('a.txt', 'b.txt'), ('dossier_x', 'neuf/dossier_y'), ('absent.txt', 'z.txt'))
        r = self.appliquer(*paires)                                               # dernière ligne : source absente
        self.assertEqual(r.returncode, 1); self.assertIn('ABSENT : absent.txt', r.stderr)
        r = self.appliquer(*paires[:2], ('autre.txt', 'pris.txt'))                    # dernière ligne : cible existante
        self.assertEqual(r.returncode, 1); self.assertIn('CIBLE EXISTE : pris.txt', r.stderr)
        self.assertEqual(self.etat('a.txt', 'b.txt', 'dossier_x/f.txt', 'neuf'), {'a.txt': True, 'b.txt': False, 'dossier_x/f.txt': True, 'neuf': False})
        self.assertEqual(self.evenements(), [])

    def test_tous_les_ecarts_sont_listes(self):
        self.ecrire('a.txt'); self.ecrire('b.txt'); self.ecrire('c.txt')
        r = self.appliquer(('absent.txt', 'x.txt'), ('a.txt', 'b.txt'), ('c.txt', 'd.txt'), ('a.txt', 'e.txt'))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stderr.splitlines(), ['ABSENT : absent.txt', 'CIBLE EXISTE : b.txt', 'PLAN REFUSE : 2 écart(s), aucun renommage effectué'])
        self.assertEqual(self.etat('a.txt', 'c.txt', 'd.txt', 'e.txt'), {'a.txt': True, 'c.txt': True, 'd.txt': False, 'e.txt': False})

    def test_meme_source_deux_fois_refusee(self):
        self.ecrire('a.txt')
        r = self.appliquer(('a.txt', 'b.txt'), ('a.txt', 'c.txt'), options=('--essai',))
        self.assertEqual(r.returncode, 1); self.assertIn('SOURCE EN DOUBLE : a.txt', r.stderr)
        self.assertEqual(self.etat('a.txt', 'b.txt', 'c.txt'), {'a.txt': True, 'b.txt': False, 'c.txt': False})

    def test_ignorer_absents_ne_masque_pas_un_ecart(self):
        self.ecrire('a.txt'); self.ecrire('b.txt'); self.ecrire('c.txt')
        r = self.appliquer(('absent.txt', 'x.txt'), ('c.txt', 'd.txt'), ('a.txt', 'b.txt'), options=('--ignorer-absents',))
        self.assertEqual(r.returncode, 1); self.assertIn('CIBLE EXISTE : b.txt', r.stderr)
        self.assertEqual(self.etat('c.txt', 'd.txt'), {'c.txt': True, 'd.txt': False})       # la ligne valide n'est pas appliquée seule

    def test_plans_enchaines_toujours_acceptes(self):
        self.ecrire('a.txt', 'A'); self.ecrire('dossier_x/f.txt', 'F')
        paires = (('a.txt', 'b.txt'), ('b.txt', 'c.txt'),                                   # cible réutilisée comme source
                  ('dossier_x', 'dossier_y'), ('dossier_y/f.txt', 'dossier_y/g.txt'))        # chemin sous un dossier déjà déplacé
        r = self.appliquer(*paires, options=('--essai',))
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn('4 renommage(s) prévu(s)', r.stdout)
        self.assertTrue(self.existe('a.txt') and self.existe('dossier_x/f.txt'))
        r = self.appliquer(*paires)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn('4 renommage(s) fait(s)', r.stdout)
        self.assertEqual((T1.lire(os.path.join(self.racine, 'c.txt')), T1.lire(os.path.join(self.racine, 'dossier_y', 'g.txt'))), ('A', 'F'))
        self.assertEqual(self.etat('a.txt', 'b.txt', 'dossier_x'), {'a.txt': False, 'b.txt': False, 'dossier_x': False})

    def test_dossier_cree_par_le_plan_est_une_cible_occupee(self):
        self.ecrire('a.txt'); self.ecrire('b.txt')
        r = self.appliquer(('a.txt', 'neuf/a.txt'), ('b.txt', 'neuf'))
        self.assertEqual(r.returncode, 1); self.assertIn('CIBLE EXISTE : neuf', r.stderr)
        self.assertEqual(self.etat('a.txt', 'neuf'), {'a.txt': True, 'neuf': False})

    def test_plan_partiellement_deja_applique_reste_accepte(self):
        self.ecrire('b.txt'); self.ecrire('d.txt')
        r = self.appliquer(('c.txt', 'd.txt'), ('b.txt', 'e.txt'))                          # c.txt absent et d.txt présent : déjà fait
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn('déjà fait c.txt -> d.txt', r.stdout)
        self.assertIn('1 renommage(s) fait(s) ; 1 déjà fait(s)', r.stdout); self.assertTrue(self.existe('e.txt'))

    def test_sans_argument_affiche_usage_et_sort_avec_2(self):
        usage = self.ligne_usage(); self.assertIn('renommer_v2.py', usage)
        for args in ((), (self.racine,), ('--essai',), ('--essai', '--ignorer-absents')):
            r = self.lancer(*args)
            self.assertEqual(r.returncode, 2, args); self.assertEqual(r.stdout.rstrip('\n'), usage, args)
        self.assertEqual(self.evenements(), [])


if __name__ == '__main__':
    unittest.main()
