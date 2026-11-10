"""Georeference a published geological section, preserving image/pick provenance.

Pixel calibration is manual against the printed A/B vertical axes and ±500 m
marks, not OCR and not inferred from the ground surface. Section-line geometry
comes from the official GSJ sec.shp. Picks are interior NGd lithology only;
ambiguous KG (granite and granodiorite) is intentionally not forced into one unit.
"""
import json,hashlib
import numpy as np
from PIL import Image
from prepare import ROOT,RAW,FWD,read_layer,fetch

def build():
    image_path=RAW/'akashi-map.jpg'
    url='https://www.gsj.jp/data/50KGM/JPG/GSJ_MAP_G050_12083_1990_200dpi.jpg'
    fetch(url,image_path)
    previous=ROOT/'data/structure/sections.json'
    if previous.exists():
        pinned=next((x for x in json.loads(previous.read_text())['sections'] if x['id']=='akashi-ab'),None)
        if pinned and pinned['source_sha256']!=hashlib.sha256(image_path.read_bytes()).hexdigest():raise ValueError('Source map changed; section calibration must be reviewed')
    line=next(sr.shape.points for sr in read_layer('akashi','sec').iterShapeRecords() if sr.record.as_dict()['DESCRIPTIO']=='A-B')
    route=np.array([FWD.transform(*p) for p in line]);lengths=np.linalg.norm(np.diff(route,axis=0),axis=1);chain=np.r_[0,np.cumsum(lengths)]
    # Full original image coordinates; 500m ticks at y=3512 and 3668.
    x0,x1,y0,y1=2341,3100,3512,3668;sea=3590
    out=ROOT/'web/data/sections';out.mkdir(parents=True,exist_ok=True)
    im=Image.open(image_path).convert('RGBA').crop((x0,y0,x1,y1));im.save(out/'akashi-ab.png')
    def position(pixel):
        x,y=pixel;distance=(x-x0)/(x1-x0)*chain[-1]
        k=min(len(lengths)-1,int(np.searchsorted(chain,distance,side='right')-1));f=(distance-chain[k])/lengths[k]
        xy=route[k]*(1-f)+route[k+1]*f;z=(sea-y)*500/78
        return [*xy,float(z)]
    interior=[(2500,3620),(2600,3610),(2800,3600),(2900,3615)]
    picks=[{'id':f'akashi-ab-ngd-{i+1}','pixel':list(p),'xyz':position(p),'source_symbol':'NGd','allowed_symbols':['K21_pim_a'],
        'sigma_m':100,'kind':'interpreted_section_lithology','correlation':'NGd = medium-grained hornblende-biotite granodiorite; correlate to seamless massive granodiorite/tonalite, not KG or a generic basement class.'} for i,p in enumerate(interior)]
    # Interpreted basal contact between the Iwaya Formation and NGd.
    # Iwaya's age assignment changed after this 1990 map; correlation records
    # the later fossil evidence instead of copying the old Miocene age.
    for i,p in enumerate([(2650,3565),(2675,3570),(2700,3568)]):
        picks.append({'id':f'akashi-ab-iwaya-base-{i+1}','pixel':list(p),'xyz':position(p),
            'source_symbol':'Iwaya/NGd basal contact','allowed_symbols':['Pg2_sbs','K21_pim_a'],
            'kind':'interpreted_section_boundary','sigma_m':100,
            'correlation':'Iwaya strata over NGd; source age revised to Eocene using calcareous nannofossils/dinoflagellates. Contact digitization is approximate.',
            'correlation_source':'https://www.jstage.jst.go.jp/article/geosoc1893/106/5/106_5_379/_article/-char/ja'})
    # Printed fault intersections, retained independently of lithology pixels.
    fault_picks=[]
    for name,pixels in [('野島断層',[(2423,3610),(2430,3630)]),('中持断層',[(2715,3590),(2720,3610)]),('楠本断層',[(2988,3600),(2980,3630)])]:
        for p in pixels:fault_picks.append({'section_id':'akashi-ab','fault_name':name,'pixel':list(p),'xyz':position(p),'sigma_m':120,'kind':'interpreted_section_fault_intersection'})
    section={'id':'akashi-ab','name':'明石（1990）A–B','source_url':url,'source_sha256':hashlib.sha256(image_path.read_bytes()).hexdigest(),
        'attribution':'水野清秀・服部仁・寒川旭・高橋浩（1990）明石地域の地質、5万分の1地質図幅 明石、地質調査所',
        'route_xy':route.tolist(),'image':'sections/akashi-ab.png','image_range_m':[0,float(chain[-1]),-500,500],
        'calibration':{'original_image_pixels':list(Image.open(image_path).size),'crop_pixels':[x0,y0,x1,y1],'sea_level_y':sea,'pixels_per_500m':78,'horizontal':'GSJ sec.shp A-B arc length between printed axes',
        'horizontal_sigma_m':100,'vertical_sigma_m':50,'note':'Manual calibration and interpreted geological section, not a borehole observation. Base of colored drawing is the illustration extent, not a geological basal contact.'},
        'picks':picks,'fault_picks':fault_picks,'used_for_model':True}
    # Register the other five printed sections, preserving their own routes.
    # Pixel axes read on the original GSJ map images, checked against Navi views.
    configs=[
      ('akashi','C-D-E','akashi-cde',(3482,4766,3590),[(3700,3610),(3900,3615),(4100,3600)],'NGd','K21_pim_a'),
      ('akashi','F-G','akashi-fg',(2489,4619,3955),[(2900,3980),(3100,3980),(3500,3980),(3800,3990),(4100,3990)],'NGd','K21_pim_a'),
      ('sumoto','A-B','sumoto-ab',(2096,3121,3573),[],None,None),
      ('sumoto','C-D-E','sumoto-cde',(2183,4901,3955),[(4380,3990),(4560,3990)],'SGd','K21_pim_a'),
      ('sumoto','F-G-H','sumoto-fgh',(3434,5007,3573),[(3650,3620),(4100,3620),(4800,3620)],'SGd','K21_pim_a'),
    ]
    builtins=[section]
    for sheet,line_name,key,(left,right,sea_y),pixels,source_symbol,symbol in configs:
        source_image=RAW/f'{sheet}-map.jpg';original=Image.open(source_image)
        vertices=next(r.shape.points for r in read_layer(sheet,'sec').iterShapeRecords() if r.record.as_dict()['DESCRIPTIO']==line_name)
        xy=np.array([FWD.transform(*v) for v in vertices]);length=np.linalg.norm(np.diff(xy,axis=0),axis=1);chainage=np.r_[0,np.cumsum(length)]
        crop=[left,sea_y-78,right,sea_y+78];original.convert('RGBA').crop(crop).save(out/f'{key}.png')
        def point(pixel):
            distance=(pixel[0]-left)/(right-left)*chainage[-1];leg=min(len(length)-1,int(np.searchsorted(chainage,distance,side='right')-1));f=(distance-chainage[leg])/length[leg]
            return [*(xy[leg]*(1-f)+xy[leg+1]*f),float((sea_y-pixel[1])*500/78)]
        extra_picks=[{'id':f'{key}-{source_symbol}-{i}','pixel':list(pixel),'xyz':point(pixel),'source_symbol':source_symbol,'allowed_symbols':[symbol],'sigma_m':150,'kind':'interpreted_section_lithology','correlation':('NGd: 野島花崗閃緑岩' if source_symbol=='NGd' else 'SGd: 先山花崗閃緑岩')+' -> seamless massive granodiorite/tonalite; lithologic correlation hypothesis, not identical original legends.'} for i,pixel in enumerate(pixels)]
        builtins.append({'id':key,'name':('明石（1990）' if sheet=='akashi' else '洲本（1992）')+line_name.replace('-','–'),'source_url':url if sheet=='akashi' else 'https://www.gsj.jp/data/50KGM/JPG/GSJ_MAP_G050_13011_1992_200dpi.jpg','source_sha256':hashlib.sha256(source_image.read_bytes()).hexdigest(),'attribution':'地質調査所 5万分の1地質図幅 '+sheet,'route_xy':xy.tolist(),'image':f'sections/{key}.png','image_range_m':[0,float(chainage[-1]),-500,500],'calibration':{'original_image_pixels':list(original.size),'crop_pixels':crop,'sea_level_y':sea_y,'pixels_per_500m':78,'horizontal':'GSJ sec.shp route; full printed endpoint axes','horizontal_sigma_m':150,'vertical_sigma_m':50,'note':'Printed image frame is NOT proof of geological constraints throughout -500m or across the island. Lithology picks only inside colored interpreted bodies.'},'picks':extra_picks,'fault_picks':[],'used_for_model':bool(extra_picks)})
    # Actual interpreted fault curves, NOT the dashed label leader lines.
    fault_pixels={
      'akashi-ab':[('野島断層',[(2423,3610),(2430,3630)]),('中持断層',[(2715,3590),(2720,3610)]),('楠本断層',[(2988,3600),(2980,3630)])],
      'akashi-cde':[('浅野断層',[(3733,3570),(3740,3590),(3750,3635)]),('久野々断層',[(4048,3550),(4065,3590),(4088,3626)])],
      'akashi-fg':[('久野々断層',[(2800,3919),(2792,3960),(2783,3998)])],
      'sumoto-cde':[('安乎断層',[(3644,3938),(3624,3990),(3605,4036)]),('厚浜断層',[(4273,3946),(4255,4000),(4243,4037)])],
      'sumoto-fgh':[('鮎原南断層',[(4280,3560),(4260,3610),(4247,3645)]),('奥畑断層',[(4598,3538),(4578,3590),(4559,3646)])],
    }
    for sec in builtins:
        route=np.array(sec['route_xy']);lengths=np.linalg.norm(np.diff(route,axis=0),axis=1);chain=np.r_[0,np.cumsum(lengths)]
        left,_,right,_=sec['calibration']['crop_pixels'];sea_y=sec['calibration']['sea_level_y']
        def xyz(pixel):
            distance=(pixel[0]-left)/(right-left)*chain[-1];leg=min(len(lengths)-1,max(0,int(np.searchsorted(chain,distance,side='right')-1)));f=(distance-chain[leg])/lengths[leg]
            return [*(route[leg]*(1-f)+route[leg+1]*f),float((sea_y-pixel[1])*500/78)]
        sec['fault_lines']=[{'id':sec['id']+'-'+name,'fault_name':name,'sigma_m':150,'points':[{'pixel':list(pixel),'xyz':xyz(pixel)} for pixel in pixels],'kind':'interpreted_fault_curve'} for name,pixels in fault_pixels.get(sec['id'],[])]
        sec['fault_picks']=[{'section_id':sec['id'],'fault_name':line['fault_name'],**point,'sigma_m':line['sigma_m'],'kind':'interpreted_section_fault_intersection','fault_line_id':line['id']} for line in sec['fault_lines'] for point in line['points']]
    extra_path=ROOT/'data/structure/sections-extra.json'
    extras=json.loads(extra_path.read_text())['sections'] if extra_path.exists() else []
    for extra in extras:
        length=float(np.linalg.norm(np.diff(np.array(extra['route_xy']),axis=0),axis=1).sum())
        if extra['image_range_m'][0]!=0 or abs(extra['image_range_m'][1]-length)>1:raise ValueError('Additional section image must span 0 to the calibrated route length')
    target=ROOT/'data/structure/sections.json';target.write_text(json.dumps({'sections':[*builtins,*extras]},ensure_ascii=False,indent=2))
    (ROOT/'web/data/sections.json').write_text(target.read_text());print('section lithology picks',len(picks),'fault intersections',len(fault_picks))
    return section
if __name__=='__main__':build()
