"""Check rejected semantic mutations and a supplied rendered/native use-case output."""
import argparse
import copy
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from usecase import validate,verify_native


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',nargs='?');p.add_argument('--native');args=p.parse_args()
    base=json.loads((Path(__file__).parent/'examples/usecase-library.json').read_text(encoding='utf-8'));validate(base)
    tests=[]
    def reject(name,change):
        bad=copy.deepcopy(base);change(bad)
        try:
            validate(bad)
        except ValueError:
            tests.append(name);return
        raise AssertionError('Accepted invalid or silently dropped fact: '+name)
    reject('unknown condition',lambda m:m['relations'][-1].update(condition='Only after request'))
    reject('missing extension point',lambda m:m['relations'][-1].update(extension_points=[]))
    reject('unknown extension location',lambda m:m['relations'][-1].update(extension_points=['Not declared']))
    reject('unknown endpoint',lambda m:m['relations'][0].update(target='missing'))
    reject('actor include',lambda m:m['relations'][0].update(kind='include'))
    reject('same-subject use-case association',lambda m:m['relations'][0].update(source='borrow',target='renew'))
    reject('duplicate node',lambda m:m['use_cases'][0].update(id='reader'))
    reject('include cycle',lambda m:m['relations'].extend([{'id':'cycle1','kind':'include','source':'search','target':'borrow'},{'id':'cycle2','kind':'include','source':'borrow','target':'search'}]))
    reject('generalization cycle',lambda m:m['relations'].extend([{'id':'cycle1','kind':'generalization','source':'reader','target':'staff'},{'id':'cycle2','kind':'generalization','source':'staff','target':'reader'}]))
    result={'rejected_semantic_mutations':tests}
    if args.output:
        folder=Path(args.output);model=json.loads((folder/'model.json').read_text(encoding='utf-8'));validate(model)
        native=Path(args.native) if args.native else folder/'diagram.drawio';result['native']=verify_native(native,model)
        root=ET.parse(folder/'diagram.svg').getroot();nodes={g.get('data-node'):g for g in root.iter() if g.get('data-node')}
        assert set(nodes)=={n['id'] for key in ('actors','use_cases') for n in model[key]},'Rendered node identities differ'
        paths={g.get('data-relation'):g for g in root.iter() if g.get('data-relation')}
        assert set(paths)=={r['id'] for r in model['relations']},'Rendered relation identities differ'
        for r in model['relations']:
            points=[tuple(map(float,p.split(','))) for p in paths[r['id']].get('points').split()]
            assert len(points)>=2 and all(math.isfinite(x) for point in points for x in point),'Degenerate rendered connector'
            assert sum(math.dist(a,b) for a,b in zip(points,points[1:]))>1,'Collapsed rendered connector'
        result['rendered_identities_and_nondegenerate_paths']='passed'
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
