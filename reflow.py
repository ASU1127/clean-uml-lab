"""Reflow a saved Clean UML draw.io file using its matching model.json."""
import argparse,json,sys
from pathlib import Path
HOME=Path(__file__).resolve().parent
sys.path.insert(0,str(HOME/'runtime/scripts'))
from drawio_import import import_edits
from prototype import run

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('drawio',type=Path)
    p.add_argument('--model',required=True,type=Path,help='The model.json exported beside this diagram, not an unsorted source prompt')
    p.add_argument('--page')
    p.add_argument('--allow-reconnect',action='store_true',help='Import unqualified ends dragged to existing classifier frames or text rows; kinds, markers and qualifier ownership stay fixed')
    p.add_argument('-o','--output',required=True,type=Path)
    p.add_argument('--root')
    p.add_argument('--no-qualifier-clearance',action='store_true',help='Ablate the measured qualifier-spacing fallback')
    p.add_argument('--node',default='node')
    p.add_argument('--sharp-module')
    p.add_argument('--elk-module')
    p.add_argument('--fontconfig')
    args=p.parse_args()
    try:
        if args.output.exists():raise ValueError('Output directory already exists; choose a new directory')
        source=json.loads(args.model.read_text(encoding='utf-8-sig'))
        model,trace=import_edits(args.drawio,source,args.page,allow_reconnect=args.allow_reconnect)
        # Imports, source edits and the layout invocation are all recorded in
        # the new output. Do not overwrite the editable file or companion.
        invocation=argparse.Namespace(model=str(args.model),input_model=model,output=str(args.output),root=args.root,node=args.node,sharp_module=args.sharp_module,elk_module=args.elk_module,fontconfig=args.fontconfig,requirements=None,research_intrinsic=False,research_regions=False,no_qualifier_clearance=args.no_qualifier_clearance)
        selected_valid=run(invocation)
        trace['source_drawio']=args.drawio.name;trace['source_model']=args.model.name
        (args.output/'native-edit-import.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2),encoding='utf-8')
        return 0 if selected_valid else 2
    except (ValueError,KeyError,OSError) as error:
        print('Cannot reflow: '+str(error),file=sys.stderr)
        return 2
if __name__=='__main__':sys.exit(main())
