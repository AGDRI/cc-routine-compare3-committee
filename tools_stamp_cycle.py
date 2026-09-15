# -*- coding: utf-8 -*-
"""cycle-N.json に git のコミット時刻(committedAt)を注入した同期用コピーを作る。
生成元は変更しない（リポジトリの正はそのまま）。出力先を返す。"""
import json, io, subprocess, sys, os
REPO=os.path.dirname(os.path.abspath(__file__))
def stamp(n):
    rel='data/cycles/cycle-%d.json'%n
    ts=subprocess.check_output(['git','-C',REPO,'log','-1','--format=%cI','--',rel],text=True).strip()
    d=json.load(io.open(REPO+'/'+rel,encoding='utf-8'))
    d['committedAt']=ts
    out=os.path.dirname(os.path.abspath(__file__))+'/sync-cycle-%d.json'%n
    json.dump(d,io.open(out,'w',encoding='utf-8'),ensure_ascii=False)
    return out,ts
if __name__=='__main__':
    for n in map(int,sys.argv[1:]):
        out,ts=stamp(n); print('cycle-%d committedAt=%s -> %s'%(n,ts,os.path.basename(out)))
