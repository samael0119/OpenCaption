import unittest

from s0_protocol_live import parse_json_caption
from s0_scene_state import MapEvidence


class JsonCaptionTests(unittest.TestCase):
    def test_both_languages_required(self):
        self.assertEqual(parse_json_caption('{"speech":true,"english":"yes","chinese":"是"}').status, 'subtitle')
        self.assertEqual(parse_json_caption('{"speech":true,"english":"","chinese":"是"}').status, 'invalid')

    def test_truncated_json_and_wrong_types_rejected(self):
        self.assertEqual(parse_json_caption('{"speech":true,"english":"yes"').status, 'invalid')
        self.assertEqual(parse_json_caption('{"speech":1,"english":"yes","chinese":"是"}').status, 'invalid')

    def test_no_speech_cannot_contain_invented_caption(self):
        self.assertEqual(parse_json_caption('{"speech":false,"english":"","chinese":""}').status, 'no_speech')
        self.assertEqual(parse_json_caption('{"speech":false,"english":"yes","chinese":"是"}').status, 'invalid')


class MapRecoveryTests(unittest.TestCase):
    def test_duplicate_frame_cannot_confirm_a_scene(self):
        state = MapEvidence()
        state.update('through Secret', 0, 'one')
        self.assertIsNone(state.update('holding Silo', 1000, 'one')['map'])

    def test_different_location_mentions_support_map(self):
        state = MapEvidence()
        state.update('through Secret', 0, 'one')
        self.assertEqual(state.update('holding Silo', 1000, 'two')['map'], 'Nuke')

    def test_wrong_scene_loses_support_on_conflict_and_recovers(self):
        state = MapEvidence()
        self.assertEqual(state.update('on Nuke', 0, 1)['map'], 'Nuke')
        self.assertIsNone(state.update('on Mirage', 5000, 2)['map'])
        self.assertEqual(state.update('on Mirage', 10000, 3)['map'], 'Mirage')

    def test_expiration_without_new_speech(self):
        state = MapEvidence()
        state.update('on Nuke', 0, 1)
        self.assertEqual(state.view(60000)['status'], 'unknown')

    def test_history_and_prompted_names_cannot_reinforce(self):
        state = MapEvidence()
        self.assertIsNone(state.update('last map was on Mirage', 0, 1)['map'])
        self.assertIsNone(state.update('on Nuke', 1000, 2, ['Nuke'])['map'])

    def test_old_epoch_cannot_restore_cleared_scene(self):
        state = MapEvidence()
        state.reset()
        self.assertIsNone(state.update('on Nuke', 0, 1, epoch=0)['map'])

    def test_shared_point_requires_independent_unique_anchor(self):
        state = MapEvidence()
        self.assertIsNone(state.update('up the vent', 0, 1)['map'])
        self.assertEqual(state.update('on lobby', 5000, 2)['map'],'Nuke')

    def test_alias_spellings_cannot_create_two_location_concepts(self):
        state = MapEvidence()
        state.update('up the vent',0,1)
        self.assertIsNone(state.update('up the vents',5000,2)['map'])
        state = MapEvidence()
        state.update('through Decon',0,1)
        self.assertIsNone(state.update('through Decontamination',5000,2)['map'])

    def test_conflicting_unique_location_releases_supported_map(self):
        state = MapEvidence()
        state.update('up the vent',0,1)
        self.assertEqual(state.update('on lobby',5000,2)['map'],'Nuke')
        self.assertIsNone(state.update('through long doors',10000,3)['map'])

    def test_prompted_alias_variants_cannot_reinforce_map(self):
        state=MapEvidence()
        state.update('up the vents',0,1,['Vent'])
        self.assertIsNone(state.update('on lobby',5000,2)['map'])

    def test_current_negation_releases_map_and_mixed_clause_keeps_positive(self):
        state=MapEvidence()
        state.update('on Nuke',0,1)
        self.assertIsNone(state.update('we are not on Nuke',5000,2)['map'])
        self.assertEqual(state.update('not on Nuke but playing Mirage',10000,3)['map'],'Mirage')

    def test_negated_location_does_not_supply_evidence(self):
        state=MapEvidence()
        state.update('not going through Secret',0,1)
        self.assertIsNone(state.update('holding Silo',5000,2)['map'])

    def test_late_old_epoch_cannot_expire_or_erase_new_scene(self):
        state=MapEvidence()
        state.reset()
        state.update('on Nuke',5000,1,epoch=1)
        self.assertEqual(state.update('on Mirage',100000,2,epoch=0)['map'],'Nuke')
        self.assertEqual(state.update('on Mirage',0,3,epoch=0)['map'],'Nuke')

    def test_out_of_order_same_epoch_cannot_change_current_scene(self):
        state=MapEvidence()
        state.update('on Nuke',5000,1)
        self.assertEqual(state.update('on Mirage',1000,2)['map'],'Nuke')
        self.assertEqual(state.view(1000)['map'],'Nuke')


if __name__ == '__main__':
    unittest.main()
