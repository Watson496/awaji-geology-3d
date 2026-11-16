"""地質構造上の接続関係を、出典の凡例から分けて扱う。

順序を持つ堆積性の地質群は侵食で欠けることがあるが、断層がなく正順に傾斜する
鉛直区間内では逆転できない。同年代の原岩相には地層としての順序を与えない。
断層と交差する位置で、順序の制約を切る。
"""
import json
import numpy as np
from prepare import ROOT

PACKAGES=[
 {'id':'pre_izumi','symbols':['K12_pbd_a','K2-Pg12_mgmpe_lks','K21_pam_a','K21_pan_a','K21_pbg_a','K21_pim_a','K21_pin_a','K21_vas_ap','K22_pam_a','K22_pim_a'],'relation':'intrusive_and_metamorphic_assemblage'},
 {'id':'izumi','symbols':['K22_soc','K22_som','K22_sosma','K22_soss'],'relation':'unconformity_over_pre_izumi; same-age facies have no invented order'},
 {'id':'paleogene','symbols':['Pg2_sbs'],'relation':'erosional_cover'},
 {'id':'neogene','symbols':['N3_snc','N3_sns'],'relation':'erosional_cover; lateral facies'},
 {'id':'early_pleistocene','symbols':['Q1-21_sn'],'relation':'erosional_cover'},
 {'id':'terrace_older','symbols':['Q31_std'],'relation':'terrace_erosional_remnant'},
 {'id':'terrace_younger','symbols':['Q32-33_std'],'relation':'terrace_erosional_remnant'},
 {'id':'holocene','symbols':['H_sad'],'relation':'valley_and_coastal_infill'},
 {'id':'fill','symbols':['H2_or'],'relation':'anthropogenic_surface_cover'},
]

def topology(meta):
    lookup={u['key']:u['id'] for u in meta['units']}
    result=[]
    for p in PACKAGES:result.append({**p,'unit_ids':[lookup[k] for k in p['symbols'] if k in lookup]})
    mapping=np.full(len(meta['units'])+1,-1,np.int16)
    for i,p in enumerate(result):mapping[p['unit_ids']]=i
    return result,mapping

def ordered_packages(scores,rock,vertical_barrier,surface_package):
    """下から上への同時動的計画法を使う。根拠のない範囲は後で未拘束に割り当てる。

断層ではどちらの年代順序も接しうるため、分断された鉛直区間を独立に最適化する。
地質構造の復元やすべりのシミュレーションは行わない。
"""
    n= scores.shape[-1];nx,ny,nz=rock.shape
    cost=np.zeros((nx,ny,n),np.float32);back=np.zeros((nx,ny,nz,n),np.uint8)
    chosen=np.zeros(rock.shape,np.uint8)
    # 上から下へ、若い地質群から同年代または古い地質群の順に進める。
    # 厳密な境界ラベルは地表だけに適用し、地下の断層ブロックには適用しない。
    for z in range(nz-1,-1,-1):
        fresh=rock[:,:,z]&((~rock[:,:,z+1]) if z<nz-1 else True)
        if z<nz-1:fresh|=rock[:,:,z]&vertical_barrier[:,:,z]
        carry=np.maximum.accumulate(cost[:,:,::-1],axis=-1)[:,:,::-1]
        arg=np.empty_like(cost,dtype=np.uint8);arg[:,:,-1]=n-1
        for g in range(n-2,-1,-1):arg[:,:,g]=np.where(cost[:,:,g]>=carry[:,:,g+1],g,arg[:,:,g+1])
        back[:,:,z]=arg;cost=np.where(fresh[...,None],0,carry)+scores[:,:,z]
        # 最上部の観測は、対応する地質群を必ず選ぶ。
        top=rock[:,:,z]&((~rock[:,:,z+1]) if z<nz-1 else True)
        cost=np.where(top[...,None]&(surface_package[...,None]>=0)&(np.arange(n)!=surface_package[...,None]),-1e5,cost)
        # 独立した各区間の、最適化済みの下端状態を保存する。
        end=rock[:,:,z]&((~rock[:,:,z-1]|vertical_barrier[:,:,z-1]) if z>0 else True)
        chosen[:,:,z]=np.where(end,np.argmax(cost,axis=-1),0)
    for z in range(nz):
        if z==0:continue
        connected=rock[:,:,z]&rock[:,:,z-1]&~vertical_barrier[:,:,z-1]
        previous=chosen[:,:,z-1]
        next_state=np.take_along_axis(back[:,:,z-1],previous[...,None],axis=-1)[...,0]
        chosen[:,:,z]=np.where(connected,next_state,chosen[:,:,z])
    return chosen

def write_topology(meta):
    packages,mapping=topology(meta)
    out={'packages':packages,'assignment':'Joint ordered-package optimization on fault-bounded vertical segments, followed by native facies classification within the chosen package.',
      'relations':[{'younger':'izumi','older':'pre_izumi','type':'unconformity','source':'https://www.gsj.jp/data/bull-gsj/48-01_04.pdf'},
      {'younger':['K21_pam_a'],'older':['K21_pan_a','K21_pin_a','K21_pim_a'],'type':'intrusive_priority_in_overlap','source':'https://www.gsj.jp/data/bull-gsj/43-05_02.pdf','status':'local phase correlation generalized as a prior; does not establish every contact between source symbols'},
      {'younger':['K21_pim_a'],'older':['K21_pan_a','K21_pin_a'],'type':'intrusive_priority_in_overlap','source':'https://www.gsj.jp/data/bull-gsj/43-05_02.pdf','status':'phase II intrudes phase I; native-symbol correlation is an explicit prior'}],
      'limitations':['Normal-order sedimentary package constraint; overturned folds and repeated thrust sheets are not resolved.',
      'Faults are kinematic discontinuities in the present-day inference, not temporally ordered earthquake events.',
      'Native facies boundaries inside a package remain less constrained than the package envelope.',
      'This hybrid GemPy-prior/graph solver does not claim to use GemPy fault_relations or a complete petrological history.']}
    (ROOT/'data/structure/topology.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    (ROOT/'web/data/topology.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    return out
