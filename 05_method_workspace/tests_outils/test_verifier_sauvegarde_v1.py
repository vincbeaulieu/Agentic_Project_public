"""Tests de verifier_sauvegarde_v1 sur un état de synchronisation synthétique (modules d'état et d'inventaire factices, fichiers d'essai
sous le dossier d'essai ; ni l'état réel du PC ni le journal de l'espace ne sont touchés) : « SAUVEGARDE À JOUR » (inventaire vide, ou
fichiers confirmés par envoi, par destination, par empreinte dans le même dossier, par empreinte ailleurs pour les fichiers hors
dossiers) ; fichiers non confirmés (contenu modifié, empreinte seulement dans un autre dossier ou pour un fichier racine) ; « EN COURS »
sous le seuil et « EN RETARD » au-delà (code 1, détails triés du plus ancien au plus récent) ; option --seuil-min ; option --details ;
limite de 25 lignes de détail ; événement de contrôle ; code de sortie de la ligne de commande."""
import os, sys, io, glob, json, time, types, runpy, hashlib, contextlib, unittest
from unittest import mock
import cc_lib_v1
from aide_tests_v2 import dossier_essai, chemin_version, importer_version

OUTIL = chemin_version('verifier_sauvegarde', 1)
MODULES_SYNC = ('sync_cloud_pc_v4', 'sync_cloud_pc')


def h16(chemin):
    with open(chemin, 'rb') as f: return hashlib.sha256(f.read()).hexdigest()[:16]


@contextlib.contextmanager
def modules_factices(etat, synchro):
    """Installe les modules d'état factices dans sys.modules le temps d'un import ou d'une exécution, puis restaure."""
    absent = object(); sauve = {k: sys.modules.get(k, absent) for k in MODULES_SYNC}; chemin_sauve = sys.path[:]
    sys.modules['sync_cloud_pc_v4'] = etat; sys.modules['sync_cloud_pc'] = synchro
    try: yield
    finally:
        for k, v in sauve.items():
            if v is absent: sys.modules.pop(k, None)
            else: sys.modules[k] = v
        sys.path[:] = chemin_sauve


class Base(unittest.TestCase):
    def setUp(self):
        self.d = dossier_essai('verifier_sauvegarde'); self.cloud = os.path.join(self.d, 'cloud'); self.journal = os.path.join(self.d, 'evenements_essai')
        self.etat = {'pc': {}, 'envoyes': {}}; self.liste = []
        self.V = types.ModuleType('sync_cloud_pc_v4'); self.S = types.ModuleType('sync_cloud_pc')
        self.V.charger = lambda: self.etat; self.V.inventaire = lambda: self.liste; self.S.h16 = h16
        with modules_factices(self.V, self.S): self.VS = importer_version('verifier_sauvegarde', 1, alias=f'verifier_sauvegarde_essai_{id(self)}')
        self.evts = []; self.VS.evenement = lambda outil, version, type_, donnees: self.evts.append((outil, version, type_, donnees))

    def fichier(self, rel, contenu='contenu', age_min=0.0, dest=None, cat='dossier'):
        """Crée un fichier du cloud d'âge donné, l'inscrit à l'inventaire et renvoie son empreinte courte."""
        full = os.path.join(self.cloud, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w', encoding='utf-8') as f: f.write(contenu)
        t = time.time() - age_min * 60; os.utime(full, (t, t))
        self.liste.append((full, rel, dest or rel, cat)); return h16(full)

    def lancer(self, *args):
        sortie = io.StringIO()
        with mock.patch.object(sys, 'argv', ['verifier_sauvegarde_v1.py', *args]), contextlib.redirect_stdout(sortie):
            code = self.VS.main()
        return code, sortie.getvalue()


class AJour(Base):
    def test_inventaire_vide(self):
        code, sortie = self.lancer()
        self.assertEqual(code, 0); self.assertIn('SAUVEGARDE À JOUR', sortie)
        self.assertEqual(self.evts, [('verifier_sauvegarde', 1, 'controle', dict(en_attente=0, en_retard=0, seuil_min=15.0))])

    def test_fichiers_confirmes_de_toutes_les_manieres(self):
        self.etat['envoyes']['NN_a/envoye.txt'] = self.fichier('NN_a/envoye.txt', 'envoyé', age_min=90)             # envoi confirmé
        self.etat['pc']['NN_a/dest.txt'] = self.fichier('NN_a/dest.txt', 'destination', age_min=90)                  # présent sur le PC
        self.etat['pc']['NN_b/ancien_nom.txt'] = self.fichier('NN_b/renomme.txt', 'même contenu', age_min=90)        # même dossier, autre nom
        self.etat['pc']['NN_c/ailleurs.txt'] = self.fichier('racine_hors.txt', 'hors dossiers', age_min=90, cat='hors')   # empreinte quelque part
        code, sortie = self.lancer('--details')
        self.assertEqual(code, 0, sortie); self.assertIn('SAUVEGARDE À JOUR', sortie)
        self.assertEqual(self.evts[0][3]['en_attente'], 0)


class EnAttente(Base):
    def test_contenu_non_confirme(self):
        h = self.fichier('NN_a/modifie.txt', 'nouveau contenu', age_min=1); self.etat['envoyes']['NN_a/modifie.txt'] = 'ancienne000000000'   # modifié depuis l'envoi
        self.etat['pc']['NN_autre/copie.txt'] = self.fichier('NN_b/seulement_ailleurs.txt', 'copie dans un autre dossier', age_min=1)          # autre dossier : ne compte pas
        self.etat['pc']['NN_c/x.txt'] = self.fichier('racine.txt', 'fichier racine', age_min=1, cat='racine')                                  # catégorie sans équivalence
        self.assertNotEqual(h, 'ancienne000000000')
        code, sortie = self.lancer('--details')
        self.assertEqual(code, 0)                                                           # tout est récent : en cours, pas en retard
        self.assertIn('EN COURS : 3 fichier(s) non confirmés', sortie)
        for rel in ('NN_a/modifie.txt', 'NN_b/seulement_ailleurs.txt', 'racine.txt'): self.assertIn(rel, sortie)

    def test_en_cours_puis_details(self):
        self.fichier('NN_a/recent.txt', age_min=2)
        code, sortie = self.lancer()
        self.assertEqual(code, 0); self.assertIn('EN COURS : 1 fichier(s) non confirmés, le plus ancien depuis 2 min', sortie)
        self.assertNotIn('NN_a/recent.txt', sortie)                                          # pas de détail sans --details ni retard
        code, sortie = self.lancer('--details')
        self.assertEqual(code, 0); self.assertIn('NN_a/recent.txt', sortie)

    def test_en_retard_detail_trie_du_plus_ancien(self):
        self.fichier('NN_a/vingt.txt', 'v', age_min=20); self.fichier('NN_a/recent.txt', 'r', age_min=1); self.fichier('NN_a/cinquante.txt', 'c', age_min=50)
        code, sortie = self.lancer()
        self.assertEqual(code, 1)
        self.assertIn('EN RETARD : 3 fichier(s) non confirmés, le plus ancien depuis 50 min', sortie)
        lignes = [l for l in sortie.splitlines() if l.startswith('   ')]                    # détails affichés d'office en cas de retard
        self.assertEqual([l.split()[-1] for l in lignes], ['NN_a/cinquante.txt', 'NN_a/vingt.txt', 'NN_a/recent.txt'])
        self.assertEqual(self.evts[0][3], dict(en_attente=3, en_retard=2, seuil_min=15.0))

    def test_option_seuil(self):
        self.fichier('NN_a/trente.txt', age_min=30)
        self.assertEqual(self.lancer()[0], 1)                                                # seuil par défaut : 15 min
        code, sortie = self.lancer('--seuil-min', '60')
        self.assertEqual(code, 0); self.assertIn('EN COURS', sortie)
        self.assertEqual(self.lancer('--seuil-min', '5')[0], 1)
        self.assertEqual(self.evts[1][3]['seuil_min'], 60.0)

    def test_detail_limite_a_25_lignes(self):
        for k in range(30): self.fichier(f'NN_a/f{k:02d}.txt', f'contenu {k}', age_min=20 + k)
        code, sortie = self.lancer()
        self.assertEqual(code, 1); self.assertIn('EN RETARD : 30 fichier(s)', sortie)
        self.assertEqual(len([l for l in sortie.splitlines() if l.startswith('   ')]), 25)
        self.assertEqual(self.evts[0][3]['en_attente'], 30)


class LigneDeCommande(Base):
    def test_code_de_sortie_du_programme(self):
        """Exécute le fichier comme programme principal : code 0 quand tout est confirmé, 1 en retard ; événement écrit dans le journal d'essai."""
        for age, attendu in ((None, 0), (40, 1)):
            self.liste.clear()
            if age: self.fichier('NN_a/attend.txt', age_min=age)
            sortie = io.StringIO()
            with modules_factices(self.V, self.S), mock.patch.object(cc_lib_v1, 'JOURNAL', self.journal), \
                    mock.patch.object(sys, 'argv', [OUTIL]), contextlib.redirect_stdout(sortie):
                with self.assertRaises(SystemExit) as c: runpy.run_path(OUTIL, run_name='__main__')
            self.assertEqual(c.exception.code, attendu, sortie.getvalue())
        ev = [json.load(open(f, encoding='utf-8')) for f in sorted(glob.glob(os.path.join(self.journal, '*', '*.json')))]
        self.assertEqual(sorted(e['donnees']['en_retard'] for e in ev), [0, 1])           # deux événements (l'ordre des noms de fichiers n'est pas garanti)


if __name__ == '__main__':
    unittest.main()
