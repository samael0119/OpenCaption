import gzip
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from v020_evidence11 import eligible, metadata, safe_member, scan, MEMBER_MAX


def row(i=2000, name='1.wav', samples=32000, ref='Human text'):
    return dict(id=i, filename=name, samples=samples, reference=ref, gender='UNKNOWN')


class Evidence11Tests(unittest.TestCase):
    def test_selection_sorted_and_old_id_excluded(self):
        en=[row(2002,'2.wav'),row(2000),row(2001,'3.wav')]
        self.assertEqual([r['id'] for r in eligible(en,en,{2001})],[2000,2002])

    def test_repeated_speakers_same_reference_not_ambiguous(self):
        en=[row(),row(name='2.wav')]
        self.assertEqual(len(eligible(en,en,set())),2)

    def test_missing_and_ambiguous_chinese_rejected(self):
        self.assertEqual(eligible([row()],[],set()),[])
        self.assertEqual(eligible([row()],[row(),row(ref='Conflicting text')],set()),[])

    def test_conflicting_english_rejected(self):
        self.assertEqual(eligible([row(),row(ref='Other')],[row()],set()),[])

    def test_duration_boundaries(self):
        en=[row(i=2000+n,samples=s) for n,s in enumerate([15999,16000,80000,80001])]
        self.assertEqual([r['samples'] for r in eligible(en,en,set())],[16000,80000])

    def test_paths_and_links_and_size(self):
        for name in ['../1.wav','/1.wav','a/../../1.wav','a\\1.wav']:
            m=tarfile.TarInfo(name);m.size=10;self.assertFalse(safe_member(m))
        m=tarfile.TarInfo('1.wav');m.type=tarfile.SYMTYPE;m.size=10
        self.assertFalse(safe_member(m))
        m.type=tarfile.REGTYPE;m.size=MEMBER_MAX+1;self.assertFalse(safe_member(m))

    def test_complete_archive_member_payload(self):
        b=io.BytesIO()
        with tarfile.open(fileobj=b,mode='w:gz') as t:
            m=tarfile.TarInfo('test/1.wav');m.size=3;t.addfile(m,io.BytesIO(b'abc'))
        found,s=scan(io.BytesIO(b.getvalue()),{'1.wav'})
        self.assertEqual(found['1.wav']['data'],b'abc');self.assertIsNone(s['archive_end_error'])

    def test_partial_member_not_admitted(self):
        b=io.BytesIO()
        with tarfile.open(fileobj=b,mode='w') as t:
            m=tarfile.TarInfo('1.wav');m.size=20000;t.addfile(m,io.BytesIO(b'x'*20000))
        data=gzip.compress(b.getvalue()[:10000])
        found,s=scan(io.BytesIO(data),{'1.wav'})
        self.assertEqual(found,{});self.assertIsNotNone(s['archive_end_error'])

    def test_duplicate_basename_rejected(self):
        b=io.BytesIO()
        with tarfile.open(fileobj=b,mode='w:gz') as t:
            for name in ['a/1.wav','b/1.wav']:
                m=tarfile.TarInfo(name);m.size=3;t.addfile(m,io.BytesIO(b'abc'))
        with self.assertRaises(ValueError):scan(io.BytesIO(b.getvalue()),{'1.wav'})

    def test_metadata_complete_seven_columns_and_original_text(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'metadata.tsv';p.write_text('2000\t1.wav\tExact human text.\tn\tu\t32000\tFEMALE\n2001\tmissing\n')
            rows=metadata(p)
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['reference'],'Exact human text.')


if __name__ == '__main__':unittest.main()
