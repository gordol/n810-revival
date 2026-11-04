"""Optional touch fixture; registered only in a separate runtime candidate."""
from pathlib import Path
import importlib.util


def create(host):
    spec = importlib.util.spec_from_file_location('_nokia_touch_lab', Path(__file__).with_name('app.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TouchLab(host)


def descriptor():
    return dict(id='nokia-touch-lab', title='Touch lab', factory=create,
                preferred_size=(62,23), minimum_size=(48,20), category='Experiments',
                description='Human-operated touch and drag comparison',
                help=(('Test', ('Drag the square; then drag this window title.',
                                'Use the real Station Map overview for the target test.',
                                'Space snapshots existing diagnostics; R resets the square.')),))
