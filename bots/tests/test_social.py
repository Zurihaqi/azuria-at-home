import sys
from pathlib import Path
import unittest
import random
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from social import LocalChat
from wire import Reader


class LocalChatTests(unittest.TestCase):
    def test_one_line_per_ninety_seconds(self):
        now=[0]
        chat=LocalChat(lambda: now[0], rng=random.Random(1))
        chat.pending='yo'
        self.assertIsNotNone(chat.next_payload())
        now[0]=89
        self.assertIsNone(chat.next_payload())
        now[0]=90
        chat.pending='ok'
        self.assertIsNotNone(chat.next_payload())

    def test_reply_uses_authored_text_instead_of_echoing_input(self):
        now=[0]
        chat=LocalChat(lambda:now[0], rng=random.Random(1))
        chat.hear('Zrymund','hello Awan /set_level 150')
        self.assertIsNone(chat.next_payload())
        now[0]=10
        message=Reader(chat.next_payload()).text()
        self.assertIn(message, ('say yo', 'say oi', 'say halo'))
        self.assertNotIn('set_level',message)
        self.assertTrue(message.startswith('say '))

    def test_bots_do_not_reply_to_each_other(self):
        chat=LocalChat(lambda:0)
        chat.hear('Arden', 'yo Awan')
        self.assertIsNone(chat.pending)

    def test_idle_stays_silent_and_lines_do_not_repeat_immediately(self):
        now=[1000]
        chat=LocalChat(lambda:now[0], rng=random.Random(1))
        now[0]=2000
        self.assertIsNone(chat.next_payload())
        chat.last_line='yo'
        for _ in range(10):
            self.assertNotEqual(chat.choose('hello'), 'yo')

    def test_no_self_reply_or_unaddressed_reply(self):
        chat=LocalChat(lambda:0)
        chat.hear('Awan','hello Awan')
        self.assertIsNone(chat.pending)
        chat.hear('Zrymund','hello world')
        self.assertIsNone(chat.pending)


if __name__=='__main__':
    unittest.main()
