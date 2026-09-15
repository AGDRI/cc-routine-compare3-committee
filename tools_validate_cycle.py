# -*- coding: utf-8 -*-
"""cycle-N.json の機械検査。ルーティンは commit 前に、同期ループは pull 後に走らせる。

  python3 tools_validate_cycle.py N            # 検査して結果を表示
  python3 tools_validate_cycle.py N --json     # 機械可読で出力

終了コード: 0=すべてPASS、1=WARNあり、2=FAILあり。
FAIL は保存してはいけない形式違反、WARN は人が判断すべき兆候。
根拠となるルール番号を各行に付ける（data/rules.md 参照）。
"""
import json, io, os, re, sys, math

REPO = os.path.dirname(os.path.abspath(__file__))
Y2026, Y2027 = 0.296, 1.295          # R13: 基準日 2026-09-14 からの年数
ACTIVE = ['nittobo', 'pillar', 'mec']
CURRENT_WORDS = ['現在', '現値', '時点', '本日', '前日比']   # R29
YEN = re.compile(r'(\d{1,3}(?:,\d{3})+|\d{4,6})\s*円')


def load(p):
    return json.load(io.open(os.path.join(REPO, p), encoding='utf-8'))


def near(a, b, tol=1.0):
    return a is not None and b is not None and abs(a - b) <= tol


def main(n, as_json=False):
    out = []                                            # (level, rule, msg)
    def add(level, rule, msg): out.append((level, rule, msg))

    d = load('data/cycles/cycle-%d.json' % n)
    s = load('data/state.json')
    team = [m['key'] for m in s['team']]
    pf = s.get('priceFeed', {}).get('prices', {})
    feed = load('data/feed/latest.json') if os.path.exists(os.path.join(REPO, 'data/feed/latest.json')) else {}
    locked = feed.get('lockedFacts', {})
    prev = None
    if os.path.exists(os.path.join(REPO, 'data/cycles/cycle-%d.json' % (n - 1))):
        prev = load('data/cycles/cycle-%d.json' % (n - 1)).get('conclusion', {})

    rounds = d.get('rounds', [])
    c = d.get('conclusion', {})
    stmts = [x for r in rounds for x in r.get('statements', [])]

    # ---- 不変条件 / R6 / R7 / R21 ----
    if not rounds:
        add('FAIL', '形式', 'rounds が空')
    last_opener = None
    sizes = []
    any_double = False
    spoke_ever = {x.get('speaker') for x in stmts}
    absent_all = sorted(set(team) - spoke_ever)
    if absent_all:
        add('WARN', '名簿', '全ラウンド不在の委員 %s（当時の名簿にいなかった可能性。名簿変更直後のサイクルなら正常）' % ','.join(absent_all))
    team_then = [k for k in team if k not in absent_all]
    for r in rounds:
        sp = [x.get('speaker') for x in r.get('statements', [])]
        mem = [k for k in sp if k != 'guest']
        if not isinstance(r.get('statements'), list):
            add('FAIL', 'R6', 'R%s: statements が配列ではない' % r.get('round'))
            continue
        missing = sorted(set(team_then) - set(mem))
        if missing:
            add('FAIL', '不変条件', 'R%s: 発言していない委員 %s' % (r.get('round'), ','.join(missing)))
        if sp and sp[0] == last_opener:
            add('FAIL', 'R6', 'R%s: 口火が前ラウンドと同じ (%s)' % (r.get('round'), sp[0]))
        last_opener = sp[0] if sp else None
        if any(mem.count(k) > 1 for k in set(mem)):
            any_double = True
        sizes.append(len(sp))
        # ゲストの直後に委員の反応があるか (R6)
        for i, x in enumerate(r.get('statements', [])):
            if x.get('speaker') == 'guest' and i == len(r['statements']) - 1:
                add('WARN', 'R6', 'R%s: ゲストがラウンド末尾で、直後の委員の反応がない' % r.get('round'))
    if rounds and not any_double:
        add('WARN', 'R7/R21', '二度発言するラウンドが1つもない（誰も反論されなかった＝予定調和の兆候）')
    if len(sizes) >= 3 and len(set(sizes)) == 1:
        add('WARN', 'R21', 'ラウンドの発言数が全て同じ (%d) — 機械的に埋めている疑い' % sizes[0])

    # ---- R14 (agentMode) ----
    if d.get('agentMode'):
        n_src = sum(1 for x in stmts if x.get('sources'))
        n_nf = sum(1 for x in stmts if x.get('newFinding'))
        if n_src < len(stmts) * 0.8:
            add('WARN', 'R14', 'sources 付きの発言が %d/%d' % (n_src, len(stmts)))
        if n_nf == 0 and '維持' not in c.get('verdict', ''):
            add('WARN', 'R14', '全員の newFinding が null なのに verdict が「前回維持」と言っていない')

    # ---- R24 字数 ----
    sl = c.get('stanceLabel', '')
    if len(sl) > 15:
        add('FAIL', 'R24', 'stanceLabel が %d字（上限15）: %s' % (len(sl), sl[:30]))
    for i, w in enumerate(c.get('nextWatch', [])):
        if len(w) > 20:
            add('FAIL', 'R24', 'nextWatch[%d] が %d字（上限20）' % (i, len(w)))
    for r in rounds:
        for w in r.get('watchItems', []):
            if len(w) > 20:
                add('WARN', 'R24', 'R%s watchItems が %d字（上限20）' % (r.get('round'), len(w)))

    # ---- R10 baseline / incr2027 ----
    bl = c.get('baseline', {})
    for k in ACTIVE:
        v = bl.get(k)
        if not isinstance(v, dict) or v.get('price') is None:
            add('FAIL', 'R10', 'baseline.%s がない' % k)
        elif pf.get(k) and abs(v['price'] - pf[k]) / pf[k] > 0.03 and not bl.get('note'):
            add('WARN', 'R10/R11', 'baseline.%s=%s が priceFeed=%s と3%%超ずれているのに note に理由がない' % (k, v['price'], pf[k]))
    if not c.get('rankingBasis'):
        add('FAIL', 'R10', 'rankingBasis がない')

    # ---- R8 / R13 ranking ----
    rk = c.get('ranking', [])
    keys = [r.get('key') for r in rk]
    if sorted(keys) != sorted(ACTIVE):
        add('FAIL', 'R8', 'ranking の銘柄が %s（期待 %s）' % (keys, ACTIVE))
    prev_rank = {r['key']: r for r in (prev or {}).get('ranking', [])}
    for r in rk:
        k = r.get('key'); h6 = r.get('h2026', {}); h7 = r.get('h2027', {})
        for h, lab in ((h6, 'h2026'), (h7, 'h2027')):
            if not (h.get('bull', -999) > h.get('base', -999) > h.get('bear', -999)):
                add('FAIL', 'R8', '%s.%s が bull>base>bear になっていない' % (k, lab))
        if h6.get('base') is not None and h7.get('base') is not None:
            inc = ((1 + h7['base'] / 100) / (1 + h6['base'] / 100) - 1) * 100
            if not near(r.get('incr2027'), inc):
                add('FAIL', 'R10', '%s.incr2027=%s（計算値 %.1f）' % (k, r.get('incr2027'), inc))
            A = r.get('annualized') or {}
            a6 = ((1 + h6['base'] / 100) ** (1 / Y2026) - 1) * 100
            a7 = ((1 + h7['base'] / 100) ** (1 / Y2027) - 1) * 100
            if not near(A.get('h2026'), a6) or not near(A.get('h2027'), a7):
                add('FAIL', 'R13', '%s.annualized=%s（計算値 %.1f/%.1f）' % (k, A, a6, a7))
            G = r.get('gainPain') or {}
            for h, lab in ((h6, 'h2026'), (h7, 'h2027')):
                if h.get('bear'):
                    g = h['base'] / abs(h['bear'])
                    if not near(G.get(lab), g, 0.05):
                        add('FAIL', 'R13', '%s.gainPain.%s=%s（計算値 %.2f）' % (k, lab, G.get(lab), g))
        for f in ('rank2026', 'rank2027', 'rankEff2026', 'rankEff2027'):
            if r.get(f) is None:
                add('FAIL', 'R10/R13', '%s.%s がない' % (k, f))
        # R20: 30%以上の切り下げに根拠があるか
        pb = (prev_rank.get(k) or {}).get('h2027', {}).get('base')
        nb = h7.get('base')
        if pb is not None and nb is not None and pb > 0 and (pb - nb) / pb >= 0.30:
            rat = (r.get('rationale') or '') + (c.get('rankingBasis') or '')
            if not any(w in rat for w in ('ガイダンス', '通期', '計画')) or not any(w in rat for w in ('高値', '12,080', '12080')):
                add('WARN', 'R20', '%s: h2027 base を %s→%s に切り下げたが、rationale にガイダンス整合と直近高値整合の両方が見当たらない' % (k, pb, nb))
    if not c.get('opportunityCost'):
        add('FAIL', 'R13', 'opportunityCost がない')

    # ---- R25 memberPositions ----
    mp = c.get('memberPositions')
    if mp is None:
        add('FAIL', 'R25', 'memberPositions がない')
    else:
        got = {x.get('key') for x in mp}
        miss = sorted(set(team_then) - got)
        if miss:
            add('FAIL', 'R25', 'memberPositions に %s がない' % ','.join(miss))
        rejected = [x for x in mp if x.get('adopted') is False]
        if not rejected:
            add('WARN', 'R25', '全員 adopted:true — 食い違いを隠している疑い')
        for x in rejected:
            if not x.get('overrideReason'):
                add('FAIL', 'R25', '%s は adopted:false なのに overrideReason がない' % x.get('key'))

    # ---- R23 doNotUse / R29 株価の機械検査 ----
    dnu = []
    for k in ACTIVE:
        for item in (locked.get(k) or {}).get('doNotUse', []):
            item = re.split(r'[—―…]| - ', item)[0]        # 「— 理由」より前の禁止値部分だけを対象にする
            for tok in re.findall(r'\d[\d,\.]*(?:%|円|億円|億)', item) + re.findall(r'\d{1,3}(?:,\d{3})+', item):
                if re.fullmatch(r'20[2-3]\d', tok):
                    continue                              # 年号は対象外
                if len(tok) >= 4 and (k, tok) not in dnu:
                    dnu.append((k, tok))
    dnu.sort(key=lambda kt: -len(kt[1]))
    for r in rounds:
        for x in r.get('statements', []):
            t = x.get('text', '') or ''
            hit_pos = set()
            for k, tok in dnu:
                for m in re.finditer(re.escape(tok), t):
                    if any(abs(m.start() - q) <= 2 for q in hit_pos):
                        break
                    hit_pos.add(m.start())
                    ctx = t[max(0, m.start() - 40):m.end() + 40]
                    if any(w in ctx for w in ('誤り', '訂正', '古い', '誤って', '時点', '当時', 'だった', '終値', '使わない', 'ではない', '前期', '分割前')):
                        continue                          # 訂正文脈・日付付き過去値は可
                    add('WARN', 'R23', 'R%s %s: doNotUse「%s」が現在の事実として使われている可能性: …%s…' % (r.get('round'), x.get('speaker'), tok, ctx.replace('\n', ' ')))
                    break
            for m in YEN.finditer(t):
                v = int(m.group(1).replace(',', ''))
                ctx = t[max(0, m.start() - 30):m.end() + 30]
                if not any(w in ctx for w in CURRENT_WORDS):
                    continue
                if any(w in ctx for w in ('目標', '平均', 'コンセンサス', '理論', '分割前', '換算', '高値', '安値', '終値だ', 'の終値')):
                    continue                              # 目標株価や過去値の説明は現在値の提示ではない
                # どの銘柄かは値の近さで推定（priceFeed の ±25% に入るもの）
                for k, p in pf.items():
                    if p and 0.75 * p <= v <= 1.25 * p and abs(v - p) / p > 0.03:
                        add('WARN', 'R29', 'R%s %s: 「%s円」を現在値として提示（priceFeed.%s=%s と %.1f%% 乖離）' % (r.get('round'), x.get('speaker'), m.group(1), k, p, abs(v - p) / p * 100))
                        break

    # ---- 出力 ----
    worst = 0
    for level, rule, msg in out:
        worst = max(worst, {'WARN': 1, 'FAIL': 2}[level])
    if as_json:
        print(json.dumps({'cycle': n, 'result': ['PASS', 'WARN', 'FAIL'][worst],
                          'items': [{'level': l, 'rule': r, 'msg': m} for l, r, m in out]}, ensure_ascii=False, indent=1))
    else:
        print('cycle-%d: %s  (発言 %d / ラウンド %s / stance %s / 27年末base %s)' % (
            n, ['PASS', 'WARN', 'FAIL'][worst], len(stmts), sizes, c.get('stance'), c.get('outlook', {}).get('base', {}).get('price')))
        for level, rule, msg in out:
            print('  [%s] %-8s %s' % (level, rule, msg))
        if not out:
            print('  すべての検査を通過')
    return worst


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    sys.exit(main(int(args[0]), '--json' in sys.argv))
