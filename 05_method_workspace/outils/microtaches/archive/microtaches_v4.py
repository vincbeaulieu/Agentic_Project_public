"""
OUTIL: microtaches
VERSION: 4
RESUME: Découpe déterministe d'une réévaluation de révision en micro-tâches pour modèles locaux (LM Studio) et banc de ces modèles : MT-PRESENCE (une phrase supprimée par la révision est-elle reprise ailleurs ? candidats trouvés par recouvrement de mots, phrase et paragraphe), MT-DEMANDE (type de la demande d'un fil ou d'un segment du transcript) ; échantillon de référence stable (tri par empreinte) ; lot JavaScript à lancer dans l'onglet LM Studio (asynchrone, résultats dans window.__R) ; évaluation des sorties (validité, exactitude, F1 macro, latence, tokens) contre les références. Textes anonymisés (rôles).
USAGE: python3 microtaches_v4.py generer <docx> <dossiers_agents> <sortie_dossier> [--seuil-unique 0.5]
       python3 microtaches_v4.py echantillon <microtaches.jsonl> <n_par_type> <sortie_dossier>
       python3 microtaches_v4.py lot <echantillon.jsonl> <modeles,séparés,par,virgules> <sortie_dossier> [--nom pilote]
       python3 microtaches_v4.py combiner <resultats.json> <microtaches.jsonl> <sortie_dossier>
       python3 microtaches_v4.py evaluer <resultats.json> <references.json> <sortie_dossier>
ENTREES: docx révisé (suivi), points_<bloc>_v1.json et dossier_<bloc>_v2.md, regles/roles (anonymisation)
SORTIES: microtaches_vN.jsonl, echantillon_vN.jsonl, lot_<nom>_vN.js, banc_local_vN.json (versionnés, jamais écrasés) ; événement dans journal/
CATEGORIE: delegation_locale
BANC: -
REMPLACE: microtaches_v3 (+ combiner : règles déterministes qui corrigent la sortie du modèle — marqueurs de remplacement → « modifier » (leçon LC-008), références [n] ou nombres de A absents de B → « partiel » au plus ; + évaluer accepte le format compact [modèle, id, valeur, ms, tokens, passe] et mesure la constance entre passes) ; v3 remplaçait microtaches_v2 (réflexion désactivée par reasoning_effort « none » : 0 token de réflexion, ~0,4 s au lieu de ~1,9 s par appel ; données gardées dans window.__T et lanceur window.__run réutilisable sans renvoyer les données) ; v2 remplaçait microtaches_v1 (fenêtre B centrée sur la meilleure phrase, 500 car. par candidat ; demande en 5 classes alignées sur le contrôle LC-008 ; échantillon stratifié par genre)
"""
import sys, os, re, json, glob, zipfile, hashlib, collections
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import RACINE_CC, evenement, ecrire_versionne, derniere_version
import detecteurs_rapport_v2 as DR
from anonymiser_v1 import anonymiser

ROLES = json.load(open(derniere_version(os.path.join(RACINE_CC, 'regles'), 'roles', 'json'), encoding='utf-8'))['roles']
def anon(t): return anonymiser(t or '', ROLES)
def court(t, n): t = re.sub(r'\s+', ' ', t or '').strip(); return t if len(t) <= n else t[:n - 1] + '…'

VALEURS = {'MT-PRESENCE': ['oui', 'partiel', 'non'],
           'MT-DEMANDE': ['supprimer', 'modifier', 'deplacer', 'question', 'aucune']}
CONSIGNES = {
 'MT-PRESENCE': "Tu compares deux textes d'un rapport. A est une phrase supprimée ; B est un extrait du rapport révisé. "
                "Réponds seulement en JSON {\"r\":X}. X = oui si toute l'information de A se trouve dans B (les mots peuvent différer) ; "
                "partiel si une partie seulement de l'information de A est dans B ; non si l'information de A est absente de B.",
 'MT-DEMANDE': "Tu classes la demande d'un relecteur sur un rapport. Réponds seulement en JSON {\"r\":X}. X = "
               "supprimer (retirer un passage sans rien mettre à la place) ; "
               "modifier (changer, corriger, remplacer, préciser, compléter, simplifier ou reformuler : il faut écrire du texte nouveau, même court) ; "
               "deplacer (mettre le passage ailleurs dans le rapport) ; question (demande une explication sans dire quoi changer) ; "
               "aucune (approbation, ou remarque sans action demandée)."}


def generer(a):
    docx, dd, out = a[0], a[1], a[2]
    seuil = float(a[a.index('--seuil-unique') + 1]) if '--seuil-unique' in a else 0.5
    P = DR.vues(zipfile.ZipFile(docx))
    acc_phr = [(p, s) for p in P if not p['toc'] for s in DR.phrases(p['acc'])]
    index = collections.defaultdict(set)
    for k, (p, s) in enumerate(acc_phr):
        for t in set(DR.tokens(s)): index[t].add(k)
    par_tok = collections.defaultdict(set)              # couverture au niveau du paragraphe
    for p in P:
        if not p['toc']:
            for t in set(DR.tokens(p['acc'])): par_tok[t].add(p['i'])
    tous_acc = set(index); T_ = []
    for p in P:
        if p['toc'] or not p['ori'].strip(): continue
        sa = set(DR.phrases(p['acc']))
        for s in DR.phrases(p['ori']):
            if s in sa or s in p['acc']: continue
            T = set(DR.tokens(s))
            if len(T) < 4: continue
            cpt = collections.Counter(k for t in T for k in index.get(t, ()))
            best = max(cpt.values()) / len(T) if cpt else 0.0
            nombres = sorted(t for t in T if re.search(r'\d', t) and t not in tous_acc)
            if not (best < seuil or nombres): continue
            cp = collections.Counter(i for t in T for i in par_tok.get(t, ()) if i != p['i'] or True)
            bpar = max(cp.values()) / len(T) if cp else 0.0
            top = [k for k, _ in sorted(cpt.items(), key=lambda x: (-x[1], x[0]))[:2]]
            b = []
            for k in top:
                q, s2 = acc_phr[k]
                v, g, d = [s2], k - 1, k + 1          # meilleure phrase entière, puis voisines tant que <= 500 car.
                while True:
                    ajout = False
                    for j in (g, d):
                        if 0 <= j < len(acc_phr) and acc_phr[j][0] is q and len(' '.join(v)) + len(acc_phr[j][1]) < 500:
                            if j == g: v.insert(0, acc_phr[j][1]); g -= 1
                            else: v.append(acc_phr[j][1]); d += 1
                            ajout = True
                    if not ajout: break
                b.append(court(' '.join(v), 500))
            iid = 'P-' + hashlib.sha256((p['pid'] or str(p['i'])) .encode() + s.encode()).hexdigest()[:10]
            T_.append(dict(id=iid, type='MT-PRESENCE', index=p['i'], paraId=p['pid'], section=court(p['section'], 60),
                           a=anon(court(s, 400)), b=anon(' […] '.join(b)), det=dict(couv_phrase=round(best, 3), couv_par=round(bpar, 3), nombres_disparus=nombres)))
    # MT-DEMANDE : premier commentaire des fils (hors repères et réponses), résumés des segments du transcript
    for f in sorted(glob.glob(os.path.join(dd, 'dossier_B*_v2.md'))):
        B = re.search(r'dossier_(B\d+)_', f).group(1); txt = open(f, encoding='utf-8').read()
        for m in re.finditer(r'^### Fil (\d+) \((\w+)\) — ¶(\d+) (\w+)[^\n]*\n(.*?)(?=^### |^## )', txt, re.S | re.M):
            fil, typ, i, pid, corps = m.groups()
            if typ == 'repere_transcript': continue
            c = re.search(r'^- \[\d+\] \*\*([^*]+)\*\* \S+ : (.*?)(?=^- \[|\Z)', corps, re.S | re.M)
            if not c or c.group(1).startswith('CC-'): continue
            T_.append(dict(id=f'D-{B}-F{fil}', type='MT-DEMANDE', bloc=B, fil=fil, genre=typ, index=int(i), paraId=pid,
                           texte=anon(court(c.group(2), 450))))
        for m in re.finditer(r'^### (T\d+) — [^¶]*¶(\d+) (\w+)[^\n]*\n(.*?)(?=^### |^## |\Z)', txt, re.S | re.M):
            seg, i, pid, corps = m.groups()
            r = [x.strip() for x in re.findall(r'^- [^\n(]+\(résumé\) : (.*)$', corps, re.M)]
            if r: T_.append(dict(id=f'D-{B}-{seg}', type='MT-DEMANDE', bloc=B, segment=seg, index=int(i), paraId=pid,
                                 texte=anon(court(' / '.join(r), 450))))
    T_.sort(key=lambda x: (x['type'], x['index'], x['id']))
    ch, cree = ecrire_versionne(out, 'microtaches', 'jsonl', ''.join(json.dumps(x, ensure_ascii=False, sort_keys=True) + '\n' for x in T_))
    res = dict(fichier=os.path.basename(ch), cree=cree, par_type=dict(collections.Counter(x['type'] for x in T_)))
    evenement('microtaches', 4, 'generer', res); print(json.dumps(res, ensure_ascii=False))


def charger(f): return [json.loads(l) for l in open(f, encoding='utf-8') if l.strip()]


def echantillon(a):
    T, n, out = charger(a[0]), int(a[1]), a[2]; E = []
    for ty in VALEURS:                      # stratifié par genre (fil_auteur, fil_relecteur, segment) ; n par strate
        for ge in sorted({x.get('genre', 'segment' if ty == 'MT-DEMANDE' else '-') for x in T if x['type'] == ty}):
            E += sorted((x for x in T if x['type'] == ty and x.get('genre', 'segment' if ty == 'MT-DEMANDE' else '-') == ge),
                        key=lambda x: hashlib.sha256(x['id'].encode()).hexdigest())[:n]
    ch, cree = ecrire_versionne(out, 'echantillon', 'jsonl', ''.join(json.dumps(x, ensure_ascii=False, sort_keys=True) + '\n' for x in E))
    print(ch, cree)


def entree(x):
    return f"A : {x['a']}\nB : {x['b']}" if x['type'] == 'MT-PRESENCE' else f"Demande : {x['texte']}"


def lot(a):
    E, modeles, out = charger(a[0]), a[1].split(','), a[2]
    nom = a[a.index('--nom') + 1] if '--nom' in a else 'pilote'
    T = [[x['id'], 'P' if x['type'] == 'MT-PRESENCE' else 'D', entree(x)] for x in E]
    S = {'P': CONSIGNES['MT-PRESENCE'], 'D': CONSIGNES['MT-DEMANDE']}; V = {'P': VALEURS['MT-PRESENCE'], 'D': VALEURS['MT-DEMANDE']}
    js = ("(()=>{window.__T=" + json.dumps(T, ensure_ascii=False) + ";window.__S=" + json.dumps(S, ensure_ascii=False)
          + ";window.__V=" + json.dumps(V) + ";window.__run=(M,o)=>{const T=window.__T,S=window.__S,V=window.__V;o=o||{};window.__R=[];window.__F=0;(async()=>{for(let p=0;p<(o.passes||1);p++)for(const m of M){for(const [i,k,u] of T){const t0=performance.now();let c='';let n=null;"
          "try{const r=await fetch('/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:m,temperature:0,max_tokens:40,reasoning_effort:'none',"
          "messages:[{role:'system',content:S[k]},{role:'user',content:u}],response_format:{type:'json_schema',json_schema:{name:'r',strict:true,schema:{type:'object',"
          "properties:{r:{type:'string',enum:V[k]}},required:['r'],additionalProperties:false}}}})}).then(x=>x.json());c=(r.choices&&r.choices[0].message.content)||JSON.stringify(r.error||r);"
          "n=r.usage&&r.usage.completion_tokens}catch(e){c='ERR '+e}window.__R.push([m,i,String(c).slice(0,80),Math.round(performance.now()-t0),n,p])}}window.__F=1})();return 'lancé '+T.length*M.length*(o.passes||1)};return window.__run(" + json.dumps(modeles) + ")})()")
    ch, cree = ecrire_versionne(out, f'lot_{nom}', 'js', js); print(ch, cree, len(js), 'caractères')


REMPLACEMENT = re.compile(r"une phrase suffit|en une phrase|dire simplement|dire plutôt|remplacer par|à remplacer|plutôt que|au lieu de|à la place|résumer en|reformuler|→", re.I)
REF = re.compile(r'\[(\d+)\]'); NOMBRE = re.compile(r'\d+(?:[,.]\d+)?')


def regle(x, v):
    """Règles déterministes appliquées après le modèle ; renvoie (valeur, règle ou None)."""
    if x['type'] == 'MT-DEMANDE' and v in ('supprimer', 'aucune', 'question') and REMPLACEMENT.search(x['texte']):
        return 'modifier', 'R-REMPLACEMENT'
    if x['type'] == 'MT-PRESENCE' and v == 'oui':
        manque = (set(REF.findall(x['a'])) - set(REF.findall(x['b']))) | (set(NOMBRE.findall(REF.sub('', x['a']))) - set(NOMBRE.findall(x['b'])))
        if manque: return 'partiel', 'R-MANQUE'
    return v, None


def valeur(c):
    if c in sum(VALEURS.values(), []): return c
    try: return json.loads(c)['r']
    except Exception: return None


def combiner(a):
    R, X, out = json.load(open(a[0], encoding='utf-8')), {x['id']: x for x in charger(a[1])}, a[2]
    C = []
    for m, i, c, ms, n, *pa in R:
        v = valeur(c); C.append([m, i, v, ms, n] + pa)
        if i in X: C.append(['regles+' + m, i, regle(X[i], v)[0], ms, n] + pa)
    ch, cree = ecrire_versionne(out, 'resultats_combines', 'json', json.dumps(C, ensure_ascii=False))
    print(ch, cree)


def evaluer(a):
    R, ref, out = json.load(open(a[0], encoding='utf-8')), json.load(open(a[1], encoding='utf-8')), a[2]
    ref = ref.get('references', ref); typ = {i: ('MT-PRESENCE' if i.startswith('P-') else 'MT-DEMANDE') for i in ref}
    G = collections.defaultdict(list)
    passes = collections.defaultdict(dict)
    for m, i, c, ms, n, *pa in R:
        if i not in ref: continue
        v = valeur(c); p = pa[0] if pa else 0
        passes[(typ[i], m)].setdefault(i, {})[p] = v
        if p == 0: G[(typ[i], m)].append((i, v, ms, n))
    res = {}
    for (ty, m), L in sorted(G.items()):
        ok = sum(1 for i, v, _, _ in L if v == ref[i]); val = sum(1 for _, v, _, _ in L if v in VALEURS[ty])
        f1 = []
        for c in VALEURS[ty]:
            tp = sum(1 for i, v, _, _ in L if v == c and ref[i] == c); fp = sum(1 for i, v, _, _ in L if v == c and ref[i] != c)
            fn = sum(1 for i, v, _, _ in L if v != c and ref[i] == c)
            if tp + fp + fn: f1.append(2 * tp / (2 * tp + fp + fn))
        ms = sorted(x[2] for x in L)
        res[f'{ty}|{m}'] = dict(n=len(L), valides=val, exactitude=round(ok / len(L), 3), f1_macro=round(sum(f1) / len(f1), 3) if f1 else None,
                               ms_median=ms[len(ms) // 2], ms_max=ms[-1], tokens_sortie=sum(x[3] or 0 for x in L),
                               constance=round(sum(1 for d in passes[(ty, m)].values() if len(set(d.values())) == 1) / len(passes[(ty, m)]), 3),
                               passes=max(len(d) for d in passes[(ty, m)].values()),
                               erreurs=[f'{i}: {v} au lieu de {ref[i]}' for i, v, _, _ in L if v != ref[i]])
    ch, cree = ecrire_versionne(out, 'banc_local', 'json', json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True))
    evenement('microtaches', 4, 'banc_local', {k: {x: v[x] for x in ('n', 'exactitude', 'f1_macro', 'ms_median', 'constance')} for k, v in res.items()})
    for k, v in res.items(): print(k, v['n'], 'exact', v['exactitude'], 'F1', v['f1_macro'], 'ms', v['ms_median'], v['ms_max'], 'constance', v['constance'], v['passes'])
    print(ch)


if __name__ == '__main__':
    {'generer': generer, 'echantillon': echantillon, 'lot': lot, 'combiner': combiner, 'evaluer': evaluer}[sys.argv[1]](sys.argv[2:])
