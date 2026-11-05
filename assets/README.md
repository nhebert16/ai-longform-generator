# Assets (not included)

Media files are git-ignored: they're large and several are third-party content
that can't be redistributed. Add your own before running:

| Path | What it is |
|---|---|
| `background.mp4` | Looping gameplay / b-roll background (vertical 9:16 for Shorts, 16:9 for long-form) |
| `fonts/Montserrat-Bold.ttf`, `fonts/Montserrat-Regular.ttf` | [Montserrat](https://fonts.google.com/specimen/Montserrat) (OFL) |
| `fonts/Bangers-Regular.ttf` | [Bangers](https://fonts.google.com/specimen/Bangers) (OFL), the subtitle font |
| `music/*.mp3` | Royalty-free background tracks; one is picked per video. If empty, `music.py` synthesizes an ambient drone |
| `outro/outro_animated_final.mp4` | Branded end card. `python outro.py` generates one from `CHANNEL_NAME` |
| `snoo_avatar.png` | Avatar shown on the intro post card |
| `meta_icons/heart.png`, `meta_icons/comment.png` | Small UI icons for the post card |
| `award_icons_fixed/*.png` | Award badges shown on the post card |
| `sfx/pop-cut.mp3` | Short sound effect when the intro card appears |

`cards/` is created at runtime (rendered post-card frames).
