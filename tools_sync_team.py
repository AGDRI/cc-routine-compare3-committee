# -*- coding: utf-8 -*-
"""`.claude/agents/*.md` の frontmatter から state.json の team を生成する。

人格の定義が state.json と agents/ の2箇所にあると必ず乖離するため、
agents/ を唯一の正とし、state.json の team はここから機械的に作る。
表示順（＝議長が先頭）は ROSTER で固定する。
"""
import json, re, sys, collections, io, os

REPO = os.path.dirname(os.path.abspath(__file__))
ROSTER = ['watanabe', 'suda', 'yoneda', 'ashiya', 'nishimura', 'takanashi']  # team[0] が議長役
FIELDS = ['displayName', 'role', 'age', 'background', 'mbti', 'bio', 'quote', 'bias', 'falsifier']


def frontmatter(path):
    txt = io.open(path, encoding='utf-8').read()
    m = re.match(r'^---\n(.*?)\n---\n', txt, re.S)
    if not m:
        raise SystemExit('frontmatter が見つからない: ' + path)
    out = {}
    for line in m.group(1).split('\n'):
        if ':' not in line or line.startswith(' '):
            continue
        k, v = line.split(':', 1)
        out[k.strip()] = v.strip().strip('"')
    return out


def main():
    team = []
    for key in ROSTER:
        fm = frontmatter('%s/.claude/agents/%s.md' % (REPO, key))
        if fm.get('name') != key:
            raise SystemExit('name が key と一致しない: %s (%s)' % (key, fm.get('name')))
        member = collections.OrderedDict([('key', key)])
        missing = [f for f in FIELDS if f not in fm]
        if missing:
            raise SystemExit('%s.md の frontmatter に不足: %s' % (key, missing))
        for f in FIELDS:
            member['name' if f == 'displayName' else f] = int(fm[f]) if f == 'age' else fm[f]
        team.append(member)

    p = REPO + '/data/state.json'
    s = json.load(io.open(p, encoding='utf-8'), object_pairs_hook=collections.OrderedDict)
    before = json.dumps(s['team'], ensure_ascii=False, sort_keys=True)
    s['team'] = team
    after = json.dumps(team, ensure_ascii=False, sort_keys=True)
    if before == after:
        print('team は既に agents/ と一致している。変更なし。')
        return 0
    with io.open(p, 'w', encoding='utf-8') as f:
        f.write(json.dumps(s, ensure_ascii=False, indent=2))
    print('team を agents/ から再生成した（%d名）' % len(team))
    return 0


if __name__ == '__main__':
    sys.exit(main())
