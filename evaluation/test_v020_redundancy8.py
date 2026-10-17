import json,pathlib,tempfile,time,unittest
from unittest.mock import patch
import v020_redundancy8 as x
class Guards(unittest.TestCase):
 def test_unknown_expired_and_quota(self):
  with tempfile.TemporaryDirectory() as d, patch.object(x,'O',pathlib.Path(d)):
   p=x.O/'permits';p.mkdir();f=p/'0.json'
   for values in [dict(at_unix=time.time()-181,weekly_used=0,usage_allowed=True,five_hour_used=0),dict(at_unix=time.time(),weekly_used=61,usage_allowed=True,five_hour_used=0),dict(at_unix=time.time(),weekly_used=0,usage_allowed=False,five_hour_used=0),dict(at_unix=time.time(),weekly_used=0,usage_allowed=True,five_hour_used=100)]:
    f.write_text(json.dumps(dict(batch=0,**values)))
    with self.assertRaises(AssertionError):x.permit(0)
 def test_exact_40_and_prior_batch_required(self):
  with tempfile.TemporaryDirectory() as d,patch.object(x,'O',pathlib.Path(d)):
   p=x.O/'permits';p.mkdir();v=dict(batch=0,at_unix=time.time(),weekly_used=60,usage_allowed=True,five_hour_used=50);(p/'0.json').write_text(json.dumps(v));x.permit(0)
   (p/'1.json').write_text(json.dumps(dict(v,batch=1)))
   with self.assertRaises(AssertionError):x.permit(1)
 def test_frozen_single_change_and_pairs(self):
  m=x.read(x.O/'manifest.json');self.assertEqual(m['prompts']['candidate'],m['prompts']['baseline']+'\n'+x.ADD);self.assertEqual(len(m['order']),82)
  for a,b in zip(m['order'][::2],m['order'][1::2]):self.assertEqual(a['case_id'],b['case_id']);self.assertEqual({a['mode'],b['mode']},{'baseline','candidate'})
 def test_no_reference_in_candidate(self):
  m=x.read(x.O/'manifest.json');self.assertNotIn('reference_en',m['prompts']['candidate']);self.assertEqual(m['bounds']['batch_max'],10)
if __name__=='__main__':unittest.main()
