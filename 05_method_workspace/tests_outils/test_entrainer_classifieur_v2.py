"""Tests unitaires de entrainer_classifieur v2 (registre central des dossiers, cc_lib_v4.chemin ; jeu lu par donnees_entrainement v2).
(a) Non-régression : cas de la suite v1 (traits déterministes, probabilités, reprise exacte au bit près, reprise refusée si les
données changent, couche cachée, mesures) et cycle complet entrainer → predire (points de reprise, modèle, configuration,
métriques, version suivante, prédictions). (b) Registre : espace fictif dont le registre renomme les dossiers ; spécification, jeu
et embeddings lus, modèle et événement écrits dans les dossiers renommés. La racine vue par cc_lib_v4 est remplacée le temps du test."""
import os, sys, io, json, glob, hashlib, contextlib, unittest
import numpy as np
from aide_tests_v2 import dossier_essai, importer_version, chemin, chemins
import cc_lib_v4 as L4
V, VD = 2, 2                                                # entrainer_classifieur v2, qui lit son jeu par donnees_entrainement v2
SPEC = dict(tache='t', entree=['texte'], traits=['ngrammes', 'embeddings:m'], classes=['x', 'y'], poids={'or': 1.0, 'argent': 0.4, 'bronze': 0.1})
TEXTES = {f'{c}{i}': ('alpha' if c == 'x' else 'beta') + f' exemple {i}' for c in 'xy' for i in range(6)}


def espace(nom, renommer=False):
    """Racine d'un espace d'essai ; renommer : registre outils/_gestion/chemins_v1.json qui renomme chaque dossier en <clé>_renomme."""
    r = dossier_essai(nom)
    if renommer:
        g = os.path.join(r, 'outils', '_gestion'); os.makedirs(g)
        with open(os.path.join(g, 'chemins_v1.json'), 'w', encoding='utf-8') as f:
            json.dump({'chemins': {k: k + '_renomme' for k in chemins() if k != 'outils'}}, f)
    return r


def importer_outils():
    """(D, C) importés pour la racine que voit cc_lib_v4 à cet instant ; C reçoit ce D comme module donnees_entrainement_v2
    (encore candidat tant qu'il n'est pas adopté : son raccourci de compatibilité ne le trouverait pas)."""
    D = importer_version('donnees_entrainement', VD); sauve = sys.modules.get('donnees_entrainement_v2')
    sys.modules['donnees_entrainement_v2'] = D
    try: C = importer_version('entrainer_classifieur', V)
    finally:
        if sauve is None: sys.modules.pop('donnees_entrainement_v2', None)
        else: sys.modules['donnees_entrainement_v2'] = sauve
    return D, C


_, C = importer_outils()                                    # cas sans fichier de l'espace (traits, apprentissage)


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
        X, Y, w = donnees(); d = dossier_essai('ec_reprise')
        P1 = C.apprendre(X, Y, w, self.cfg, C.Numpy(), dossier=d, empreinte='e')
        P2 = C.apprendre(X, Y, w, self.cfg, C.Numpy(), reprise=os.path.join(d, 'ckpt_e00004.npz'), empreinte='e')
        self.assertTrue(all(np.array_equal(P1[k], P2[k]) for k in P1))

    def test_reprise_refusee_si_donnees_changees(self):
        X, Y, w = donnees(); d = dossier_essai('ec_reprise_refus')
        C.apprendre(X, Y, w, self.cfg, C.Numpy(), dossier=d, empreinte='e1')
        with self.assertRaises(SystemExit):
            C.apprendre(X, Y, w, self.cfg, C.Numpy(), reprise=os.path.join(d, 'ckpt_e00004.npz'), empreinte='e2')

    def test_couche_cachee(self):
        X, Y, w = donnees(); cfg = dict(self.cfg, cache=6)
        P = C.apprendre(X, Y, w, cfg, C.Numpy()); self.assertIn('W1', P)

    def test_mesures(self):
        m = C.mesures([('a', 'a'), ('b', 'a')], ['a', 'b']); self.assertEqual(m['exactitude'], 0.5)


class Cycle(unittest.TestCase):
    """entrainer puis predire sur un espace d'essai : spécification, jeu d'or (12 exemples) et embeddings en cache."""
    renommer = False

    def setUp(self):
        self.r = espace('ec_registre' if self.renommer else 'ec_defaut', self.renommer)
        sauve = L4.RACINE_CC; L4.RACINE_CC = self.r; self.addCleanup(setattr, L4, 'RACINE_CC', sauve)   # racine vue par les outils et leur journal
        self.D, self.C = importer_outils(); E = self.D.E
        os.makedirs(os.path.join(E, self.D.SPECS))
        with open(os.path.join(E, self.D.SPECS, 't_v1.json'), 'w', encoding='utf-8') as f: json.dump(SPEC, f)
        t = os.path.join(E, 'traits', 'm'); os.makedirs(t)                       # cache d'embeddings (clé = empreinte du texte)
        with open(os.path.join(t, 'vecteurs_l_v1.json'), 'w', encoding='utf-8') as f:
            json.dump({hashlib.sha256(x.encode()).hexdigest()[:16]: [1.0, 0.0, 0.5, 0.0] if x.startswith('alpha') else [0.0, 1.0, 0.0, 0.5]
                       for x in TEXTES.values()}, f)
        self.w = dossier_essai('ec_travail'); self.mt = os.path.join(self.w, 'mt.jsonl'); et = os.path.join(self.w, 'etiquettes.json')
        with open(self.mt, 'w', encoding='utf-8') as f: f.write(''.join(json.dumps(dict(id=i, texte=x)) + '\n' for i, x in TEXTES.items()))
        with open(et, 'w', encoding='utf-8') as f: json.dump({i: i[0] for i in TEXTES}, f)
        with contextlib.redirect_stdout(io.StringIO()):
            self.D.collecter(['t', '--taches', self.mt, '--etiquettes', et, '--qualite', 'or', '--source', 'reference', '--travail', 'essai'])

    def entrainer(self):
        with contextlib.redirect_stdout(io.StringIO()): self.C.entrainer(['t', '--nom', 'essai', '--epoques', '3', '--peripherique', 'cpu'])

    def test_entrainer_puis_predire(self):
        self.assertEqual(len(self.C.vecteurs('m')), len(TEXTES))
        self.entrainer(); d = chemin('entrainement', 'modeles', 't', 'essai_v1', racine=self.r)
        self.assertEqual(sorted(os.listdir(d)), ['ckpt_e00003.npz', 'config.json', 'metriques.json', 'modele.npz'])
        cfg = json.load(open(os.path.join(d, 'config.json'), encoding='utf-8')); met = json.load(open(os.path.join(d, 'metriques.json'), encoding='utf-8'))
        self.assertEqual((cfg['version'], cfg['exemples'], cfg['moteur'], cfg['par_qualite']), (1, 12, 'cpu-numpy', {'or': 12}))
        self.assertEqual(met['validation_croisee_or']['n'], 12)
        self.entrainer(); self.assertTrue(os.path.isdir(chemin('entrainement', 'modeles', 't', 'essai_v2', racine=self.r)))   # jamais réécrit
        out = dossier_essai('ec_predictions')
        with contextlib.redirect_stdout(io.StringIO()): self.C.predire([d, self.mt, out])
        P = json.load(open(os.path.join(out, 'predictions_essai_v1.json'), encoding='utf-8'))
        self.assertEqual(sorted(P), sorted(TEXTES)); self.assertTrue(all(p['decision'] in ('auto', 'deleguer') for p in P.values()))
        self.assertEqual(len(glob.glob(chemin('journal', '*', '*_entrainer_classifieur_v2_*.json', racine=self.r))), 2)


class Registre(Cycle):
    renommer = True

    def test_dossiers_renommes(self):
        E = chemin('entrainement', racine=self.r)
        self.assertEqual((self.D.E, self.C.E), (E, E)); self.assertTrue(os.path.basename(E).endswith('_renomme'))
        self.test_entrainer_puis_predire()                                       # lit spécification, jeu et embeddings renommés ; écrit le modèle et l'événement
        self.assertTrue(os.path.isfile(os.path.join(E, 'modeles', 't', 'essai_v1', 'modele.npz')))
        self.assertEqual(sorted(d for d in os.listdir(self.r) if d != 'outils' and not d.endswith('_renomme')), [])   # aucun nom par défaut


if __name__ == '__main__':
    unittest.main()
