import math
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from party import Party
from wire import ProtocolError, string


def roster(leader):
    payload = struct.pack('<h', 2)
    for slot, actor, name in ((0, 111, 'Arden'), (3, 222, 'Leader')):
        payload += struct.pack('<hhI', slot, 0, actor) + string(name)
        for code in ('i','i','i','i','h','h','h','H','i','i','h',
                     'i','i','i','i','q','q','q','i','h','b'):
            payload += struct.pack('<' + code, 0)
    return payload + struct.pack('<h', leader)


class PartyTests(unittest.TestCase):
    def test_roster_tracks_current_leader_instead_of_first_member(self):
        party = Party()
        self.assertEqual(party.roster(roster(3)), 222)
        self.assertEqual(party.roster(roster(0)), 111)

    def test_malformed_roster_does_not_replace_valid_roster(self):
        party = Party()
        party.roster(roster(3))
        for invalid in (roster(0)[:-1], struct.pack('<h', 41)):
            with self.assertRaises(ProtocolError):
                party.roster(invalid)
            self.assertEqual(party.leader, 222)

    def test_following_rejects_stale_and_nonfinite_coordinates(self):
        party = Party()
        party.roster(roster(3))
        with patch('party.time.monotonic', return_value=10):
            party.position(struct.pack('<Ihff', 222, 2, 50, 70))
        self.assertEqual(party.destination(now=29), (2, 50, 70))
        self.assertIsNone(party.destination(now=30))
        with self.assertRaises(ProtocolError):
            party.position(struct.pack('<Ihff', 222, 2, math.nan, 70))

    def test_leaving_party_clears_leader_and_positions(self):
        party = Party()
        party.roster(roster(3))
        party.position(struct.pack('<Ihff', 222, 2, 50, 70))
        party.leave(struct.pack('<hb', 0, 0), 111)
        self.assertEqual(party.members, {})
        self.assertIsNone(party.destination())

    def test_invitation_answer_keeps_inviter_and_kind(self):
        party = Party()
        answer, name, context = party.invitation(struct.pack('<I', 222) + string('Leader') + struct.pack('<hhh', 7, 8, 2))
        self.assertEqual(answer, struct.pack('<hIhh', 0, 222, 2, 1))
        self.assertEqual((name, context), ('Leader', (7, 8, 2)))

    def test_real_notice_metadata_is_not_returned_as_busy_result(self):
        answer, _, _ = Party().invitation(struct.pack('<I', 50000001) + string('Zrymund') + struct.pack('<hhh', 3, 1, 0))
        self.assertEqual(answer, struct.pack('<hIhh', 0, 50000001, 0, 1))


if __name__ == '__main__':
    unittest.main()
