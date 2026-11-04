"""Pinned APRS advertised-symbol filter semantics, not observed capabilities."""
import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('model',Path(__file__).with_name('n810-directory-model.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class SymbolClassificationTests(unittest.TestCase):
 def test_primary_mobile_master_list(self):
  expected=set("!'<=>()*0123456789CFOPRSUXY[\\^abefgjkpsuv")
  for code in map(chr,range(33,127)):
   self.assertEqual(m.classify_symbol('/',code)['advertised_mobile_symbol'],code in expected,code)
 def test_alternate_and_supported_overlays_share_mobile_base(self):
  expected=set('>KOSY[^ksuv\\')
  for table in ('\\','A','Z','0','9'):
   for code in map(chr,range(33,127)):
    self.assertEqual(m.classify_symbol(table,code)['advertised_mobile_symbol'],code in expected,(table,code))
 def test_gateway_and_link_base_with_overlay(self):
  for table,code in [('/','&'),('\\','&'),('I','&'),('R','&'),('T','&'),('2','&'),('Z','&'),('\\','0'),('E','0'),('I','0'),('W','0')]:
   result=m.classify_symbol(table,code)
   self.assertTrue(result['advertised_gateway_link_symbol']);self.assertEqual((result['table'],result['code']),(table,code))
   self.assertNotIn('internet_available',result);self.assertNotIn('reachable',result);self.assertNotIn('moving',result)
 def test_table_distinctions_and_no_repeater_or_gateway_from_digi(self):
  self.assertTrue(m.classify_symbol('/','0')['advertised_mobile_symbol'])
  self.assertFalse(m.classify_symbol('\\','0')['advertised_mobile_symbol'])
  self.assertFalse(m.classify_symbol('/','0')['advertised_gateway_link_symbol'])
  for table,code in [('/','#'),('A','#'),('/','r'),('/','-')]:
   result=m.classify_symbol(table,code);self.assertFalse(result['advertised_gateway_link_symbol'])
   self.assertNotIn('repeater',result)
 def test_unknown_invalid_or_unsupported_table_is_explicit(self):
  for table,code in [(None,'>'),('/',''),('/','xx'),('/','\0'),('é','>'),('a','>'),('!','>')]:
   result=m.classify_symbol(table,code)
   self.assertIsNone(result['advertised_mobile_symbol']);self.assertIsNone(result['advertised_gateway_link_symbol'])

if __name__=='__main__':unittest.main()
