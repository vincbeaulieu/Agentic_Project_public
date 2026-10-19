"""Tests de accepter_auteurs_v2. (a) Non-régression : suite v1 rejouée sur la version 2. (b) Ajout : marques de paragraphe d'un déplacement
suivi acceptées — la source (marque moveFrom) disparaît, la copie (marque moveTo) est validée ; les révisions d'un autre auteur imbriquées
dans le déplacement restent en suivi ; accepter l'auteur puis les autres = tout accepter d'un coup. Témoin : la v1 laisse la source du
déplacement comme paragraphe vide."""
import unittest
from aide_tests_v2 import importer_version, chemin_version
import test_accepter_auteurs_v1 as T1
import test_moteur_revision_multi_v3 as TM

M2 = importer_version('accepter_auteurs', 2, 'accepter_auteurs_v2_essai')
M1 = importer_version('accepter_auteurs', 1, 'accepter_auteurs_v1_temoin')


class SurV2:
    @classmethod
    def setUpClass(cls): cls._s = T1.M; T1.M = M2

    @classmethod
    def tearDownClass(cls): T1.M = cls._s


class ContenuSurV2(SurV2, T1.Contenu): pass
class MarquesSurV2(SurV2, T1.Marques): pass
class RangeesSurV2(SurV2, T1.Rangees): pass
class ChampsSurV2(SurV2, T1.Champs): pass
class ProprieteSurV2(SurV2, T1.Propriete): pass
class PaquetSurV2(SurV2, T1.Paquet): pass


class Deplacements(unittest.TestCase):
    def setUp(self): self.f, self.out = TM.Deplacement().deplacer(TM.M3)

    def test_accepter_le_deplacement(self):
        A = TM.lire(self.out); b = M2.accepter(A, [TM.AUTEUR])
        self.assertEqual(b.get('marque_supprimee'), 1); self.assertEqual(b.get('marque_deplacee_vers'), 1)
        self.assertEqual(TM.textes(A), ['[1]\tAlpha', '[3]\tGamma', '[2]\tBeta ajout ', 'Fin'])
        self.assertEqual(len(list(A.iter(M2.q('p')))), 4)
        self.assertEqual({a for (t, a) in M2.auteurs_revisions(A)}, {TM.AUTRE})

    def test_par_etapes_egal_tout(self):
        X = TM.lire(self.out); M2.accepter(X, [TM.AUTEUR]); M2.accepter(X, [TM.AUTRE])
        Y = TM.lire(self.out); M2.accepter(Y, [TM.AUTEUR, TM.AUTRE])
        self.assertEqual(TM.textes(X), TM.textes(Y)); self.assertEqual(dict(M2.auteurs_revisions(X)), {})

    def test_temoin_v1(self):
        A = TM.lire(self.out); M1.accepter(A, [TM.AUTEUR])
        self.assertEqual(len(list(A.iter(M2.q('p')))), 5)             # la source du déplacement restait

    def test_entete(self):
        s = open(chemin_version('accepter_auteurs', 2), encoding='utf-8').read(); self.assertIn('VERSION: 2', s); self.assertNotIn('À DÉCRIRE', s)


if __name__ == '__main__':
    unittest.main()
