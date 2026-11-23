"""Prepare portable phrase-list extracts from English Wikivoyage."""
from html.parser import HTMLParser
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import field_companion as field

LANGUAGES = ('Spanish', 'French', 'German', 'Japanese')
TERMS = 'Phrase-list text adapted under CC BY-SA 4.0 · https://creativecommons.org/licenses/by-sa/4.0/'


class PhraseList(HTMLParser):
    def __init__(self):
        super().__init__()
        self.section = 'Phrases'
        self.tag = self.term = None
        self.parts = []
        self.entries = []

    def handle_starttag(self, tag, attrs):
        if tag in ('h2', 'h3', 'h4', 'dt', 'dd'):
            self.tag, self.parts = tag, []
            if tag != 'dd':
                self.term = None
        elif tag == 'br':
            self.parts.append(' ')

    def handle_data(self, data):
        if self.tag:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if self.tag != tag:
            return
        value = ' '.join(''.join(c for c in ''.join(self.parts) if c.isprintable() or c.isspace()).split())
        if tag.startswith('h'):
            self.section = value or 'Phrases'
        elif tag == 'dt':
            self.term = value
        elif self.term and value:
            self.entries.append((self.section, self.term, value))
        self.tag = None


def convert(language, page):
    parser = PhraseList()
    parser.feed(page['text'])
    parser.close()
    if not parser.entries:
        raise ValueError('No phrase pairs found on this Wikivoyage page.')
    source = f"Wikivoyage contributors, {page['title']} · https://en.wikivoyage.org/wiki/Special:PermanentLink/{int(page['revid'])}"
    cards = []
    previous = None
    for section, term, translation in parser.entries:
        pair = term+'\n'+translation
        if section != previous or len(cards[-1]['body'])+len(pair)>3000:
            cards.append(dict(id=f'section-{len(cards)+1}', kind='phrase', title=f'{language} · {section}',
                              body=pair, source=source, terms=TERMS))
        else:
            cards[-1]['body']+='\n\n'+pair
        previous = section
    return field.check_pack(dict(format=field.PACK,id='wikivoyage-'+language.lower(),
                                 region=page['title'],cards=cards))


def download(language):
    if language not in LANGUAGES:
        raise ValueError('Choose a listed language.')
    params = urlencode(dict(action='parse', page=language+' phrasebook', prop='text|revid',
                            format='json', formatversion=2, redirects=1))
    request = Request('https://en.wikivoyage.org/w/api.php?'+params,
                      headers={'User-Agent':'Pocket-field-companion/1 (https://github.com/gordol/n810-revival)'})
    with urlopen(request,timeout=20) as response:
        raw = response.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:
        raise ValueError('Phrasebook download exceeds 4 MiB.')
    page = json.loads(raw).get('parse')
    if not page:
        raise ValueError('Wikivoyage did not return the requested phrasebook.')
    return convert(language,page)


def save(book):
    directory = field.state_root()/'phrasebooks'
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    field.write_file(directory/(field.identifier(book['id'])+'.pack'),field.check_pack(book))
