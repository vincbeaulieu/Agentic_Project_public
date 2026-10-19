"""v7 de la suite : mêmes cas, contre file_lmstudio_v7 (ouvrier trouvé par cc_lib_v4.chemin_outil). Tests unitaires de file_lmstudio v6 (registre central des dossiers, cc_lib_v4.chemin). (a) Non-régression : cas des suites v1 et v2
(lot bien formé, consigne citée et non répétée, valeurs permises, pas d'écrasement en mode local, paires d'embeddings, file locale à
côté de l'espace), installation de l'ouvrier, récolte des résultats (format microtaches) et des vecteurs (versés au cache du répertoire
d'entraînement, clé = empreinte du texte). (b) Registre : espace fictif dont le registre renomme les dossiers ; le cache d'embeddings
et les événements vont dans les dossiers renommés. La file elle-même (00_espace_cloud_claude/file_lmstudio) n'est pas un dossier de
l'espace de compétences. Aucun appel à LM Studio ni au réseau : les résultats « rapatriés » sont écrits par le test."""
import os, io, json, glob, hashlib, contextlib, unittest
from aide_tests_v2 import dossier_essai, importer_version, chemin, chemins
import cc_lib_v4 as L4
V = 7                                                       # version essayée (candidate tant qu'elle n'est pas adoptée)
F0 = importer_version('file_lmstudio', V)                   # racine réelle de l'espace (emplacement de la file locale)


def espace(nom, renommer=False):
    """Racine d'un espace d'essai ; renommer : registre outils/_gestion/chemins_v1.json qui renomme chaque dossier en <clé>_renomme."""
    r = dossier_essai(nom)
    if renommer:
        g = os.path.join(r, 'outils', '_gestion'); os.makedirs(g)
        with open(os.path.join(g, 'chemins_v1.json'), 'w', encoding='utf-8') as f:
            json.dump({'chemins': {k: k + '_renomme' for k in chemins() if k != 'outils'}}, f)
    return r


def jsonl(f): return [json.loads(x) for x in open(f, encoding='utf-8') if x.strip()]


class Emplacement(unittest.TestCase):
    def test_file_locale_a_cote_de_l_espace(self):
        self.assertEqual(os.path.dirname(os.path.dirname(F0.LOCALE)), os.path.dirname(F0.RACINE_CC))
        self.assertTrue(F0.LOCALE.endswith(os.path.join('00_espace_cloud_claude', 'file_lmstudio')))


class Base(unittest.TestCase):
    renommer = False

    def setUp(self):
        self.r = espace('fl_registre' if self.renommer else 'fl_defaut', self.renommer)
        sauve = L4.RACINE_CC; L4.RACINE_CC = self.r; self.addCleanup(setattr, L4, 'RACINE_CC', sauve)   # racine vue par l'outil et son journal
        self.F = F = importer_version('file_lmstudio', V)
        F.ENVOI = dossier_essai('fl_envoi'); F.LOCAL = True; F.RAPATRIE = dossier_essai('fl_rapatrie')    # transport : dossiers d'essai
        self.w = dossier_essai('fl_travail'); self.src = os.path.join(self.w, 'mt.jsonl')
        with open(self.src, 'w', encoding='utf-8') as f:
            f.write(json.dumps(dict(id='D-1', type='MT-DEMANDE', texte='Faire plus simple')) + '\n')
            f.write(json.dumps(dict(id='P-1', type='MT-PRESENCE', a='A', b='B')) + '\n')

    def appel(self, fn, args):
        with contextlib.redirect_stdout(io.StringIO()) as s: fn(args)
        return s.getvalue()

    def rapatrier(self, lot, lignes):                       # ce que l'ouvrier du PC aurait rendu
        os.makedirs(os.path.join(self.F.RAPATRIE, 'sortie'), exist_ok=True)
        with open(os.path.join(self.F.RAPATRIE, 'sortie', f'{lot}_resultats.jsonl'), 'w', encoding='utf-8') as f:
            f.write(''.join(json.dumps(x) + '\n' for x in lignes))

    def recolter_vecteurs(self):
        self.appel(self.F.deposer_embeddings, [self.src, self.w, '--lot', 'e'])
        self.rapatrier('e_v1', [dict(id=i, modele='nomic/embed', r=[float(n), 1.0]) for n, i in enumerate(('D-1#t', 'P-1#a', 'P-1#b'))])
        self.appel(self.F.recolter, [self.w, '--lot', 'e_v1'])
        f = chemin('entrainement', 'traits', 'nomic_embed', 'vecteurs_e_v1_v1.json', racine=self.r)
        self.assertTrue(os.path.isfile(os.path.join(self.w, 'file', 'sortie', 'e_v1_vecteurs_v1.json')))
        cache = json.load(open(f, encoding='utf-8'))
        self.assertEqual(cache, {hashlib.sha256(t.encode()).hexdigest()[:16]: [float(n), 1.0] for n, t in enumerate(('Faire plus simple', 'A', 'B'))})
        return f

    def evenements(self, type_):
        return [e for e in (json.load(open(f, encoding='utf-8')) for f in glob.glob(chemin('journal', '*', f'*_file_lmstudio_v{V}_*.json', racine=self.r)))
                if e['type'] == type_]


class NonRegression(Base):
    def test_deposer_demandes(self):
        self.appel(self.F.deposer, [self.src, self.w, '--lot', 'l', '--modele', 'm', '--prio', '1', '--type', 'MT-DEMANDE'])
        L = jsonl(os.path.join(self.F.ENVOI, 'entree', 'l_v1.jsonl'))
        self.assertEqual(len(L), 1); t = L[0]
        self.assertEqual((t['consigne'], t['modele'], t['prio']), ('MT-DEMANDE_v1', 'm', 1.0))
        self.assertIn('modifier', t['valeurs']); self.assertNotIn('systeme', t)
        self.assertEqual(jsonl(os.path.join(self.w, 'file', 'entree', 'l_v1.jsonl')), L)            # copie de travail identique
        self.assertEqual(len(self.evenements('deposer')), 1)

    def test_pas_d_ecrasement_local(self):
        self.appel(self.F.deposer, [self.src, self.w, '--lot', 'l', '--modele', 'm', '--type', 'MT-DEMANDE'])
        with self.assertRaises(SystemExit): self.F.envoyer('entree/l_v1.jsonl', 'x')

    def test_embeddings_paires(self):
        self.appel(self.F.deposer_embeddings, [self.src, self.w, '--lot', 'e'])
        ids = [x['id'] for x in jsonl(os.path.join(self.F.ENVOI, 'entree', 'e_v1.jsonl'))]
        self.assertEqual(ids, ['D-1#t', 'P-1#a', 'P-1#b'])

    def test_installer(self):
        L = json.loads(self.appel(self.F.installer, [self.w]).strip().splitlines()[-1])
        self.assertEqual(len(L), 3 + len(self.F.CONSIGNE))
        ps1 = [x['local'] for x in L if x['local'].endswith('.ps1')]
        self.assertEqual(len(ps1), 1); self.assertEqual(open(ps1[0], 'rb').read(3), b'\xef\xbb\xbf')        # BOM pour PowerShell 5.1
        self.assertTrue(os.path.isfile(os.path.join(self.w, 'file', 'consignes', 'MT-DEMANDE_v1_v1.txt')))

    def test_recolter_resultats(self):
        self.rapatrier('l_v1', [dict(id='D-1', modele='m', r='modifier', ms=12, tokens=3), dict(id='D-2', modele='m', erreur='delai')])
        self.assertIn('2 résultat(s), 1 erreur(s)', self.appel(self.F.recolter, [self.w, '--lot', 'l_v1']))
        rows = json.load(open(os.path.join(self.w, 'file', 'sortie', 'l_v1_resultats_v1.json'), encoding='utf-8'))
        self.assertEqual(rows, [['m', 'D-1', 'modifier', 12, 3, 0], ['m', 'D-2', None, None, None, 0]])
        self.assertEqual(len(self.evenements('recolter')), 1)

    def test_recolter_vecteurs_dans_le_cache_d_entrainement(self):
        self.recolter_vecteurs()


class Registre(Base):
    renommer = True

    def test_cache_et_journal_renommes(self):
        f = self.recolter_vecteurs()                                               # écrit le cache dans le dossier renommé
        self.assertTrue(f.startswith(chemin('entrainement', racine=self.r) + os.sep))
        self.assertTrue(os.path.basename(chemin('entrainement', racine=self.r)).endswith('_renomme'))
        self.rapatrier('l_v1', [dict(id='D-1', modele='m', r='modifier', ms=12, tokens=3)])
        self.appel(self.F.recolter, [self.w, '--lot', 'l_v1'])
        self.assertEqual((len(self.evenements('deposer_embeddings')), len(self.evenements('recolter'))), (1, 1))   # journal renommé
        self.assertEqual(sorted(d for d in os.listdir(self.r) if d != 'outils' and not d.endswith('_renomme')), [])   # aucun nom par défaut


if __name__ == '__main__':
    unittest.main()
