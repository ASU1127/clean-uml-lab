"""Deterministic structural ordering without additional semantic relationships."""
import copy
import json
from collections import deque

def structural_order(model):
    result=copy.deepcopy(model)
    nodes={n['id']:n for n in model['nodes']}
    adjacency={n:set() for n in nodes};parents=set();children=set()
    for rel in model['relations']:
        a,b=rel['source'],rel['target']
        if a!=b:adjacency[a].add(b);adjacency[b].add(a)
        if rel['kind'] in ('generalization','realization'):
            parents.add(b);children.add(a)
    def priority(n):return (n not in parents-children,-len(adjacency[n]),n)
    remaining=set(nodes);order=[]
    while remaining:
        seed=min(remaining,key=priority);queue=deque([seed]);remaining.remove(seed)
        while queue:
            current=queue.popleft();order.append(current)
            for n in sorted(adjacency[current]&remaining,key=priority):
                remaining.remove(n);queue.append(n)
    result['nodes']=[nodes[n] for n in order]
    result['relations']=sorted(result['relations'],key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False))
    return result
