from collections import Counter
import unittest

from v020_round3_candidate import blocks_for, execute_blocks, runtime_args


class CandidateSafetyTest(unittest.TestCase):
    def cases(self):
        return [dict(id=f'{g}{i}',group=g) for g,n in [('f',6),('w',18),('o',12),('m',4),('s',1)] for i in range(n)]

    def test_every_case_paired_once_with_group_balancing(self):
        cases=self.cases();blocks=blocks_for(cases)
        counts=Counter((v,b['mode']) for b in blocks for v in b['case_ids'])
        self.assertEqual(sum(counts.values()),82)
        self.assertTrue(all(counts[(c['id'],m)]==1 for c in cases for m in ['auto','disabled']))
        for group in ['f','w','o','m','s']:
            ids={c['id'] for c in cases if c['group']==group}
            self.assertLessEqual(abs(len(ids.intersection(blocks[0]['case_ids']))-len(ids.intersection(blocks[2]['case_ids']))),1)

    def test_runtime_preserves_context_and_only_changes_speculation(self):
        a=vars(runtime_args('auto'));b=vars(runtime_args('disabled'))
        self.assertEqual([k for k in a if a[k]!=b[k]],['speculative_decoding'])
        self.assertEqual(b['max_context_tokens'],768)
        self.assertEqual(b['max_new_tokens'],128)

    def test_single_lifetime_closed_before_next_load(self):
        active=[];seen=[]
        def create(mode,index):
            self.assertFalse(active);active.append(index);return index
        def consume(model,case,mode,index,offset): seen.append((case,mode))
        def close(model,index): self.assertEqual(active.pop(),index)
        execute_blocks(blocks_for(self.cases()),create,consume,close)
        self.assertFalse(active);self.assertEqual(len(seen),82)

    def test_request_failure_closes_and_never_retries_or_loads_next(self):
        loads=[];closed=[];calls=[]
        def create(mode,index): loads.append(index);return index
        def consume(model,case,mode,index,offset): calls.append(case);raise RuntimeError('synthetic transport fault')
        def close(model,index): closed.append(index)
        with self.assertRaises(RuntimeError): execute_blocks(blocks_for(self.cases()),create,consume,close)
        self.assertEqual(loads,[0]);self.assertEqual(closed,[0]);self.assertEqual(len(calls),1)


if __name__=='__main__': unittest.main()
