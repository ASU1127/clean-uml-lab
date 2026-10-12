"""Reproduce the fixed role/column factorial; optionally render local PlantUML controls."""
import argparse
import hashlib
import html
import json
import subprocess
import sys
from pathlib import Path

CORE=Path(__file__).resolve().parent.parent
DATA=CORE/'benchmarks/usecase_cases'


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def plantuml(model,hints=False):
    quote=lambda s:'"'+s.replace('\\','\\\\').replace('"','\\"').replace('\n','\\n')+'"'
    lines=['@startuml','left to right direction','skinparam shadowing false','skinparam backgroundColor white',
           'skinparam defaultFontName Arial','skinparam defaultFontSize 16','skinparam monochrome true']
    ids={n['id']:'a_'+n['id'] for n in model['actors']}|{n['id']:'u_'+n['id'] for n in model['use_cases']}
    actors={n['id']:n for n in model['actors']}
    for n in model['actors']:
        if hints and n.get('kind')=='external':
            lines.append('rectangle '+quote('«actor»\n'+n['name'])+' as '+ids[n['id']])
        else:
            lines.append('actor '+quote(n['name'])+' as '+ids[n['id']])
    lines.append('rectangle '+quote(model['name'])+' {')
    for n in model['use_cases']:
        text=n['name']+('\n--\nextension points\n'+'\n'.join(n['extension_points']) if n.get('extension_points') else '')
        lines.append('usecase '+quote(text)+' as '+ids[n['id']])
    lines.append('}')
    for r in model['relations']:
        op={'association':'--','include':'..>','extend':'..>','generalization':'--|>'}[r['kind']]
        if hints and r['kind']=='association':
            if r['source'] in actors:
                actor=actors[r['source']];which=actor.get('side','right' if actor.get('kind')=='external' else 'left')
                # PlantUML rotates these hints with left-to-right rank direction.
                op='-down-' if which=='left' else '-up-'
            else:
                actor=actors[r['target']];which=actor.get('side','right' if actor.get('kind')=='external' else 'left')
                op='-up-' if which=='left' else '-down-'
        lines.append(ids[r['source']]+' '+op+' '+ids[r['target']]+(' : <<'+r['kind']+'>>' if r['kind'] in ('include','extend') else ''))
    return '\n'.join(lines+['@enduml',''])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('-o','--output',required=True)
    p.add_argument('--node',default='node');p.add_argument('--plantuml-jar');p.add_argument('--java',default='java')
    args=p.parse_args();out=Path(args.output).resolve()
    if out.exists():
        p.error('Output exists; use a new directory')
    out.mkdir(parents=True)
    cases=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))['cases']
    arms={'neither':['--no-role-order','--no-relation-columns'],'roles':['--no-relation-columns'],'columns':['--no-role-order'],'full':[]}
    report={'scope':'Eight fixed synthetic models; not a held-out or human-preference evaluation. Each arm has one placement and one text batch. Only full arms rasterize; arm timings are not a fair latency benchmark.',
            'algorithm_sha256':hashlib.sha256((CORE/'usecase.py').read_bytes()).hexdigest(),'cases':[],'controls':[]}
    for name in cases:
        source=DATA/(name+'.json');model=json.loads(source.read_text(encoding='utf-8'));rows=[]
        for arm,flags in arms.items():
            folder=out/name/arm
            cmd=[sys.executable,'-X','utf8',str(CORE/'usecase.py'),str(source),'-o',str(folder),'--node',args.node,*flags]
            if arm!='full':
                cmd.append('--vector-only')
            proc=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',timeout=60)
            (folder/'command.log').write_text(proc.stdout+'\n'+proc.stderr,encoding='utf-8')
            run=json.loads((folder/'run.json').read_text(encoding='utf-8'))
            rows.append({'arm':arm,'exit':proc.returncode,'facts_equal':json.loads((folder/'model.json').read_text(encoding='utf-8'))==model,'run':run})
        report['cases'].append({'case':name,'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'runs':rows})
        if args.plantuml_jar:
            for control,hints in [('plantuml',False),('plantuml-hints',True)]:
                folder=out/name/control;folder.mkdir();puml=folder/'diagram.puml';puml.write_text(plantuml(model,hints),encoding='utf-8');save(folder/'model.json',model)
                cmd=[args.java,'-jar',str(Path(args.plantuml_jar).resolve()),'-tsvg','-charset','UTF-8',str(puml)]
                proc=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',timeout=60)
                (folder/'command.log').write_text(proc.stdout+'\n'+proc.stderr,encoding='utf-8')
                report['controls'].append({'case':name,'engine':control,'exit':proc.returncode,'svg_exists':(folder/'diagram.svg').is_file(),'source_sha256':hashlib.sha256(puml.read_bytes()).hexdigest(),
                    'layout_hints':hints,'hidden_edges':0,'manual_positions':0})
        save(out/'study.json',report)
        print(json.dumps({'case':name,'crossings':{r['arm']:r['run']['geometry']['crossings'] for r in rows}}),flush=True)
    report['summary']={'arms':len(cases)*4,'all_facts_equal':all(r['facts_equal'] for c in report['cases'] for r in c['runs']),
        'full_geometry_pass':sum(c['runs'][-1]['run']['status']=='geometry_pass' for c in report['cases']),
        'layout_calls':sum(r['run']['layout_calls'] for c in report['cases'] for r in c['runs']),
        'text_batches':sum(r['run']['text_measurement_calls'] for c in report['cases'] for r in c['runs']),
        'pngs':sum(r['run']['pngs'] for c in report['cases'] for r in c['runs']),'repairs':0}
    save(out/'study.json',report)
    chunks=['<!doctype html><meta charset="utf-8"><title>Clean UML 用例图对照</title><style>body{font:16px Arial;max-width:1400px;margin:24px auto;color:#222}h2{margin-top:48px}figure{margin:16px 0;border:1px solid #ddd;padding:14px}img{max-width:100%;height:auto}summary{cursor:pointer;padding:10px}a{color:#235383}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px}</style><h1>Clean UML 用例图阶段版本</h1><p>固定模型、独立消融、完整事实。几何通过不等于人类审美认证；门诊案例仍有一处交叉。</p>']
    for c in report['cases']:
        name=c['case'];full=c['runs'][-1]['run'];model=json.loads((DATA/(name+'.json')).read_text(encoding='utf-8'))
        chunks.append('<h2>'+html.escape(model['name'])+'</h2><p>'+str(len(model['use_cases']))+' 个用例 / '+str(len(model['relations']))+' 条关系；'+str(full['geometry']['crossings'])+' 处交叉。</p><p><a href="'+name+'/full/diagram.drawio">可编辑 draw.io</a> · <a href="'+name+'/full/diagram.svg">SVG</a> · <a href="'+name+'/full/review.json">审核记录</a></p><figure><img src="'+name+'/full/diagram.svg" alt="'+html.escape(model['name'],quote=True)+'"></figure>')
        if args.plantuml_jar:
            chunks.append('<details><summary>同内容 PlantUML 对照</summary><figure><figcaption>自动布局</figcaption><img src="'+name+'/plantuml/diagram.svg"></figure><figure><figcaption>加入左右位置提示，并按外部参与者类型显示</figcaption><img src="'+name+'/plantuml-hints/diagram.svg"></figure></details>')
        chunks.append('<details><summary>独立消融</summary><table><tr><th>角色排序</th><th>关系分列</th><th>交叉</th><th>结果</th></tr>')
        for r in c['runs']:
            run=r['run'];chunks.append('<tr><td>'+str(run['role_order'])+'</td><td>'+str(run['relation_columns'])+'</td><td>'+str(run['geometry']['crossings'])+'</td><td>'+html.escape(run['status'])+'</td></tr>')
        chunks.append('</table></details>')
    (out/'gallery.html').write_text('\n'.join(chunks),encoding='utf-8')
    print(json.dumps(report['summary']))


if __name__=='__main__':
    main()
