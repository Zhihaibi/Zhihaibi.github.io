# Personal website


Thanks to [psander](https://www.cse.ust.hk/~psander/), [jonbarron](https://github.com/jonbarron/jonbarron_website) and [Wenchao Ding](https://wenchaoding.github.io/personal/index.html).

The current layout is inspired by [Tairan He](https://tairanhe.com/).

## Animated publication covers

After downloading the complete repository, install Python 3 and FFmpeg
(including `ffprobe`), then run:

```bash
python3 scripts/make-paper-gifs.py
```

This creates GIF covers for the IJMS WSIM and ROBIO papers and a smaller version
of the Interactive Navigation animation. The default six-second excerpts show
WSIM locomotion (50–56 s), ROBIO pipe traversal (8–14 s), and Interactive
Navigation arm-pushing (40–46 s). The navigation cover crops to the experiment
panel. Covers use up to 480 pixels in width and 10 fps. The script
reduces the settings if needed to stay within 3 MiB per cover. Original images
and videos remain intact. The homepage uses the generated GIFs for visitors
without a reduced-motion preference, and the original still images otherwise.

Inspect the actual clips before publishing. To choose a specific excerpt:

```bash
python3 scripts/make-paper-gifs.py --paper wsim --start 12 --duration 6
```

Paper names are `wsim`, `robio`, and `interactive-nav`. The script validates all
required sources before conversion and updates `index.html` only after every
requested output succeeds. Run it again to regenerate covers; it does not add
duplicate HTML elements. Commit the generated files in `images/paper-previews/`
together with the updated homepage when publishing.
