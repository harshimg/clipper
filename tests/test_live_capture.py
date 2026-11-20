"""A link still on air is clipped from its last LIVE_MINUTES (main.capture_live_tail).

YouTube's live HLS playlists list the last ~60 min of a broadcast, video and
audio apart; the helpers below pick the playlists, count how many segments
back from the live edge cover the minutes asked for, and recognise a live
source. A channel's /live link is one video (its current broadcast).
"""
import pytest

from yt_clients import youtube_non_video_reason

main = pytest.importorskip("main")


def _playlist(durations):
    lines = ["#EXTM3U", "#EXT-X-TARGETDURATION:5", "#EXT-X-MEDIA-SEQUENCE:100"]
    for i, d in enumerate(durations):
        lines += [f"#EXTINF:{d},", f"seg{i}.ts"]
    return "\n".join(lines)


class TestSegmentsFromTheLiveEdge:
    def test_counts_back_until_the_minutes_are_covered(self):
        count, window = main.live_segments_for(_playlist([5.0] * 720), 180)
        assert count == 36 and window == 3600

    def test_never_more_than_the_playlist_holds(self):
        count, window = main.live_segments_for(_playlist([5.0] * 10), 600)
        assert count == 10 and window == 50

    def test_uneven_segments(self):
        # From the edge: 4, then 4 + 6 = 10 covers 9 s; 11 s needs one more.
        count, _ = main.live_segments_for(_playlist([2.0, 2.0, 6.0, 4.0]), 9)
        assert count == 2
        count, _ = main.live_segments_for(_playlist([2.0, 2.0, 6.0, 4.0]), 11)
        assert count == 3

    def test_empty_or_garbage(self):
        assert main.live_segments_for("", 60) == (0, 0)
        assert main.live_segments_for("#EXTINF:abc,\nx.ts", 60) == (0, 0)


def _fmt(fid, height=None, vcodec="avc1", acodec="none", tbr=None, protocol="m3u8_native"):
    return {"format_id": fid, "url": f"https://example.invalid/{fid}.m3u8", "protocol": protocol,
            "height": height, "vcodec": vcodec, "acodec": acodec, "tbr": tbr}


class TestPickFormats:
    YOUTUBE = [
        _fmt("233", vcodec="none", acodec=None),
        _fmt("234", vcodec="none", acodec=None),
        _fmt("229", 240, tbr=500), _fmt("232", 720, tbr=2400),
        _fmt("270", 1080, tbr=4500), _fmt("311", 1440, tbr=9000),
    ]

    def test_youtube_video_and_audio_apart(self):
        video, audio = main.pick_live_hls_formats(self.YOUTUBE)
        assert video["format_id"] == "270" and audio["format_id"] == "234"

    def test_height_cap(self):
        video, _ = main.pick_live_hls_formats(self.YOUTUBE, max_height=720)
        assert video["format_id"] == "232"

    def test_muxed_format_is_used_alone(self):
        video, audio = main.pick_live_hls_formats([_fmt("720p", 720, acodec="mp4a.40.2")])
        assert video["format_id"] == "720p" and audio is None

    def test_no_hls_video(self):
        dash = [_fmt("137", 1080, protocol="https")]
        assert main.pick_live_hls_formats(dash) == (None, None)
        assert main.pick_live_hls_formats(None) == (None, None)


class TestLiveMinutes:
    @pytest.mark.parametrize("raw, minutes", [
        ("", 30.0), ("10", 10.0), ("0", 1.0), ("500", 60.0), ("abc", 30.0),
    ])
    def test_bounded_with_a_default(self, monkeypatch, raw, minutes):
        monkeypatch.setenv("LIVE_MINUTES", raw)
        assert main.live_minutes_requested() == minutes

    def test_source_is_live(self):
        assert main.source_is_live({"live_status": "is_live"})
        assert main.source_is_live({"is_live": True})
        assert not main.source_is_live({"live_status": "was_live"})
        assert not main.source_is_live({})
        assert not main.source_is_live(None)


class TestChannelLiveLink:
    def test_a_channels_live_link_is_one_video(self):
        assert youtube_non_video_reason("https://www.youtube.com/@LofiGirl/live") is None

    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/@LofiGirl",
        "https://www.youtube.com/@LofiGirl/videos",
        "https://www.youtube.com/@LofiGirl/live/extra",
    ])
    def test_the_rest_of_a_channel_still_is_not(self, url):
        assert youtube_non_video_reason(url)
