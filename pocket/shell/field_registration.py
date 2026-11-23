"""Lazy desktop entries for offline field apps."""


def entry(identifier, title, kind, description):
    def create(host):
        from field_views import FieldView
        return FieldView(kind)
    return dict(id=identifier, title=title, factory=create, category='Field',
                preferred_size=(78, 22), minimum_size=(32, 12), description=description,
                help=((title, ('I imports a prepared pack. R reloads the active region.',
                               'Tab switches between the list and text. Arrows select or scroll.',
                               'F filters entries. In Field Log, N starts a note and Enter saves it.')),))


def guide():
    return entry('field-guide', 'Field Guide', 'guide', 'Read sourced regional guide cards offline')


def phrases():
    return entry('field-phrases', 'Phrasebook', 'phrase', 'Browse prepared phrases offline')


def log():
    return entry('field-log', 'Field Log', 'log', 'Keep private observations by region')
