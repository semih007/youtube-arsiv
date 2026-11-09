"""core.parser birim testleri.

Çalıştırma:  python -m unittest tests.test_parser -v
(Proje kökünden: youtube-arsiv)
"""

import unittest

from core.parser import ParseError, parse


class TestPlaylistParsing(unittest.TestCase):
    def test_playlist_url(self):
        t = parse("https://www.youtube.com/playlist?list=PLwIOf35e8aFWECZ4pGw-7rCrFwEhX3rzz")
        self.assertEqual(t.playlist_id, "PLwIOf35e8aFWECZ4pGw-7rCrFwEhX3rzz")
        self.assertIsNone(t.video_id)

    def test_playlist_url_with_extra_params(self):
        t = parse("https://www.youtube.com/playlist?list=PLabc123&si=xyz&app=desktop")
        self.assertEqual(t.playlist_id, "PLabc123")

    def test_bare_playlist_id(self):
        t = parse("PLwIOf35e8aFWECZ4pGw-7rCrFwEhX3rzz")
        self.assertEqual(t.playlist_id, "PLwIOf35e8aFWECZ4pGw-7rCrFwEhX3rzz")
        self.assertIsNone(t.video_id)

    def test_bare_upload_playlist(self):
        t = parse("UUxxxxxxxxxxxxxxxxxxxxxx")
        self.assertEqual(t.playlist_id, "UUxxxxxxxxxxxxxxxxxxxxxx")


class TestVideoParsing(unittest.TestCase):
    def test_watch_url(self):
        t = parse("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(t.video_id, "dQw4w9WgXcQ")
        self.assertIsNone(t.playlist_id)

    def test_watch_url_with_all_params(self):
        t = parse(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            "&list=PLwIOf35e8aFWECZ4pGw-7rCrFwEhX3rzz&index=1"
        )
        self.assertEqual(t.video_id, "dQw4w9WgXcQ")
        self.assertEqual(t.playlist_id, "PLwIOf35e8aFWECZ4pGw-7rCrFwEhX3rzz")

    def test_short_url(self):
        t = parse("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(t.video_id, "dQw4w9WgXcQ")
        self.assertIsNone(t.playlist_id)

    def test_short_url_with_playlist(self):
        t = parse("https://youtu.be/dQw4w9WgXcQ?list=PLabc123456789012345")
        self.assertEqual(t.video_id, "dQw4w9WgXcQ")
        self.assertEqual(t.playlist_id, "PLabc123456789012345")

    def test_music_youtube(self):
        t = parse("https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=RDabc12345678")
        self.assertEqual(t.video_id, "dQw4w9WgXcQ")
        self.assertEqual(t.playlist_id, "RDabc12345678")

    def test_bare_video_id(self):
        t = parse("dQw4w9WgXcQ")
        self.assertEqual(t.video_id, "dQw4w9WgXcQ")
        self.assertIsNone(t.playlist_id)

    def test_whitespace_and_angles(self):
        t = parse("  <https://www.youtube.com/watch?v=dQw4w9WgXcQ>  ")
        self.assertEqual(t.video_id, "dQw4w9WgXcQ")


class TestErrors(unittest.TestCase):
    def test_empty(self):
        with self.assertRaises(ParseError):
            parse("")

    def test_garbage(self):
        with self.assertRaises(ParseError):
            parse("merhaba dunya")

    def test_other_site(self):
        with self.assertRaises(ParseError):
            parse("https://example.com/watch?v=dQw4w9WgXcQ")

    def test_too_short_video_id(self):
        with self.assertRaises(ParseError):
            parse("https://www.youtube.com/watch?v=kisa")


class TestHelpers(unittest.TestCase):
    def test_urls(self):
        from core.parser import playlist_url, video_url

        self.assertEqual(
            playlist_url("PLabc"),
            "https://www.youtube.com/playlist?list=PLabc",
        )
        self.assertEqual(video_url("dQw4w9WgXcQ"), "https://www.youtube.com/watch?v=dQw4w9WgXcQ")


if __name__ == "__main__":
    unittest.main()
