import copy
import unittest
from pathlib import Path
import v020_architecture_screen as first
import v020_architecture_precision as second

class PrecisionGuards(unittest.TestCase):
    def setUp(self):
        self.model={'revision':'pinned','files':[
            {'path':'encoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx','sha256':'a'},
            {'path':'decoder.int8.onnx','sha256':'b'},
            {'path':'joiner.int8.onnx','sha256':'c'},
            {'path':'tokens.txt','sha256':'d'}]}
        self.replacement={'revision':'pinned','path':'encoder-epoch-99-avg-1-chunk-16-left-128.onnx','sha256':'e'}

    def test_only_encoder_changes_without_mutating_control(self):
        old=copy.deepcopy(self.model)
        changed=second.replace_encoder(self.model,self.replacement)
        self.assertEqual(self.model,old)
        self.assertEqual(changed['files'][1:],old['files'][1:])
        self.assertEqual(changed['files'][0]['sha256'],'e')

    def test_reject_different_revision_or_context(self):
        for patch in [{'revision':'different'},{'path':'encoder-epoch-99-avg-1-chunk-16-left-64.onnx'}]:
            with self.assertRaises(RuntimeError): second.replace_encoder(self.model,{**self.replacement,**patch})

    def test_same_decoding_and_feed(self):
        self.assertEqual(first.CONFIG,second.CONFIG)
        pcm=list(range(6000))
        self.assertEqual(list(first.chunks(pcm)),list(second.chunks(pcm)))

    def test_separate_artifact_directory(self):
        self.assertNotEqual(first.OUT,second.OUT)
        self.assertEqual(second.OUT.name,'screen2')

if __name__=='__main__': unittest.main()
