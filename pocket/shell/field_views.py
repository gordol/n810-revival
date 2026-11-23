"""Pocket views over one locally selected pack and a separate private journal."""
from types import SimpleNamespace
import sqlite3

from app_widgets import DetailBlock, TextInput
import field_companion as field
from native_documents import DocumentView, prose


class FieldView(DocumentView):
    actions = (('i', 'Import pack'), ('r', 'Reload'), ('F', 'Filter'))
    shortcuts = {'i': 'import_local', 'r': 'reload', 'F': 'search'}
    entry_labels = {'import_local': 'Pack file', 'search': 'Filter', 'note': 'New note', 'import_notes': 'Observation file'}
    content_title = 'Detail'

    def __init__(self, kind):
        super().__init__(self.command)
        self.kind = kind
        self.root = field.state_root()
        self.item_title = {'guide': 'Guide cards', 'phrase': 'Phrases', 'log': 'Observations'}[kind]
        self.empty_message = 'No matching entries'
        self.region = None
        self.records = []
        if kind == 'log':
            self.actions += (('n', 'New note'), ('m', 'Import log'))
            self.shortcuts = dict(self.shortcuts, n='note', m='import_notes')
        self.command('reload')

    def activate(self, action):
        if action == 'import_notes':
            self.begin(action)
        elif action == 'note':
            if self.region:
                self.entry_action = action
                self.entry = TextInput('', limit=1024)
            else:
                self.notice = 'Import a regional pack first'
        else:
            super().activate(action)

    def open(self):
        self.command('reload')

    def action(self, action):
        if action == 'open':
            self.layout.select('detail')
            self.scroll = 0
        else:
            self.command(action)

    def command(self, action, value=''):
        try:
            added = None
            if action == 'import_notes':
                added = field.Journal(self.root).merge(field.read_log(value))
            if action == 'note':
                if not self.region:
                    raise ValueError('Import a regional pack first')
                note = field.observation(self.region['id'], 'Pocket keyboard', 'note', value)
                field.Journal(self.root).merge(dict(format=field.LOG, notes=[note]))
            if action != 'search':
                region = field.activate(value, self.root) if action == 'import_local' else field.active(self.root)
                if not region:
                    rows = []
                elif self.kind == 'log':
                    rows = field.Journal(self.root).recent(region['id'])
                else:
                    rows = [card for card in region['cards'] if card['kind'] == self.kind]
                if self.kind == 'phrase':
                    for path in sorted((self.root/'phrasebooks').glob('*.pack')):
                        book = field.check_pack(field.read_file(path))
                        if not region or book['id'] != region['id']:
                            rows.extend(book['cards'])
                self.region, self.records = region, rows
            self.query = value if action == 'search' else self.query
            rows = [SimpleNamespace(**row) for row in self.records
                    if self.query.casefold() in (row.get('title', '')+' '+row['body']).casefold()]
            self.update(object(), rows)
            self.notice = 'Note saved' if action == 'note' else ''
            if added is not None:
                self.notice = f'{added} observations imported'
        except (OSError, ValueError, sqlite3.Error) as error:
            self.notice = str(error)
            if action == 'note':
                self.entry_action = action
                self.entry = TextInput(value, limit=1024)

    def subtitle(self):
        if self.kind == 'phrase' and self.records and not self.region:return 'Downloaded phrasebooks'
        return self.region['region'] if self.region else 'I: import a regional pack'

    def row_label(self, row):
        return row.body.splitlines()[0][:100] if self.kind == 'log' else row.title

    def body(self, width):
        body = DetailBlock(width)
        row = self.selected()
        if row:
            body.section(row.time if self.kind == 'log' else row.title)
            prose(body, row.body)
            body.field('Source', row.source)
            if self.kind == 'log':
                body.field('Type', row.kind)
            else:
                body.field('Terms', row.terms)
        return body
