import unittest

from pixiv.parser import parse_ids


class ParserTests(unittest.TestCase):
    def test_mixed_text_and_ordered_duplicates(self):
        text = 'TapTap\npixiv id：97003966\n今日は冷えますねっ…-pixiv id：103816477\n97003966\n97720788'
        self.assertEqual(parse_ids(text), ['97003966', '103816477', '97720788'])

    def test_links_legacy_and_non_artwork_urls(self):
        text = ('https://www.pixiv.net/en/artworks/103816477\n'
                'https://www.pixiv.net/member_illust.php?mode=medium&illust_id=97003966\n'
                'https://www.pixiv.net/users/12345678\n'
                'https://www.pixiv.net/novel/show.php?id=88776655\n'
                'https://evil.example/artworks/11223344')
        self.assertEqual(parse_ids(text), ['103816477', '97003966'])

    def test_dates_and_numbers_in_titles_are_not_ids(self):
        self.assertEqual(parse_ids('2026-10-01\n作者12345678\n今天是2026年\nID: 7654321'), ['7654321'])

    def test_numeric_lists_and_fullwidth_text(self):
        self.assertEqual(parse_ids('００９７００３９６６，103816477; 97720788\n0\n-1234567'),
                         ['97003966', '103816477', '97720788'])

    def test_empty_and_oversized(self):
        self.assertEqual(parse_ids(' \n99999999999999999999'), [])


if __name__ == '__main__':
    unittest.main()
