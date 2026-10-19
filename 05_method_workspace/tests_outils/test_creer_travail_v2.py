"""Tests de creer_travail_v2. (a) Non-régression : toute la suite v1 (six sous-dossiers, sources copiées en lecture seule avec
empreintes, fiche et LISEZMOI, options, rejeu qui n'écrase rien, erreurs de ligne de commande) est rejouée sur la version 2.
(b) Corrections de la v2 : une source ajoutée au rejeu a son empreinte dans une nouvelle version sha256_sources_v(N+1).txt qui reprend
toutes les empreintes, sans jamais modifier la version précédente ; pas de nouvelle version quand aucune source n'est nouvelle ;
une source absente arrête l'outil avant de créer quoi que ce soit (ni racine, ni dossier, ni copie), au premier lancement comme au rejeu."""
import os, unittest
from aide_tests_v2 import chemin_version
import test_creer_travail_v1 as T1

OUTIL2 = chemin_version('creer_travail', 2)


class SurV2:
    """Rejoue une classe de la suite v1 avec la version 2 (exécutable), puis restaure."""
    @classmethod
    def setUpClass(cls):
        cls._sauve = T1.OUTIL; T1.OUTIL = OUTIL2

    @classmethod
    def tearDownClass(cls):
        T1.OUTIL = cls._sauve


class CreationV1SurV2(SurV2, T1.Creation):
    pass


class RejeuV1SurV2(SurV2, T1.Rejeu):
    def test_rejeu_nouvelle_source_a_son_empreinte(self): pass   # remplacé par Corrige.test_rejeu_nouvelle_source_a_son_empreinte


class ErreursV1SurV2(SurV2, T1.Erreurs):
    pass


class Corrige(SurV2, T1.Base):
    def sources(self):
        return os.path.join(self.dossier(), '00_sources')

    def fsha(self, n):
        return os.path.join(self.sources(), f'sha256_sources_v{n}.txt')

    def versions_empreintes(self):
        return sorted(f for f in os.listdir(self.sources()) if f.startswith('sha256_sources_v'))

    def test_rejeu_nouvelle_source_a_son_empreinte(self):
        self.assertEqual(self.creer('07_sujet', '--source', self.doc).returncode, 0)
        v1 = T1.lire(self.fsha(1))
        r = self.creer('07_sujet', '--source', self.doc, self.csv)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.versions_empreintes(), ['sha256_sources_v1.txt', 'sha256_sources_v2.txt'])
        self.assertEqual(T1.lire(self.fsha(2)), f'{T1.sha(self.doc)}  00_sources/rapport_v1.docx\n{T1.sha(self.csv)}  00_sources/donnees.csv\n')
        self.assertEqual(T1.lire(self.fsha(1)), v1)                      # la v1 n'est pas écrasée
        self.assertTrue(T1.lecture_seule(self.fsha(2)))

    def test_versions_successives_reprennent_tout(self):
        autre = T1.ecrire(os.path.join(self.d, 'entrees', 'notes.txt'), 'notes')
        self.assertEqual(self.creer('07_sujet', '--source', self.doc).returncode, 0)
        self.assertEqual(self.creer('07_sujet', '--source', self.csv).returncode, 0)    # seule la nouvelle source est donnée
        v1, v2 = T1.lire(self.fsha(1)), T1.lire(self.fsha(2))
        self.assertEqual(v2, v1 + f'{T1.sha(self.csv)}  00_sources/donnees.csv\n')      # v2 garde l'empreinte de la source précédente
        self.assertEqual(self.creer('07_sujet', '--source', autre, self.doc).returncode, 0)
        self.assertEqual(T1.lire(self.fsha(3)), v2 + f'{T1.sha(autre)}  00_sources/notes.txt\n')
        self.assertEqual((T1.lire(self.fsha(1)), T1.lire(self.fsha(2))), (v1, v2))      # versions précédentes intactes
        self.assertEqual(len(self.versions_empreintes()), 3)

    def test_aucune_source_nouvelle_pas_de_nouvelle_version(self):
        self.assertEqual(self.creer('07_sujet', '--source', self.doc, self.csv).returncode, 0)
        v1 = T1.lire(self.fsha(1))
        self.assertEqual(self.creer('07_sujet', '--source', self.csv, self.doc).returncode, 0)
        self.assertEqual(self.creer('07_sujet').returncode, 0)
        self.assertEqual(self.versions_empreintes(), ['sha256_sources_v1.txt']); self.assertEqual(T1.lire(self.fsha(1)), v1)

    def test_empreinte_ajoutee_est_celle_de_la_copie(self):
        self.assertEqual(self.creer('07_sujet', '--source', self.doc).returncode, 0)
        avant = T1.sha(self.doc)
        T1.ecrire(self.doc, b'PK source remplacee apres coup')                  # la source d'origine change entre-temps
        self.assertEqual(self.creer('07_sujet', '--source', self.doc, self.csv).returncode, 0)
        self.assertEqual(T1.lire(self.fsha(2)), f'{avant}  00_sources/rapport_v1.docx\n{T1.sha(self.csv)}  00_sources/donnees.csv\n')

    def test_source_ajoutee_a_un_dossier_cree_sans_source(self):
        self.assertEqual(self.creer('07_sujet').returncode, 0)
        self.assertEqual(self.versions_empreintes(), [])
        self.assertEqual(self.creer('07_sujet', '--source', self.doc).returncode, 0)
        self.assertEqual(self.versions_empreintes(), ['sha256_sources_v1.txt'])          # première version, pas v2
        self.assertEqual(T1.lire(self.fsha(1)), f'{T1.sha(self.doc)}  00_sources/rapport_v1.docx\n')

    def test_source_absente_ne_cree_rien(self):
        absent = os.path.join(self.d, 'entrees', 'inexistant.docx')
        for sources in ((absent,), (self.doc, absent)):                           # même si une autre source est présente
            r = self.creer('07_sujet', '--source', *sources)
            self.assertNotEqual(r.returncode, 0); self.assertIn('inexistant.docx', r.stderr)
            self.assertFalse(os.path.exists(self.racine))                       # ni racine, ni dossier de travail, ni copie
        self.assertEqual(self.evenements(), [])

    def test_source_absente_au_rejeu_ne_change_rien(self):
        self.assertEqual(self.creer('07_sujet', '--source', self.doc).returncode, 0)
        avant = sorted(os.listdir(self.sources())); ev = len(self.evenements())
        r = self.creer('07_sujet', '--source', self.csv, os.path.join(self.d, 'entrees', 'inexistant.docx'))
        self.assertNotEqual(r.returncode, 0); self.assertIn('inexistant.docx', r.stderr)
        self.assertEqual(sorted(os.listdir(self.sources())), avant)              # la source présente n'est pas copiée non plus
        self.assertEqual(len(self.evenements()), ev)


if __name__ == '__main__':
    unittest.main()
