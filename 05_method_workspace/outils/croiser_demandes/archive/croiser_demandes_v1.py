"""
OUTIL: croiser_demandes
VERSION: 1
RESUME: Contrôle déterministe des leçons LC-008 et LC-009 : croise le type de chaque demande (fil de commentaire ou segment du transcript, classé par microtaches + règles) avec ce que la passe de révision précédente a réellement fait au paragraphe d'ancrage et dans sa section (caractères insérés et supprimés par l'auteur de cette passe, paragraphe supprimé) et avec le statut annoncé dans sa réponse ; rend les écarts typés et priorisés.
USAGE: python3 croiser_demandes_v1.py <docx> <classement_demandes.json> <microtaches.jsonl> <dossiers_dir> <sortie_dossier> [--auteur "Correction - Claude"]
ENTREES: docx révisé ; classement {id: {final, regle}} ; microtaches (index, genre) ; dossier_<bloc>_vN.md (réponses « [Correction rev1 | statut] »)
SORTIES: croisement_demandes_vN.json {id: {type, statut_annonce, ancre:{ins,del,supprime}, section:{ins,del,par_supprimes}, ecarts:[code], priorite}} ; résumé ; événement dans journal/
CATEGORIE: revision_rapport
BANC: -
REMPLACE: -
"""
import sys, os, re, json, glob, zipfile, collections
from lxml import etree
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import evenement, ecrire_versionne
import detecteurs_rapport_v5 as DR
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'; q = lambda t: f'{{{W}}}{t}'
ECARTS = {  # code : (priorité 1 forte … 3 faible, libellé)
    'E1': (1, 'modification demandée, suppression seule faite (LC-008)'),
    'E2': (2, 'suppression demandée, rien de supprimé'),
    'E3': (2, 'question traitée par une suppression (LC-008 : lire la demande)'),
    'E4': (3, 'aucune action demandée, texte modifié'),
    'E5': (2, 'statut « Traité » annoncé, aucune révision à l’ancre ni dans la section (LC-009)'),
    'E6': (3, 'modification demandée, aucune révision à l’ancre ni dans la section, sans statut d’attente')}


def main():
    a = sys.argv[1:]; docx, fcls, fmt, dd, out = a[:5]
    auteur = a[a.index('--auteur') + 1] if '--auteur' in a else 'Correction - Claude'
    z = zipfile.ZipFile(docx); P = DR.vues(z); doc = etree.fromstring(z.read('word/document.xml'))
    rev = []                                       # caractères insérés / supprimés par l'auteur, par paragraphe
    for xp in doc.iter(q('p')):
        ins = sum(len(''.join(t.text or '' for t in e.iter(q('t')))) for e in xp.iter(q('ins')) if e.get(q('author')) == auteur)
        dl = sum(len(''.join(t.text or '' for t in e.iter(q('delText'), q('t')))) for e in xp.iter(q('del')) if e.get(q('author')) == auteur)
        rev.append((ins, dl))
    sec = {}; cur = '(début)'
    for p in P:
        if p['titre'] and p['ori'].strip(): cur = p['ori'].strip()[:80]
        sec[p['i']] = cur
    par_sec = collections.defaultdict(list)
    for p in P: par_sec[sec[p['i']]].append(p['i'])
    statut = {}
    for f in glob.glob(os.path.join(dd, 'dossier_B*_v*.md')):
        for m in re.finditer(r'^### Fil (\d+) [^\n]*\n(.*?)(?=^### |^## )', open(f, encoding='utf-8').read(), re.S | re.M):
            s = re.search(r'\[Correction rev1 \| ([^\]]+)\]', m.group(2))
            if s: statut[m.group(1)] = s.group(1).strip()
    cls = json.load(open(fcls, encoding='utf-8'))
    X = {json.loads(l)['id']: json.loads(l) for l in open(fmt, encoding='utf-8') if l.strip()}
    res = {}
    for i, c in sorted(cls.items()):
        x = X[i]; k = x['index']; ty = c['final']
        st = statut.get(x.get('fil', ''), '') if x.get('fil') else ''
        ai, ad = rev[k]; anc_sup = bool(P[k]['ori'].strip() and not P[k]['acc'].strip())
        idx = par_sec[sec[k]]; si = sum(rev[j][0] for j in idx); sd = sum(rev[j][1] for j in idx)
        psup = sum(1 for j in idx if P[j]['ori'].strip() and not P[j]['acc'].strip())
        E = []
        if ty == 'modifier' and (ad > 0 or anc_sup) and ai == 0 and si == 0: E.append('E1')
        if ty == 'supprimer' and ad == 0 and sd == 0: E.append('E2')
        if ty == 'question' and (anc_sup or (ad > 0 and ai == 0)): E.append('E3')
        if ty == 'aucune' and (ai or ad): E.append('E4')
        if st.lower().startswith('traité') and not (ai or ad or si or sd): E.append('E5')
        if ty == 'modifier' and not (ai or ad or si or sd) and not re.search(r'attente|décision|hors', st, re.I): E.append('E6')
        res[i] = dict(type=ty, regle=c.get('regle'), statut_annonce=st or None, ancre=dict(index=k, ins=ai, dele=ad, supprime=anc_sup),
                      section=dict(nom=sec[k], ins=si, dele=sd, par_supprimes=psup), ecarts=E,
                      priorite=min([ECARTS[e][0] for e in E], default=None))
    ch, _ = ecrire_versionne(out, 'croisement_demandes', 'json', json.dumps(res, ensure_ascii=False, indent=0, sort_keys=True))
    cpt = collections.Counter(e for r in res.values() for e in r['ecarts'])
    evenement('croiser_demandes', 1, 'croisement', dict(demandes=len(res), ecarts=dict(cpt)))
    print(ch); print(len(res), 'demandes ;', ', '.join(f'{e} {cpt[e]} ({ECARTS[e][1]})' for e in sorted(cpt)))


if __name__ == '__main__':
    main()
