"""Pure offline topic records and lookup; no UI, service or command imports."""
import json
import re
from pathlib import Path

CONTENT=Path(__file__).resolve().parent/'data'
SECTIONS=('Overview','Setup / example','Controls','Settings / defaults / storage','Lifecycle','Troubleshooting')


def load_pages(directory=CONTENT):
    pages=[]
    for path in sorted(Path(directory).glob('*.json')):
        document=json.loads(path.read_text())
        for page in document['pages']:
            if page['owner']!=document['owner'] or not all(key in page for key in ('id','app','title','revision','sections','see_also','sources')):
                raise ValueError('Invalid manual page ownership or fields')
            if not isinstance(page['id'],str) or not re.fullmatch(r'[a-z][a-z0-9.-]{0,79}',page['id']):raise ValueError('Invalid stable topic ID')
            if not isinstance(page['sections'],dict) or set(page['sections'])!=set(SECTIONS):raise ValueError('Incomplete manual sections')
            if any(not isinstance(lines,list) or not 1<=len(lines)<=16 for lines in page['sections'].values()):raise ValueError('Invalid section size')
            if any(not isinstance(line,str) or not line.isprintable() or len(line)>500 for lines in page['sections'].values() for line in lines):
                raise ValueError('Manual text must be printable and fit the existing browser bounds')
            pages.append(page)
    ids=[page['id'] for page in pages]
    if not pages or len(pages)>96 or len(ids)!=len(set(ids)):raise ValueError('Invalid manual size or duplicate topic')
    for page in pages:
        if len(page['see_also'])>9 or any(ref not in ids for ref in page['see_also']):raise ValueError('Broken manual reference')
    return tuple(pages)


def page_lines(page,by_id):
    lines=['Version: '+page['revision']+' | '+page['scope']]
    for section in SECTIONS:
        lines += [section.upper(),*page['sections'][section]]
    lines += ['SEE ALSO (press the number while reading)']
    lines += [str(i)+'. '+by_id[ref]['title']+' ['+ref+']' for i,ref in enumerate(page['see_also'],1)]
    return tuple(lines)


class ManualIndex:
    def __init__(self,pages):
        self.pages=tuple(pages);self.by_id={page['id']:page for page in pages}
        self.text={page['id']:' '.join((page['id'],page['app'],page['title'],page['owner'],*page.get('keywords',()),
            *(line for section in SECTIONS for line in page['sections'][section]))).casefold() for page in pages}

    def search(self,query):
        terms=str(query)[:256].casefold().split()
        if not terms:return ()
        return tuple(page for page in self.pages if all(term in self.text[page['id']] for term in terms))[:32]


def lookup_topic(identifier,pages=None):
    """Return an exact stable topic or None; never guess a neighboring page."""
    records=load_pages() if pages is None else pages
    return next((page for page in records if page['id']==identifier),None)
