"""Include private-contact contract checks in the normal release suite."""
import importlib.util
from pathlib import Path
path=Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum/tests/test_private_rendezvous.py'
spec=importlib.util.spec_from_file_location('private_contact_contract_tests',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
PrivateContact=module.PrivateContact
