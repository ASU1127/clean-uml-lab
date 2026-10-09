"""Check the bundled native reconnect fixture against its matching model."""
import copy
import json
import sys
from pathlib import Path

HOME=Path(__file__).resolve().parent
sys.path.insert(0,str(HOME/'runtime/scripts'))
from drawio_import import import_edits


def main():
    saved=HOME/'examples/native-reconnect.drawio'
    model=json.loads((HOME/'examples/native-reconnect.model.json').read_text(encoding='utf-8'))
    expected=copy.deepcopy(model)
    expected['relations'][0]['target']='BackupPerson'
    try:
        import_edits(saved,model)
    except ValueError as error:
        if '--allow-reconnect' not in str(error):raise
    else:raise AssertionError('Default importer must reject a changed connection')
    result,audit=import_edits(saved,model,allow_reconnect=True)
    assert result==expected,'Only the explicit target may change, including exact namespace encoding'
    assert len(audit['edits'])==1 and audit['edits'][0]['field']=='target'
    print(json.dumps(dict(strict_guard_passed=True,exact_expected_model=True,
                         qualifier_and_other_facts_preserved=True,edits=audit['edits']),ensure_ascii=False))


if __name__=='__main__':main()
