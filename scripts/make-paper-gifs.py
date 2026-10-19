#!/usr/bin/env python3
"""Create small animated paper covers from local media; keep originals intact.

Requires Python 3, ffmpeg and ffprobe. Run after downloading the full repository.
By default, use six-second action sequences selected from the original videos.
Use --paper NAME --start SECONDS to choose another action sequence.
"""

import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


PAPERS = {
    "wsim": {
        "source": "images/IJMS23_WSIM_robot/WSIM_video.mp4",
        "poster": "images/IJMS23_WSIM_robot/WSIM_cover.jpg",
        "start": 50,
    },
    "robio": {
        "source": "images/ROBIO2022/robio_video.mp4",
        "poster": "images/ROBIO2022/robio_cover.png",
        "start": 8,
    },
    "interactive-nav": {
        "source": "images/Interactive_Nav_IROS_2025_final.gif",
        "poster": "images/interNav_iros.jpg",
        "start": 40,
        # Focus on the arm-pushing experiment rather than the entire slide.
        "crop": (366, 214, 96, 94),
    },
}


def run(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def probe(path):
    data = json.loads(run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,nb_frames,duration:format=duration",
        "-of", "json", str(path),
    ]))
    if not data.get("streams"):
        raise ValueError(f"No video stream in {path}")
    stream = data["streams"][0]
    duration = float(data.get("format", {}).get("duration") or stream.get("duration", 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"Could not determine a positive duration for {path}")
    return duration, stream


def picture_markup(page, name, poster):
    """Plan the HTML edit before converting anything, and support repeat runs."""
    output_url = f"images/paper-previews/{name}.gif"
    marker = f'srcset="{output_url}"'
    if page.count(marker) == 1:
        return page
    if page.count(marker) > 1:
        raise ValueError(f"Duplicate animated cover for {name}")
    pattern = r'<img\b[^>]*\bsrc="' + re.escape(poster) + r'"[^>]*>'
    matches = list(re.finditer(pattern, page))
    if len(matches) != 1:
        raise ValueError(f"Expected one poster for {name}; found {len(matches)}. Apply the homepage redesign first.")
    match = matches[0]
    replacement = (
        '<picture>\n'
        '              <source media="(prefers-reduced-motion: no-preference)" '
        f'srcset="{output_url}" type="image/gif">\n'
        f'              {match.group()}\n'
        '            </picture>'
    )
    return page[:match.start()] + replacement + page[match.end():]


def encode(source, target, start, duration, width, fps, max_bytes, crop=None):
    # Palette-based conversion with progressively smaller settings if necessary.
    # A single FFmpeg process avoids intermediate uncompressed video files.
    profiles = [
        (width, fps, 128, duration),
        (min(width, 400), min(fps, 8), 96, duration),
        (min(width, 320), min(fps, 8), 64, duration),
        (min(width, 320), min(fps, 6), 64, min(duration, 4)),
    ]
    for w, rate, colors, length in dict.fromkeys(profiles):
        crop_filter = "crop=" + ":".join(map(str, crop)) + "," if crop else ""
        filters = crop_filter + (
            f"fps={rate},scale='min({w},iw)':-2:flags=lanczos,split[a][b];"
            f"[a]palettegen=max_colors={colors}:stats_mode=diff[p];"
            "[b][p]paletteuse=dither=bayer:bayer_scale=3[v]"
        )
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-filter_complex_threads", "1", "-ss", str(start),
            "-t", str(length), "-i", str(source), "-filter_complex", filters,
            "-map", "[v]", "-an", "-loop", "0", str(target),
        ])
        if target.stat().st_size <= max_bytes:
            actual_duration, stream = probe(target)
            if int(stream.get("nb_frames", 0)) < 2:
                raise ValueError(f"The selected excerpt of {source.name} contains fewer than two frames")
            # Decode the entire output, not just its metadata.
            run(["ffmpeg", "-v", "error", "-i", str(target), "-f", "null", "-"])
            return {
                "width": stream["width"], "height": stream["height"],
                "fps": rate, "duration": round(actual_duration, 3),
                "bytes": target.stat().st_size,
            }
    raise ValueError(f"{source.name}: cannot meet size limit; try a shorter --duration")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--paper", choices=PAPERS, action="append", help="Convert only this paper; can be repeated")
    parser.add_argument("--start", type=float, help="Excerpt start in seconds; default: selected action sequence")
    parser.add_argument("--duration", type=float, default=6)
    parser.add_argument("--width", type=int, default=480)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--max-mib", type=float, default=3)
    args = parser.parse_args()
    if not all(math.isfinite(x) and x > 0 for x in (args.duration, args.max_mib)):
        parser.error("duration and max-mib must be finite and positive")
    if not 64 <= args.width <= 1280 or not 1 <= args.fps <= 30:
        parser.error("width must be 64–1280 and fps must be 1–30")
    if args.start is not None and (not math.isfinite(args.start) or args.start < 0):
        parser.error("start must be finite and nonnegative")
    for executable in ("ffmpeg", "ffprobe"):
        if not shutil.which(executable):
            parser.error(f"{executable} is required")

    root = args.root.resolve()
    names = list(dict.fromkeys(args.paper or PAPERS))
    required = [root / "index.html"]
    required += [root / PAPERS[n][k] for n in names for k in ("source", "poster")]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Download the full repository first. Missing:\n  " + "\n  ".join(missing))

    page_path = root / "index.html"
    original_page = page_path.read_text(encoding="utf-8")
    page = original_page
    jobs = []
    for name in names:
        source = root / PAPERS[name]["source"]
        full_duration, stream = probe(source)
        start = args.start if args.start is not None else PAPERS[name]["start"]
        crop = PAPERS[name].get("crop")
        if crop:
            w, h, x, y = crop
            if x + w > stream["width"] or y + h > stream["height"]:
                raise ValueError(f"{name}: crop does not fit the source video")
        if start >= full_duration:
            raise ValueError(f"{name}: start {start}s is beyond duration {full_duration}s")
        duration = min(args.duration, full_duration - start)
        if duration * args.fps < 2:
            raise ValueError(f"{name}: choose an excerpt long enough for at least two frames")
        page = picture_markup(page, name, PAPERS[name]["poster"])
        jobs.append((name, source, start, duration, crop))

    # Publish HTML only after every requested GIF has been successfully encoded.
    target_dir = root / "images/paper-previews"
    target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".encoding-", dir=target_dir) as directory:
        temporary = Path(directory)
        for name, source, start, duration, crop in jobs:
            output = temporary / f"{name}.gif"
            result = encode(source, output, start, duration, args.width, args.fps, args.max_mib * 1024**2, crop)
            print(f"{name}: {source.stat().st_size / 1024**2:.2f} MiB -> "
                  f"{result['bytes'] / 1024**2:.2f} MiB, "
                  f"{result['width']}x{result['height']}, {result['fps']} fps, "
                  f"start {start:.2f}s, duration {result['duration']}s", flush=True)
        if page_path.read_text(encoding="utf-8") != original_page:
            raise RuntimeError("index.html changed during conversion; no page changes were applied")
        for name, *_ in jobs:
            (temporary / f"{name}.gif").replace(target_dir / f"{name}.gif")
        staged_page = temporary / "index.html"
        staged_page.write_text(page, encoding="utf-8")
        staged_page.replace(page_path)
    print("Animated covers are ready. Original media and reduced-motion posters are preserved.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
