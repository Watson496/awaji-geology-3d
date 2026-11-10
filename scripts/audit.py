"""原凡例の保持と、未拘束領域・地表境界条件の再現を検査する。"""
import json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

def main():
    folder=ROOT/'web/data';meta=json.loads((folder/'model.json').read_text());raw={d['symbol']:d for d in json.loads((ROOT/'data/raw/seamless-legend.json').read_text())}
    units=[u for u in meta['units'] if u['kind']=='geological']
    for u in units:
        assert u['key']==u['source_symbol'];assert u['color']=='#'+raw[u['key']]['value'];assert u['name']==raw[u['key']]['title']
    domain=np.fromfile(folder/'domain.bin',np.uint8)>0;reports={}
    for name in meta['scenarios']:
        volume=np.fromfile(folder/name/'volume.bin',np.uint8);metrics=json.loads((folder/name/'metrics.json').read_text())
        assert set(np.unique(volume)).issubset({0,*[u['id'] for u in meta['units']]})
        reports[name]={'source_symbols_preserved':len(units),'unknown_fraction':float(np.mean(volume[domain]==meta['unknown_id'])),
                       'surface_boundary_agreement':metrics['surface_agreement'],'ambiguous_fraction':metrics['ambiguous_fraction'],
                       'notes':'地表は既知の境界条件。単元IDの大小は年代や層序を表さない。未拘束・競合はモデルの制約不足であり、信頼区間ではない。'}
    (folder/'quality.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2));print(json.dumps(reports,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
