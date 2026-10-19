"""Tests de croiser_demandes_v3 (contrôle des leçons LC-008 et LC-009), sur un docx synthétique écrit avec zipfile et des entrées minimales
(classement JSON, microtâches JSONL, dossiers de blocs en Markdown). Testés :
- écarts E1 à E4 selon le type de la demande (modifier, supprimer, question, aucune) et ce que la passe a fait à l'ancre ;
- écarts E5 et E6 selon le statut annoncé dans la réponse du fil : la dernière version du dossier de chaque bloc l'emporte, plusieurs blocs
  sont réunis, un statut d'attente écarte E6 ;
- D1 (texte d'ancrage supprimé mais repris ailleurs) et son seuil --seuil-deplace ;
- l'auteur de la passe (--auteur) : les révisions d'un autre auteur ne comptent pas, mais un paragraphe supprimé par n'importe quel auteur
  compte comme supprimé ;
- sortie versionnée (aucune nouvelle version si le contenu est identique), résumé imprimé, événement du journal redirigé vers le dossier d'essai ;
- refus : demande absente des microtâches (KeyError) ; ligne de commande sans argument (échec ; défaut : pas de message d'usage)."""
import os, sys, io, json, glob, zipfile, itertools, contextlib, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, OUTILS
import cc_lib_v4 as L4

CD = importer_version('croiser_demandes', 3); OUTIL = chemin_version('croiser_demandes', 3)
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"'
CLAUDE = 'Correction - Claude'; COLLEGUE = 'Collègue A'
_id = itertools.count(1)


def run(t): return f'<w:r><w:t xml:space="preserve">{t}</w:t></w:r>'
def ins(t, auteur=CLAUDE): return f'<w:ins w:id="{next(_id)}" w:author="{auteur}" w:date="2026-10-01T00:00:00Z">{run(t)}</w:ins>'
def sup(t, auteur=CLAUDE): return f'<w:del w:id="{next(_id)}" w:author="{auteur}" w:date="2026-10-01T00:00:00Z"><w:r><w:delText xml:space="preserve">{t}</w:delText></w:r></w:del>'
def par(*morceaux): return '<w:p>' + ''.join(morceaux) + '</w:p>'
def titre(t): return f'<w:p><w:pPr><w:pStyle w:val="Titre1"/></w:pPr>{run(t)}</w:p>'


class Doc:
    """Liste de paragraphes ; l'indice d'un paragraphe nommé est celui que l'outil lit (ordre du document)."""
    def __init__(self): self.ps = []; self.idx = {}
    def ajouter(self, xml, nom=None):
        if nom: self.idx[nom] = len(self.ps)
        self.ps.append(xml)
    def section(self, nom, *paragraphes, cle=None):
        self.ajouter(titre(nom))
        for k, xml in enumerate(paragraphes): self.ajouter(xml, cle if k == 0 else None)


DEPLACE = 'Les fichiers archivés sont restaurés lentement avant lecture.'


def construire():
    d = Doc()
    d.section('Section A', par(sup('ancien libellé complet de colonne'), run(' fin')), cle='e1')
    d.section('Section B', par(sup('ancienne formulation'), ins('nouvelle formulation')), cle='ok')
    d.section('Section C', par(run('Paragraphe resté intact.')), cle='e2')
    d.section('Section D', par(sup('résultat provisoire'), run(' conservé ici')), cle='e3')
    d.section('Section E', par(run('Texte'), ins(' ajouté sans demande')), cle='e4')
    d.section('Section F', par(run('Rien de changé ici.')), cle='e5')
    d.section('Section G', par(run('Décision laissée à l’auteur.')), cle='attente')
    d.section('Section H', par(sup(DEPLACE)), par(run(DEPLACE)), cle='deplace')
    d.section('Section I', par(sup('texte retiré', COLLEGUE), run(' suite')), cle='autre')
    d.section('Section J', par(sup('Phrase obsolète retirée', COLLEGUE)), cle='supprime_autre')
    d.section('Section K', par(run('Texte'), ins(' ajouté', CLAUDE)), cle='traite_ok')
    return d


# id : (nom du paragraphe, type, fil)
DEMANDES = dict(d01=('e1', 'modifier', ''), d02=('ok', 'modifier', ''), d03=('e2', 'supprimer', ''), d04=('e3', 'question', ''),
                d05=('e4', 'aucune', ''), d06=('e5', 'modifier', '11'), d07=('attente', 'modifier', '12'), d08=('deplace', 'modifier', ''),
                d09=('autre', 'modifier', ''), d10=('supprime_autre', 'supprimer', ''), d11=('traite_ok', 'modifier', '13'))


def fil(num, statut, role='auteur'):
    return f'### Fil {num} ({role}) ancre de test\nDemande de test.\n[Correction rev1 | {statut}] Réponse de test.\n\n'


class Croiser(unittest.TestCase):
    def setUp(self):
        self.d = dossier_essai('croiser_demandes_v3'); self.cc = os.path.join(self.d, 'espace')
        sauve = (L4.RACINE_CC, os.environ.get('CC_BANC'))

        def restaurer():
            L4.RACINE_CC = sauve[0]
            if sauve[1] is None: os.environ.pop('CC_BANC', None)
            else: os.environ['CC_BANC'] = sauve[1]
        self.addCleanup(restaurer)
        L4.RACINE_CC = self.cc                                       # le journal de l'outil va dans le dossier d'essai
        doc = construire(); self.idx = doc.idx
        self.docx = os.path.join(self.d, 'rapport_v1.docx')
        with zipfile.ZipFile(self.docx, 'w') as z: z.writestr('word/document.xml', f'<w:document {W}><w:body>{"".join(doc.ps)}</w:body></w:document>')
        self.cls = os.path.join(self.d, 'classement_demandes.json'); self.mt = os.path.join(self.d, 'microtaches.jsonl')
        with open(self.cls, 'w', encoding='utf-8') as f: json.dump({i: dict(final=t, regle=f'regle_{t}') for i, (_, t, _) in DEMANDES.items()}, f)
        with open(self.mt, 'w', encoding='utf-8') as f:
            for i, (nom, t, fl) in DEMANDES.items():
                f.write(json.dumps(dict(id=i, index=self.idx[nom], genre='commentaire', **({'fil': fl} if fl else {})), ensure_ascii=False) + '\n')
        self.dos = os.path.join(self.d, 'dossiers_agents'); os.makedirs(self.dos)
        # B1 : v1 annonce une attente pour le fil 11, v2 (la dernière) le dit « Traité » ; B2 : un autre bloc, un fil « Traité »
        self.ecrire('dossier_B1_v1.md', '## Bloc B1\n\n' + fil(11, 'En attente') + fil(12, 'En attente de décision') + '## Fin\n')
        self.ecrire('dossier_B1_v2.md', '## Bloc B1\n\n' + fil(11, 'Traité') + fil(12, 'En attente de décision') + '## Fin\n')
        self.ecrire('dossier_B2_v1.md', '## Bloc B2\n\n' + fil(13, 'Traité') + '## Fin\n')

    def ecrire(self, nom, texte):
        with open(os.path.join(self.dos, nom), 'w', encoding='utf-8') as f: f.write(texte)

    def lancer(self, *extra, sortie='sortie'):
        sauve = sys.argv; sys.argv = [OUTIL, self.docx, self.cls, self.mt, self.dos, os.path.join(self.d, sortie), *extra]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out): CD.main()
        finally: sys.argv = sauve
        return out.getvalue()

    def resultat(self, sortie='sortie', v=1):
        with open(os.path.join(self.d, sortie, f'croisement_demandes_v{v}.json'), encoding='utf-8') as f: return json.load(f)

    def test_ecarts_selon_le_type(self):
        self.lancer(); R = self.resultat()
        self.assertEqual(len(R), 11)
        self.assertEqual(R['d01']['ecarts'], ['E1']); self.assertEqual(R['d01']['priorite'], 1)       # modifier : suppression seule faite
        self.assertGreater(R['d01']['ancre']['dele'], 0); self.assertEqual(R['d01']['ancre']['ins'], 0)
        self.assertEqual(R['d01']['ancre']['index'], self.idx['e1']); self.assertEqual(R['d01']['section']['nom'], 'Section A')
        self.assertEqual(R['d02']['ecarts'], []); self.assertIsNone(R['d02']['priorite'])               # supprimé et remplacé : conforme
        self.assertEqual((R['d02']['ancre']['ins'], R['d02']['section']['ins']), (len('nouvelle formulation'),) * 2)
        self.assertEqual(R['d03']['ecarts'], ['E2']); self.assertEqual(R['d03']['priorite'], 2)         # suppression demandée, rien fait
        self.assertEqual(R['d04']['ecarts'], ['E3']); self.assertEqual(R['d04']['priorite'], 2)         # question traitée par suppression
        self.assertEqual(R['d05']['ecarts'], ['E4']); self.assertEqual(R['d05']['priorite'], 3)         # aucune action demandée, texte modifié
        self.assertEqual(R['d01']['type'], 'modifier'); self.assertEqual(R['d03']['regle'], 'regle_supprimer')

    def test_statuts_annonces(self):
        self.lancer(); R = self.resultat()
        self.assertEqual(R['d06']['statut_annonce'], 'Traité')                      # la v2 du bloc B1 l'emporte sur la v1 (« En attente »)
        self.assertEqual(R['d06']['ecarts'], ['E5', 'E6']); self.assertEqual(R['d06']['priorite'], 2)   # « Traité » sans aucune révision
        self.assertEqual(R['d07']['statut_annonce'], 'En attente de décision')
        self.assertEqual(R['d07']['ecarts'], [])                                    # statut d'attente : pas de E6
        self.assertEqual(R['d11']['statut_annonce'], 'Traité'); self.assertEqual(R['d11']['ecarts'], [])   # fil du bloc B2, révision à l'ancre
        self.assertIsNone(R['d01']['statut_annonce'])                               # demande sans fil

    def test_texte_deplace_et_seuil(self):
        self.lancer(); R = self.resultat()
        self.assertEqual(R['d08']['ecarts'], ['D1']); self.assertEqual(R['d08']['priorite'], 3)         # ni E1 ni E3 : le texte est repris ailleurs
        self.assertTrue(R['d08']['ancre']['supprime']); self.assertEqual(R['d08']['ancre']['couverture_ailleurs'], 1.0)
        self.assertEqual(R['d08']['section']['par_supprimes'], 1)
        self.lancer('--seuil-deplace', '1.1', sortie='sortie_seuil'); R2 = self.resultat('sortie_seuil')
        self.assertEqual(R2['d08']['ecarts'], ['E1'])                                # seuil inatteignable : plus de « déplacé », la suppression seule est signalée
        self.assertEqual(R2['d08']['ancre']['couverture_ailleurs'], 1.0)

    def test_auteur_de_la_passe(self):
        self.lancer(); R = self.resultat()
        self.assertEqual(R['d09']['ancre']['dele'], 0); self.assertEqual(R['d09']['ecarts'], ['E6'])   # suppression d'un autre auteur : non comptée
        self.assertTrue(R['d10']['ancre']['supprime']); self.assertEqual(R['d10']['ancre']['dele'], 0)
        self.assertEqual(R['d10']['ecarts'], [])                                    # paragraphe supprimé par n'importe quel auteur : pas de E2
        self.lancer('--auteur', COLLEGUE, sortie='sortie_autre'); R2 = self.resultat('sortie_autre')
        self.assertEqual(R2['d09']['ancre']['dele'], len('texte retiré')); self.assertEqual(R2['d09']['ecarts'], ['E1'])
        self.assertEqual(R2['d02']['ancre']['ins'], 0)                              # les révisions de la première passe ne sont plus les siennes

    def test_sortie_versionnee_resume_et_journal(self):
        out = self.lancer()
        self.assertIn('croisement_demandes_v1.json', out); self.assertIn('11 demandes', out)
        for code, n in (('E1', 1), ('E2', 1), ('E3', 1), ('E4', 1), ('E5', 1), ('E6', 2), ('D1', 1)): self.assertIn(f'{code} {n} (', out, code)
        self.lancer()                                                               # même contenu : pas de nouvelle version
        self.assertEqual(sorted(os.listdir(os.path.join(self.d, 'sortie'))), ['croisement_demandes_v1.json'])
        self.lancer('--seuil-deplace', '1.1')                                       # contenu différent : v2, la v1 reste intacte
        self.assertEqual(sorted(os.listdir(os.path.join(self.d, 'sortie'))), ['croisement_demandes_v1.json', 'croisement_demandes_v2.json'])
        self.assertEqual(self.resultat()['d08']['ecarts'], ['D1'])
        evts = sorted(glob.glob(os.path.join(self.cc, '*', '*', '*_croiser_demandes_v3_*.json')))
        self.assertEqual(len(evts), 2)                                              # un événement par exécution, dans l'espace d'essai
        with open(evts[0], encoding='utf-8') as f: e = json.load(f)
        self.assertEqual((e['outil'], e['version'], e['type']), ('croiser_demandes', 3, 'croisement'))
        self.assertEqual(e['donnees']['demandes'], 11); self.assertEqual(e['donnees']['ecarts']['E6'], 2)

    def test_demande_absente_des_microtaches(self):
        with open(self.cls, encoding='utf-8') as f: c = json.load(f)
        c['d99'] = dict(final='modifier', regle='r')
        with open(self.cls, 'w', encoding='utf-8') as f: json.dump(c, f)
        with self.assertRaises(KeyError): self.lancer()                             # refus : la demande n'a pas de microtâche
        self.assertFalse(os.path.exists(os.path.join(self.d, 'sortie')))            # rien n'est écrit

    def env(self): return dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS]))

    def test_ligne_de_commande_sans_argument(self):
        r = subprocess.run([sys.executable, OUTIL], capture_output=True, text=True, env=self.env())
        self.assertNotEqual(r.returncode, 0)

    @unittest.expectedFailure
    def test_ligne_de_commande_usage(self):
        # Défaut : sans argument, l'outil s'arrête sur une trace Python (ValueError) au lieu d'un message d'usage et du code 2 des autres outils.
        r = subprocess.run([sys.executable, OUTIL], capture_output=True, text=True, env=self.env())
        self.assertEqual(r.returncode, 2); self.assertIn('USAGE', r.stderr.upper())


if __name__ == '__main__':
    unittest.main()
