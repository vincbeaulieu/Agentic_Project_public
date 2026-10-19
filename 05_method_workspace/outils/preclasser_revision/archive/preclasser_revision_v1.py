"""
OUTIL: preclasser_revision
VERSION: 1
RESUME: Pré-classement déterministe des points d'une réévaluation de révision Word (type de tâche reevaluation_correctifs_rapport) : règles dures qui rendent un verdict sans LLM pour les points triviaux (couverture, lignes de table des matières, révisions de l'auteur seul, notes de l'auteur sans réponse, repères doublons d'un segment du transcript, signalements périmés) ; écrit un module POINTS par bloc, que l'évaluateur contrôle comme un module d'agent ; les agents ne traitent que le résidu.
USAGE: python3 preclasser_revision_v1.py <dossier_dossiers_agents> <alignement_transcript.json> <sortie_dossier_modules> [--couverture 23] [--auteur "Author NAME"]
ENTREES: points_<bloc>_v1.json, vue_rev1_complete_v1.txt, dossier_<bloc>_v1.md (fils), alignement du transcript (segments horodatés)
SORTIES: <sortie>/auto_<bloc>_v1.py (POINTS, OPS=[]) et <sortie>/preclassement_v1.json (décompte par règle et par bloc) ; événement dans journal/
CATEGORIE: revision_rapport
BANC: -
REMPLACE: -
"""
import sys, os, re, json, collections
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import evenement

BLOCS = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9']


def sec(t):
    h, m, s = (int(x) for x in t.split(':')); return h * 3600 + m * 60 + s


def main():
    a = sys.argv[1:]; dd, alignf, out = a[0], a[1], a[2]
    couv = int(a[a.index('--couverture') + 1]) if '--couverture' in a else 23
    auteur = a[a.index('--auteur') + 1] if '--auteur' in a else 'Author NAME'
    os.makedirs(out, exist_ok=True)
    vue = {}
    for l in open(os.path.join(dd, 'vue_rev1_complete_v1.txt'), encoding='utf-8'):
        p = l.rstrip('\n').split(' | ', 3)
        if len(p) == 4: vue[int(p[0])] = dict(pid=p[1], section=p[2], texte=p[3])
    toc_deb = next((i for i, v in vue.items() if v['texte'].strip() == 'Table des matières'), None)
    toc_fin = next((i for i, v in sorted(vue.items()) if toc_deb is not None and i > toc_deb and not re.search(r'\t\d+\s*$', v['texte']) and v['texte'].strip()), None)
    segs = json.load(open(alignf, encoding='utf-8'))
    def segment_de(ts):
        t = sec(ts)
        c = [s for s in segs if sec(s['debut']) <= t <= sec(s['fin'])]
        return c[0]['id'] if c else None
    bilan = collections.Counter(); par_bloc = {}
    for B in BLOCS:
        pts = json.load(open(os.path.join(dd, f'points_{B}_v1.json'), encoding='utf-8'))
        dossier = open(os.path.join(dd, f'dossier_{B}_v1.md'), encoding='utf-8').read()
        textes_fil = {}
        for m in re.finditer(r'^### Fil (\d+) \((\w+)\)[^\n]*\n(.*?)(?=^### |^## )', dossier, re.S | re.M):
            textes_fil[m.group(1)] = m.group(3)
        P = []; n = 0
        def ajouter(srcs, regle, point, verdict, raison, demande):
            nonlocal n; n += 1; bilan[regle] += 1
            P.append(dict(id=f'{B}-A{n:03d}', sources=srcs, point=point, demande=demande, correctif='pré-classement déterministe (règle ' + regle + ')',
                          regle_le_point='sans_objet', nouveau_probleme='aucun', statut_rev1_vrai='sans_objet', verdict=verdict,
                          raison=raison, ops=[], question=None, regle_auto=regle))
        couv_pts = []
        for p in pts:
            i = p.get('index'); t = p['type']
            if t == 'paragraphe_revise' and i is not None and i <= couv:
                couv_pts.append(p['id']); continue
            if t == 'paragraphe_revise' and toc_deb is not None and toc_fin is not None and toc_deb < i < toc_fin:
                ajouter([p['id']], 'AUTO-TDM', f'Ligne de table des matières ¶{i} révisée ({", ".join(p.get("auteurs", []))}).', 'SANS_OBJET',
                        'Table des matières = champ régénéré dans Word (F9) ; ses lignes ne s’éditent pas.', 'Aucune édition directe de la table des matières.')
                continue
            if t == 'paragraphe_revise' and p.get('auteurs') == ['Author'] and not p.get('commentaires'):
                ajouter([p['id']], 'AUTO-AUTEUR', f'¶{i} : révision de l’auteur (auteur) seule.', 'CONFORME',
                        'Révision de l’auteur : elle fait autorité (brief §3).', 'Garder la révision de l’auteur.')
                continue
            if t == 'fil_auteur':
                txt = textes_fil.get(p['fil'], '')
                if 'CC-rev1' not in txt and not p.get('reponse_rev1'):
                    ajouter([p['id']], 'AUTO-NOTE-AUTEUR', f'Fil {p["fil"]} de l’auteur, sans réponse de rev1.', 'SANS_OBJET',
                            'Note de l’auteur sans réponse de la passe précédente : laissée à l’auteur (brief §3).', 'Aucune.')
                    continue
            if t == 'repere_transcript':
                txt = textes_fil.get(p['fil'], '')
                m = re.search(r'transcript (\d\d:\d\d:\d\d)', txt)
                sg = segment_de(m.group(1)) if m else None
                if sg and any(q['id'] == f'{B}-{sg}' for q in pts):
                    ajouter([p['id']], 'AUTO-REPERE', f'Repère du fil {p["fil"]} ({m.group(1)}), dans le segment {sg}.', 'SANS_OBJET',
                            f'Repère de transcript : doublon du segment {sg} du même bloc, évalué avec lui (source : verbatim).', f'Voir {B}-{sg}.')
                    continue
            if t == 'signalement_rev1':
                txt = textes_fil.get(p['fil'], ''); v = vue.get(i, {}).get('texte', '')
                paires = re.findall(r'«\s*([^»]{1,60}?)\s*»\s*→\s*«\s*([^»]{1,60}?)\s*»', txt)
                if paires and all(x not in v and y in v for x, y in paires):
                    ajouter([p['id']], 'AUTO-PERIME', f'Signalement du fil {p["fil"]} : ' + ' ; '.join(f'« {x} » → « {y} »' for x, y in paires),
                            'SANS_OBJET', 'Signalement périmé : les formes signalées n’existent plus et les formes correctes sont présentes dans la vue rev1 du paragraphe.',
                            'Aucune.')
                    continue
        if couv_pts:
            n += 1; bilan['AUTO-COUVERTURE'] += len(couv_pts)
            P.append(dict(id=f'{B}-A{n:03d}', sources=couv_pts, point=f'Révisions sur la couverture (¶0 à {couv}) : {len(couv_pts)} paragraphes.',
                          demande='Couverture : non modifiée par Claude (règle) ; révisions des relecteurs laissées à l’auteur.',
                          correctif='pré-classement déterministe (règle AUTO-COUVERTURE)', regle_le_point='sans_objet', nouveau_probleme='aucun',
                          statut_rev1_vrai='sans_objet', verdict='DECISION_AUTEUR',
                          raison='La couverture n’est jamais modifiée par Claude ; les révisions des relecteurs y restent en suivi pour votre décision.',
                          ops=[], question='Couverture : accepter ou refuser, dans Word, les révisions des relecteurs (Statut, Objet, historique) ? ★ Les examiner avec la mise à jour de la page de garde.',
                          regle_auto='AUTO-COUVERTURE'))
        par_bloc[B] = dict(points=len(pts), auto=sum(len(x['sources']) for x in P))
        corps = f'"""Pré-classement déterministe du bloc {B} (preclasser_revision_v1) : verdicts par règles dures, sans LLM."""\nPOINTS = {json.dumps(P, ensure_ascii=False, indent=1)}\nOPS = []\nREPONSES = {{}}\n'
        corps = corps.replace(': null', ': None').replace(': true', ': True').replace(': false', ': False')
        with open(os.path.join(out, f'auto_{B}_v1.py'), 'x', encoding='utf-8') as f: f.write(corps)
    res = dict(par_regle=dict(bilan), par_bloc=par_bloc, total_points=sum(v['points'] for v in par_bloc.values()),
               total_auto=sum(v['auto'] for v in par_bloc.values()))
    res['part_automatique'] = round(res['total_auto'] / res['total_points'], 4)
    with open(os.path.join(out, 'preclassement_v1.json'), 'x', encoding='utf-8') as f: json.dump(res, f, ensure_ascii=False, indent=1)
    evenement('preclasser_revision', 1, 'preclassement', res)
    print(json.dumps(res, ensure_ascii=False))


if __name__ == '__main__':
    main()
