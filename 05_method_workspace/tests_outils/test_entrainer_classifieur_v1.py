"""Tests unitaires de entrainer_classifieur : traits déterministes, probabilités, reprise exacte depuis un point de reprise."""
import os, unittest
import numpy as np
from aide_tests_v1 import importer, dossier_essai
C = importer('entrainer_classifieur')


def donnees(n=40, d=12, k=3, graine=1):
    r = np.random.default_rng(graine); X = r.normal(size=(n, d)).astype(np.float32)
    y = (X[:, 0] > 0).astype(int) + (X[:, 1] > 0.5).astype(int); Y = np.eye(k, dtype=np.float32)[y]
    return X, Y, np.ones(n, np.float32)


class Traits(unittest.TestCase):
    def test_ngrammes_deterministes_et_normes(self):
        a, b = C.ngrammes('Une phrase suffit.', 't:'), C.ngrammes('Une phrase suffit.', 't:')
        self.assertTrue(np.array_equal(a, b)); self.assertAlmostEqual(float(np.linalg.norm(a)), 1.0, places=5)

    def test_paire_couverture(self):
        f = C.paire('Série de 128 mesures', 'La série compte 128 mesures')
        self.assertGreater(f[0], 0.5); self.assertEqual(f[2], 0.0)       # nombres tous présents


class Apprentissage(unittest.TestCase):
    cfg = dict(epoques=12, cache=0, lr=0.1, l2=1e-4, lot=8, graine=3, ckpt_tous=4, traits=[], classes=['a', 'b', 'c'])

    def test_probabilites_sommees_a_un(self):
        X, Y, w = donnees(); P = C.apprendre(X, Y, w, self.cfg, C.Numpy())
        p, _ = C.proba(C.Numpy(), P, X); self.assertTrue(np.allclose(p.sum(1), 1, atol=1e-5))

    def test_reprise_identique_au_bit_pres(self):
        X, Y, w = donnees(); d = dossier_essai('reprise')
        P1 = C.apprendre(X, Y, w, self.cfg, C.Numpy(), dossier=d, empreinte='e')
        P2 = C.apprendre(X, Y, w, self.cfg, C.Numpy(), reprise=os.path.join(d, 'ckpt_e00004.npz'), empreinte='e')
        self.assertTrue(all(np.array_equal(P1[k], P2[k]) for k in P1))

    def test_reprise_refusee_si_donnees_changees(self):
        X, Y, w = donnees(); d = dossier_essai('reprise_refus')
        C.apprendre(X, Y, w, self.cfg, C.Numpy(), dossier=d, empreinte='e1')
        with self.assertRaises(SystemExit):
            C.apprendre(X, Y, w, self.cfg, C.Numpy(), reprise=os.path.join(d, 'ckpt_e00004.npz'), empreinte='e2')

    def test_couche_cachee(self):
        X, Y, w = donnees(); cfg = dict(self.cfg, cache=6)
        P = C.apprendre(X, Y, w, cfg, C.Numpy()); self.assertIn('W1', P)

    def test_mesures(self):
        m = C.mesures([('a', 'a'), ('b', 'a')], ['a', 'b']); self.assertEqual(m['exactitude'], 0.5)


if __name__ == '__main__':
    unittest.main()
