"""Keep image items exposed by yt-dlp's normal logged-out Instagram response.

No alternate login, cookies or access-restriction bypass. Only media_type=1
items are images; a video's thumbnail is never substituted for a failed video.
"""

from yt_dlp.extractor.instagram import InstagramIE


class InstagramMediaIE(InstagramIE):
    def _extract_product_media(self, product_media):
        result = super()._extract_product_media(product_media)
        if product_media.get("media_type") == 1:
            candidates = [
                c
                for c in product_media.get("image_versions2", {}).get("candidates", [])
                if isinstance(c, dict) and str(c.get("url", "")).startswith("https://")
            ]
            if candidates:
                best = max(
                    candidates,
                    key=lambda c: (c.get("width") or 0) * (c.get("height") or 0),
                )
                result.update(
                    media_type="image",
                    image_url=best["url"],
                    thumbnail=best["url"],
                    width=best.get("width"),
                    height=best.get("height"),
                )
                # The parent extractor's "no video" check requires a format.
                # Image results are processed by our image downloader, never as video.
                result["formats"] = [
                    {
                        "url": best["url"],
                        "protocol": "https",
                        "vcodec": "none",
                        "acodec": "none",
                        "width": best.get("width"),
                        "height": best.get("height"),
                    }
                ]
        else:
            result["media_type"] = "video"
        for fmt in result.get("formats", []):
            if not fmt.get("protocol") and str(fmt.get("url", "")).startswith(
                "https://"
            ):
                fmt["protocol"] = "https"
        return result
