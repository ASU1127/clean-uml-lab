"""Native editable mxGraph export. Use semantic routes; never run another layout."""
import xml.etree.ElementTree as ET
import math
import json
from notation import namespace,end_lines,node_title

NS='{http://www.w3.org/2000/svg}'

def export_drawio(model,scene,svg,editable_autofit=True,qualifier_anchors=True):
    doc=ET.Element('mxfile',host='Clean UML',version='1.8-preview')
    page=ET.SubElement(doc,'diagram',id='clean-uml',name='Class diagram')
    graph=ET.SubElement(page,'mxGraphModel',grid='0',page='0',math='0',shadow='0')
    cells=ET.SubElement(graph,'root')
    ET.SubElement(cells,'mxCell',id='0');ET.SubElement(cells,'mxCell',id='1',parent='0')
    source=ET.fromstring(svg)
    def vertex(cid,parent,x,y,w,h,style,value=''):
        c=ET.SubElement(cells,'mxCell',id=cid,parent=parent,vertex='1',value=value,style=style)
        ET.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),attrib={'as':'geometry'})
        return c
    def texts(group,parent,ox=0,oy=0,header_bottom=None,parent_width=None):
        created=[]
        for i,t in enumerate(group.findall(NS+'text')):
            style='text;html=0;strokeColor=none;fillColor=none;align=left;verticalAlign=top;spacing=0;fontFamily=Arial;fontSize=16;fontColor=#000000;whiteSpace=nowrap;overflow=visible;'
            italic=t.get('font-style')=='italic'
            bold=t.get('font-weight')=='bold'
            style+=f'fontStyle={int(bold)+2*int(italic)};'
            tx,ty=float(t.get('x'))-ox,float(t.get('y'))-oy-20
            width=float(t.get('textLength','100'))+4
            in_header=header_bottom is not None and ty+20<header_bottom
            if header_bottom is not None and editable_autofit:
                # A borderless native swimlane supplies a centered title that
                # grows from its left origin instead of shifting a relative
                # geometry by pixel values. It has no children to collapse.
                if in_header:
                    style=style.replace('text;','swimlane;').replace('align=left;','align=center;')
                    style+='swimlaneFillColor=none;separatorColor=none;startSize=20;horizontal=1;collapsible=0;'
                else:
                    # Match the original glyph origin while putting member
                    # geometry below its preceding compartment separator.
                    ty+=5
                    style+='spacingLeft=10;spacingRight=10;spacingTop=-5;'
                style+='autosize=1;autosizeGrid=0;movable=1;resizable=0;resizeWidth=1;resizeHeight=0;'
                tx=0;width=parent_width
            elif header_bottom is not None:
                style+='movable=0;resizable=0;resizeWidth=0;resizeHeight=0;'
            cell=vertex(f'{parent}_text_{i}',parent,tx,ty,width,20,style,t.text or '')
            created.append(cell)
            if header_bottom is not None and editable_autofit:
                cell.set('cleanUmlTextRole','header' if in_header else 'member')
                if in_header:cell.set('collapsed','1')
            elif in_header:
                geometry=cell.find('mxGeometry')
                geometry.set('relative','1');geometry.set('x','0.5');geometry.set('y','0')
                ET.SubElement(geometry,'mxPoint',x=str(tx-parent_width/2),y=str(ty),attrib={'as':'offset'})
        return created
    for n in model['nodes']:
        nid=n['id'];box=scene['nodes'][nid];cid='node_'+nid
        classifier=vertex(cid,'1',box['x'],box['y'],box['width'],box['height'],'rounded=0;html=0;fillColor=#FFFFFF;strokeColor=#000000;strokeWidth=1;container=1;collapsible=0;recursiveResize=1;')
        if 'package' in n or 'package' in model:classifier.set('cleanUmlNamespace',json.dumps(namespace(model,n),ensure_ascii=False))
        if 'visibility' in n:classifier.set('cleanUmlVisibility',n['visibility'])
        group=source.find(f'.//*[@id="{cid}"]')
        # Scale separator widths while keeping text rows at their original height.
        # Relative header anchors track the class center without scaling the font.
        lines=group.findall(NS+'line')
        header_bottom=min((float(line.get('y1'))-box['y'] for line in lines),default=box['height'])
        text_cells=texts(group,cid,box['x'],box['y'],header_bottom,box['width'])
        if editable_autofit:
            last=max((float(c.find('mxGeometry').get('y'))+float(c.find('mxGeometry').get('height')) for c in text_cells),default=0)
            padding=max(0,box['height']-last)
            classifier.set('style',classifier.get('style')+'childLayout=stackLayout;horizontalStack=0;resizeParent=1;resizeParentMax=1;resizeLast=0;allowGaps=1;stackUnitSize=0.5;groupPadding=0;marginBottom='+str(padding)+';')
            for c in text_cells:
                if c.get('value')==node_title(model,n):c.set('cleanUmlTextRole','name')
        for i,line in enumerate(lines):
            separator_style='shape=line;html=0;strokeColor=#000000;strokeWidth=1;fillColor=none;movable=0;resizable=1;resizeWidth=1;resizeHeight=0;connectable=0;'
            if editable_autofit:separator_style=separator_style.replace('movable=0;resizable=1;','movable=1;resizable=0;')
            vertex(f'{cid}_separator_{i}',cid,float(line.get('x1'))-box['x'],float(line.get('y1'))-box['y']-.5,float(line.get('x2'))-float(line.get('x1')),1,separator_style)
    for e in scene['edges']:
        i=e['index'];r=model['relations'][i];points=e['points'];kind=r['kind']
        terminals={side:'node_'+r[side] for side in ('source','target')}
        terminal_boxes={side:scene['nodes'][r[side]] for side in ('source','target')}
        for side,q in e.get('qualifiers',{}).items():
            cid=f'edge_{i}_qualifier_{side}';owner=scene['nodes'][r[side]]
            parent='node_'+r[side]
            qualifier_style='rounded=0;html=0;fillColor=#FFFFFF;strokeColor=#000000;strokeWidth=1;align=left;verticalAlign=middle;spacing=8;fontFamily=Arial;fontSize=16;fontColor=#000000;whiteSpace=nowrap;movable=0;resizable=0;'
            if qualifier_anchors:
                # Only the invisible zero-size anchor is relative. Native label
                # autosize moves the visible rectangle in *pixel* coordinates,
                # keeping its contact with any of the four classifier faces.
                parent=cid+'_anchor'
                anchor=vertex(parent,'node_'+r[side],0,0,0,0,'rounded=0;fillColor=none;strokeColor=none;container=1;connectable=0;movable=0;resizable=0;recursiveResize=0;expand=0;')
                anchor.set('cleanUmlQualifierAnchor',cid)
                ag=anchor.find('mxGeometry');ag.set('relative','1')
                if q['face'] in ('north','south'):
                    ag.set('x',str((q['x']+q['width']/2-owner['x'])/owner['width']));ag.set('y','0' if q['face']=='north' else '1')
                    offset=(-q['width']/2,-q['height'] if q['face']=='north' else 0)
                    align='center';vertical='bottom' if q['face']=='north' else 'top'
                else:
                    ag.set('x','0' if q['face']=='west' else '1');ag.set('y',str((q['y']+q['height']/2-owner['y'])/owner['height']))
                    offset=(-q['width'] if q['face']=='west' else 0,-q['height']/2)
                    align='right' if q['face']=='west' else 'left';vertical='middle'
                qualifier_style=qualifier_style.replace('align=left;verticalAlign=middle;spacing=8;',f'align={align};verticalAlign={vertical};spacing=0;spacingLeft=8;spacingRight=8;spacingTop=1;spacingBottom=1;')
                qualifier_style+='autosize=1;autosizeGrid=0;'
            cell=vertex(cid,parent,0,0,q['width'],q['height'],qualifier_style,q['name'])
            cell.set('cleanUmlAssociation',f'edge_{i}');cell.set('cleanUmlEnd',side)
            cell.set('cleanUmlClassifier','node_'+r[side])
            if qualifier_anchors:
                cell.set('cleanUmlFace',q['face'])
                geo=cell.find('mxGeometry');geo.set('x',str(offset[0]));geo.set('y',str(offset[1]))
                terminals[side]=cid;terminal_boxes[side]=q
                continue
            geo=cell.find('mxGeometry');geo.set('relative','1')
            if q['face'] in ('north','south'):
                geo.set('x',str((q['x']+q['width']/2-owner['x'])/owner['width']));geo.set('y','0' if q['face']=='north' else '1')
                offset=(-q['width']/2,-q['height'] if q['face']=='north' else 0)
            else:
                geo.set('x','0' if q['face']=='west' else '1');geo.set('y',str((q['y']+q['height']/2-owner['y'])/owner['height']))
                offset=(-q['width'] if q['face']=='west' else 0,-q['height']/2)
            ET.SubElement(geo,'mxPoint',x=str(offset[0]),y=str(offset[1]),attrib={'as':'offset'})
            terminals[side]=cid;terminal_boxes[side]=q
        style='edgeStyle=none;noEdgeStyle=1;rounded=0;html=0;strokeColor=#000000;strokeWidth=1.1;startArrow=none;endArrow=none;'
        if kind in ('generalization','realization'):style+='endArrow=block;endFill=0;endSize=12;'
        if kind=='dependency':style+='endArrow=open;endSize=10;'
        if kind in ('composition','aggregation'):style+=f'startArrow=diamondThin;startFill={int(kind=="composition")};startSize=16;'
        if kind in ('dependency','realization'):style+='dashed=1;dashPattern=6 4;'
        navigation=r.get('navigability','--')
        if navigation in ('<-','<->'):style+='startArrow=open;startSize=10;'
        if navigation in ('->','<->'):style+='endArrow=open;endSize=10;'
        for side,p,prefix in [('source',points[0],'exit'),('target',points[-1],'entry')]:
            box=terminal_boxes[side]
            style+=f'{prefix}X={(p[0]-box["x"])/box["width"]};{prefix}Y={(p[1]-box["y"])/box["height"]};{prefix}Perimeter=0;'
        loop=r['source']==r['target']
        owner=scene['nodes'][r['source']]
        c=ET.SubElement(cells,'mxCell',id=f'edge_{i}',parent='node_'+r['source'] if loop else '1',edge='1',source=terminals['source'],target=terminals['target'],style=style)
        if e.get('qualifiers'):
            c.set('cleanUmlSource','node_'+r['source']);c.set('cleanUmlTarget','node_'+r['target'])
        for side in ('source','target'):
            if side+'_ordered' in r:c.set('cleanUml'+side.title()+'Ordered',str(r[side+'_ordered']).lower())
        geometry=ET.SubElement(c,'mxGeometry',relative='1',attrib={'as':'geometry'})
        array=ET.SubElement(geometry,'Array',attrib={'as':'points'})
        for x,y in points[1:-1]:ET.SubElement(array,'mxPoint',x=str(x-owner['x'] if loop else x),y=str(y-owner['y'] if loop else y))
        group=source.find(f'.//*[@id="edge_{i}"]')
        # Each semantic label group belongs to its connector. Use relative
        # arclength plus normal distance, retaining role/multiplicity together.
        remaining=list(group.findall(NS+'text'))
        lengths=[math.dist(a,b) for a,b in zip(points,points[1:])];total=sum(lengths)
        for side in ('source','target','center'):
            expected=([r['label']] if 'label' in r else []) if side=='center' else end_lines(r,side)
            if not expected:continue
            ts=remaining[:len(expected)];remaining=remaining[len(expected):]
            if [t.text for t in ts]!=expected:raise ValueError('Unexpected semantic label order in export')
            x=min(float(t.get('x')) for t in ts);y=min(float(t.get('y'))-20 for t in ts)
            w=max(float(t.get('x'))+float(t.get('textLength'))+4 for t in ts)-x
            h=max(float(t.get('y')) for t in ts)-y;cx,cy=x+w/2,y+h/2
            candidates=[];walked=0
            for a,b,length in zip(points,points[1:],lengths):
                if length<1e-9:continue
                dx,dy=b[0]-a[0],b[1]-a[1];f=max(0,min(1,((cx-a[0])*dx+(cy-a[1])*dy)/(length*length)))
                # mxGraph rounds arc distance and selects the next segment at
                # a waypoint. Keep the anchor inside this segment so its normal
                # remains the one used below (notably on short self-loop legs).
                if length>2:f=min(f,1-1.01/length)
                px,py=a[0]+f*dx,a[1]+f*dy
                candidates.append((math.hypot(cx-px,cy-py),walked+f*length,(cx-px)*dy/length-(cy-py)*dx/length,px,py,dy/length,-dx/length))
                walked+=length
            _,arc,normal,px,py,nx,ny=min(candidates)
            if side in ('source','target'):
                # Role/multiplicity belong to a terminal, not a fraction of the
                # changing route. Keep their offset relative to that terminal.
                px,py=points[0 if side=='source' else -1]
                arc=0 if side=='source' else total
                normal=0
            cid=f'edge_{i}_label_{side}'
            cell=vertex(cid,f'edge_{i}',2*arc/total-1,normal,w,h,'group;fillColor=none;strokeColor=none;connectable=0;resizable=0;rotatable=0;')
            geo=cell.find('mxGeometry');geo.set('relative','1')
            ET.SubElement(geo,'mxPoint',x=str(x-px-nx*normal),y=str(y-py-ny*normal),attrib={'as':'offset'})
            label_group=ET.Element('g')
            for t in ts:label_group.append(t)
            texts(label_group,cid,x,y)
        if remaining:raise ValueError('Unaccounted edge label text')
    return ET.tostring(doc,encoding='utf-8',xml_declaration=True)
