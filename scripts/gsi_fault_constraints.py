"""国土地理院の記号と2014年の解説書から、断層運動の定性的な制約を得る。

短線記号は低下側を示す。傾斜側への変換は、正断層・逆断層の区別が既知の場合に限る。
記号の位置で元の断層頂点を置き換えない。海域で短線が反対側にある断層は分けて扱う。
"""
import json,hashlib
import numpy as np
from prepare import ROOT,FWD

def build(faults):
    image=ROOT/'web/data/gsi-active-fault-map.png';metadata=json.loads((ROOT/'data/structure/gsi-active-fault-map.json').read_text());xmin,xmax,ymin,ymax=metadata['extent_xy'];w,h=2400,3200
    previous=ROOT/'data/structure/gsi-fault-kinematics.json'
    digest=hashlib.sha256(image.read_bytes()).hexdigest()
    if previous.exists() and json.loads(previous.read_text())['image_sha256']!=digest:
        raise ValueError('GSI raster changed: manual glyph readings require review before reuse')
    observations=[
     {'id':'gsi-shizuki-west-down','fault_name':'志筑断層','pixels':[[1365,1024],[1360,1024]],'sense':'reverse','sense_source':'GSI 2014 printed p11: N-S Shizuki/Senzan/Yura/Hansanji reverse-fault interpretation'},
     {'id':'gsi-senzan-east-down','fault_name':'先山断層','pixels':[[1323,1741],[1328,1741]],'sense':'reverse','sense_source':'GSI 2014 printed pp11,16: reverse fault, local trench west dip'},
     {'id':'gsi-mtl-west-south-down','fault_id':'major:081-01-02:2648','pixels':[[308,3174],[308,3177]],'sense':None},
     {'id':'gsi-mtl-west2-south-down','fault_id':'major:081-01-02:2649','pixels':[[508,3168],[508,3171]],'sense':None},
     {'id':'gsi-mtl-diagonal-se-down','fault_id':'major:081-01-02:2650','pixels':[[628,3131],[630,3134]],'sense':None},
     {'id':'gsi-mtl-east-north-down','fault_id':'major:081-01-02:2655','pixels':[[1535,2809],[1535,2805]],'sense':None},
     {'id':'gsi-mtl-east-south-down','fault_id':'major:081-01-02:2646','pixels':[[1885,2780],[1885,2784]],'sense':None},
     {'id':'gsi-mtl-splay-se-down','fault_id':'major:081-01-02:2647','pixels':[[1745,2729],[1747,2732]],'sense':None},
    ]
    for o in observations:
        points=np.array([[xmin+p[0]/(w-1)*(xmax-xmin),ymax-p[1]/(h-1)*(ymax-ymin)] for p in o['pixels']]);vector=points[1]-points[0];az=float(np.degrees(np.arctan2(vector[0],vector[1]))%360)
        o.update({'anchor_xy':points[0].tolist(),'downthrow_azimuth_deg':az,'dip_angle_deg':None,'reading':'manual reading of glyph SIDE on georeferenced official raster; not a surveyed tick endpoint','position_sigma_m':250})
        if o['sense']=='reverse':o['dip_side_azimuth_deg']=(az+180)%360
        else:o['dip_sense_alternatives']=[{'sense':'normal component','dip_side_azimuth_deg':az},{'sense':'reverse component','dip_side_azimuth_deg':(az+180)%360}]
    data={'source':'GSI urban active fault map (afm tiles), checked against supplied screenshots','image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'image_size':[w,h],'legend_url':'https://www.gsi.go.jp/common/000084060.pdf','guidebook_url':'https://www.gsi.go.jp/common/000096723.pdf','observations':observations,
      'local_numeric_observations_not_transferred_to_whole_fault':[{'fault':'先山断層','site':'洲本市安坂 trench','dip_range_deg':[10,20],'direction':'west','source_page':16,'scope':'shallow trench only; exact trench location/depth not registered, so not applied as a whole-fault 15deg plane'},{'fault':'安乎断層','site':'southern exposure','dip_deg':70,'direction':'west','source_page':17,'scope':'local exposure; source notes near-surface shallowing/gravitational spreading'},{'fault':'鳴門南断層','site':'鳴門市段関 boreholes','dip_range_deg':[65,75],'direction':'north','source_page':23,'scope':'local borehole interpretation, not every MTL strand'}]}
    for fault in faults:
        obs=[o for o in observations if o.get('fault_id')==fault['id'] or o.get('fault_name')==fault['name']]
        fault['gsi_kinematic_constraints']=obs
        if fault['layer']=='major' and fault.get('source_properties',{}).get('fault_segment_id')=='081-01-02':
            fault['structural_candidate']=True;fault['used_for_model']=True;fault['attitude_kind']='unresolved_orientation'
            fault['notes']='中央構造線の個別原トレース。地質断層線がない海域の構造候補。地域的な姿勢事前分布で推定し、同じ断層帯というだけで地下面を接続しない。'
    mtl_members=[f['id'] for f in faults if f.get('structural_candidate')]
    for fault in faults:
        if fault['id'].startswith('active:183-05:'):fault['model_aliases']=mtl_members;fault['association_note']='Reference segment selects separate MTL model strands; no deep joining or shared plane implied'
    (ROOT/'data/structure/gsi-fault-kinematics.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    return data
