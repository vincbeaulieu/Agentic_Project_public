"""
OUTIL: appliquer_suivi
VERSION: 3
RESUME: Applique des opérations typées (OPS) et des réponses de fil (REPONSES) à un docx, en suivi des modifications sous un auteur donné, sans jamais modifier l'intérieur des révisions des autres auteurs ; texte de travail = vue « tout accepté » ; échec explicite « ÉCHEC <id> » (code 2).
USAGE: python3 appliquer_suivi_v3.py <mod1,mod2,…> <entree.docx> <sortie.docx> <journal.json> [--auteur "Reevaluation - Claude"] [--initiales RC]
ENTREES: modules Python exposant OPS (et facultativement POINTS, REPONSES) ; types : remplacer (cible, couples), inserer_apres / inserer_avant (ref, texte, modele, cle), supprimer_par (cible), supprimer_ligne (cible), inserer_ligne (apres, textes, cle)
SORTIES: docx en suivi ; journal technique JSON (avant / après par opération, réponses)
CATEGORIE: docx
BANC: tests/test_appliquer_suivi_v3.py
REMPLACE: appliquer_suivi_v2 (reposait sur moteur_revision_multi_v1, qui exige word/comments.xml : un document sans aucun commentaire, comme la v6.0.12-rev1 du rapport, faisait échouer l'application le 18 oct. 2026 ; repose désormais sur moteur_revision_multi_v5, version courante, qui crée les parties de commentaires au besoin) ; v2 : appliquer_suivi_v1 (sans argument suffisant, l'outil affiche la ligne USAGE de son en-tête et sort avec le code 2, au lieu d'une trace ValueError de code 1) ; v1 : 11_reevaluation/90_scripts/appliquer_reeval_v1.py (auteur paramétrable, moteur consolidé moteur_revision_multi_v1)
"""
import sys, os, json, html, importlib, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from moteur_revision_multi_v5 import DocR, q, W14, ln

NORM = {0xa0: 32, 0x202f: 32, 0x2019: 39, 0x2009: 32}
def norm(s): return s.translate(NORM)

def remplacer_tolerant(cur, a, b):
    nc, na = norm(cur), norm(a)
    i = nc.find(na)
    if i < 0: raise ValueError('introuvable : %r' % a[:100])
    if nc.find(na, i + 1) >= 0: raise ValueError('ambigu : %r' % a[:100])
    return cur[:i] + b + cur[i + len(a):]


class DocA(DocR):
    def repondre(self, cid, texte):
        root = self.root_of(cid)
        if root != cid: raise ValueError(f'{cid} n\'est pas un commentaire racine (racine : {root})')
        nid = self.next_cid; self.next_cid += 1
        pid = self.newhex(self.used_para)
        t = html.escape(texte, quote=False)
        body = (f'<w:p w14:paraId="{pid}" w14:textId="77777777"><w:pPr><w:pStyle w:val="CommentText"/></w:pPr>'
                f'<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:annotationRef/></w:r>'
                f'<w:r><w:t xml:space="preserve">{t}</w:t></w:r></w:p>')
        self.new_c.append(f'<w:comment w:id="{nid}" w:author="{self.author}" w:date="{self.now}" w:initials="{self.init}">{body}</w:comment>')
        self.new_ex.append(f'<w15:commentEx w15:paraId="{pid}" w15:paraIdParent="{self.last_para[root]}" w15:done="0"/>')
        d = self.newhex(self.used_dur)
        self.new_ids.append(f'<w16cid:commentId w16cid:paraId="{pid}" w16cid:durableId="{d}"/>')
        self.new_cx.append(f'<w16cex:commentExtensible w16cex:durableId="{d}" w16cex:dateUtc="{self.now}"/>')
        st, en, rf = self._marker('commentRangeStart', root), self._marker('commentRangeEnd', root), self._marker('commentReference', root)
        if st is not None and en is not None:
            st.addnext(self.mk('commentRangeStart', id=str(nid))); en.addprevious(self.mk('commentRangeEnd', id=str(nid)))
        rf.getparent().addnext(self._refrun(nid))
        return nid


def charger(mods):
    POINTS, OPS, REP = [], [], {}
    for m in mods.split(','):
        mod = importlib.import_module(m)
        POINTS += list(getattr(mod, 'POINTS', [])); OPS += list(mod.OPS); REP.update(getattr(mod, 'REPONSES', {}))
    return POINTS, OPS, REP


def main():
    if len(sys.argv) < 5: print('USAGE: ' + __doc__.split('USAGE: ')[1].split('\n')[0]); sys.exit(2)
    mods, src, out, jout = sys.argv[1:5]
    auteur = sys.argv[sys.argv.index('--auteur') + 1] if '--auteur' in sys.argv else 'Reevaluation - Claude'
    init = sys.argv[sys.argv.index('--initiales') + 1] if '--initiales' in sys.argv else 'RC'
    for f in (out, jout):
        if os.path.exists(f): raise SystemExit('existe déjà : ' + f)
    POINTS, OPS, REP = charger(mods)
    d = DocA(src, author=auteur, init=init)
    cles, journal = {}, []
    def res(c):
        if c.startswith('N:'): return cles[c[2:]]
        if c not in d.byid: raise ValueError('paraId inconnu : ' + c)
        return c
    for op in OPS:
        t = op['type']; rec = dict(id=op['id'], type=t, point=op.get('point'))
        try:
            if t == 'remplacer':
                pid = res(op['cible']); avant = d.text(pid); apres = avant
                for a, b in op['couples']: apres = remplacer_tolerant(apres, a, b)
                n = d.appliquer_texte(pid, apres)
                rec.update(paraId=pid, avant=avant, apres=apres, n_segments=n)
            elif t in ('inserer_apres', 'inserer_avant'):
                ref = res(op['ref']); mod = res(op.get('modele', op['ref']))
                f = d.insert_after if t == 'inserer_apres' else d.insert_before
                npid = f(ref, op['texte'], mod, res(op['rpr']) if op.get('rpr') else None)
                if op.get('cle'): cles[op['cle']] = npid
                rec.update(paraId=npid, ref=ref, texte=op['texte'])
            elif t == 'supprimer_par':
                pid = res(op['cible']); avant = d.text(pid)
                rec.update(paraId=pid, avant=avant, resultat=d.delete_paragraph(pid))
            elif t == 'supprimer_ligne':
                pid = res(op['cible']); rec.update(paraId=pid, textes=d.supprimer_ligne_multi(pid))
            elif t == 'inserer_ligne':
                tr = d.tr_of(res(op['apres'])); pids = d.inserer_ligne_apres(tr, op['textes'])
                if op.get('cle'): cles[op['cle']] = pids[0]
                rec.update(paraIds=pids, textes=op['textes'])
            else:
                raise ValueError('type inconnu : ' + t)
        except Exception as e:
            print(f'ÉCHEC {op["id"]} : {e}'); traceback.print_exc(limit=2); sys.exit(2)
        journal.append(rec)
    reps = []
    for cid, texte in REP.items():
        try:
            nid = d.repondre(str(cid), texte); reps.append(dict(fil=str(cid), id=nid, texte=texte))
        except Exception as e:
            print(f'ÉCHEC réponse {cid} : {e}'); sys.exit(2)
    d.save(out)
    json.dump(dict(source=src, modules=mods, auteur=d.author, date=d.now, operations=journal, reponses=reps,
                   cles=cles, n_points=len(POINTS)), open(jout, 'x', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{len(journal)} opérations, {len(reps)} réponses -> {out}')


if __name__ == '__main__':
    main()
