"""
post_card.py — Single unified Reddit post card matching the reference.

Layout (top to bottom):
  [Snoo avatar]  <CHANNEL_NAME>
  [award] [award] [award] [award] [award] [award] [award] [award]
  BOLD WHITE ALL-CAPS TITLE TEXT
  ♡ 99+   ○ 99+                              ↑ Share

No checkmark. Awards fixed order, animated bounce.
render_post_card() returns:
  animated=True  → list of (path, start, duration) for video_builder
  animated=False → single path string
"""

import math, os, glob, shutil
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "Reddit Stories")

CARD_W  = 680
PAD     = 28
INNER_W = CARD_W - PAD * 2
SCALE   = 2

BOLD_FONT  = "assets/fonts/Montserrat-Bold.ttf"
REG_FONT   = "assets/fonts/Montserrat-Regular.ttf"
FALLBACK_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FALLBACK_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

SNOO_PATH    = Path("assets/snoo_avatar.png")
AWARD_DIR    = Path("assets/award_icons_fixed")
CARDS_DIR    = Path("assets/cards")
AVATAR_CACHE = CARDS_DIR / "snoo_circle.png"

AWARD_SIZE    = 58
ANIM_FRAMES   = 60   # 60 frames over 3.5s = ~17fps, smooth motion
ANIM_DURATION = 3.5
FRAME_DUR     = ANIM_DURATION / ANIM_FRAMES


def _font(bold, size):
    for i, path in enumerate([BOLD_FONT if bold else REG_FONT,
                               FALLBACK_B if bold else FALLBACK_R]):
        try:
            return ImageFont.truetype(path, size * SCALE)
        except Exception:
            if i == 0:
                print(f"  [PostCard] WARNING: {path} not found, using system fallback")
    return ImageFont.load_default()


def _wrap(text, font, max_w):
    words = text.split(); lines, cur = [], ""
    for word in words:
        test = f"{cur} {word}".strip()
        bb   = font.getbbox(test)
        if (bb[2]-bb[0]) > max_w and cur: lines.append(cur); cur = word
        else: cur = test
    if cur: lines.append(cur)
    return lines or [""]


def _rr(draw, xy, r, fill=None, outline=None, width=2):
    x0,y0,x1,y1 = xy
    if fill:
        draw.rectangle([x0+r,y0,x1-r,y1], fill=fill)
        draw.rectangle([x0,y0+r,x1,y1-r], fill=fill)
        for cx,cy in [(x0+r,y0+r),(x1-r,y0+r),(x0+r,y1-r),(x1-r,y1-r)]:
            draw.ellipse([cx-r,cy-r,cx+r,cy+r], fill=fill)
    if outline:
        for s,e,cx,cy in [(180,270,x0+r,y0+r),(270,0,x1-r,y0+r),
                          (90,180,x0+r,y1-r),(0,90,x1-r,y1-r)]:
            draw.arc([cx-r,cy-r,cx+r,cy+r],s,e,fill=outline,width=width)
        draw.line([x0+r,y0,x1-r,y0],fill=outline,width=width)
        draw.line([x0+r,y1,x1-r,y1],fill=outline,width=width)
        draw.line([x0,y0+r,x0,y1-r],fill=outline,width=width)
        draw.line([x1,y0+r,x1,y1-r],fill=outline,width=width)


def _get_snoo(size_px):
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    if AVATAR_CACHE.exists():
        return Image.open(AVATAR_CACHE).convert("RGBA").resize(
            (size_px, size_px), Image.LANCZOS)
    if not SNOO_PATH.exists():
        img = Image.new("RGBA",(size_px,size_px),(255,69,0,255))
        img.save(str(AVATAR_CACHE)); return img
    snoo = Image.open(str(SNOO_PATH)).convert("RGBA")
    sw,sh = snoo.size
    crop = snoo.crop((int(sw*.22), 0, int(sw*.78), int(sh*.52)))
    cw,ch = crop.size; side = max(cw,ch)
    sq = Image.new("RGBA",(side,side),(255,255,255,255))
    sq.paste(crop,((side-cw)//2,(side-ch)//2),crop)
    mask = Image.new("L",(side,side),0)
    ImageDraw.Draw(mask).ellipse([(0,0),(side-1,side-1)],fill=255)
    res = Image.new("RGBA",(side,side),(0,0,0,0))
    res.paste(sq,mask=mask)
    final = res.resize((size_px,size_px),Image.LANCZOS)
    final.save(str(AVATAR_CACHE))
    return final


def _load_awards(award_px):
    files = sorted(glob.glob(str(AWARD_DIR / "award_*.png")))
    if not files:
        print("  [!] No award icons found in", AWARD_DIR)
        return []
    return [Image.open(f).convert("RGBA").resize(
            (award_px, award_px), Image.LANCZOS) for f in files]


def _build_base(title_lines, line_h, font_name, font_title, font_meta,
                cw2, ch2, pad2, sp, AV_R, HEADER_H, AWARD_H,
                likes_str, cmts_str):
    """Static layers: background, snoo, username, title, meta."""
    card = Image.new("RGBA",(cw2,ch2),(0,0,0,0))
    d    = ImageDraw.Draw(card)

    # Dark rounded card — color matches award icon backgrounds
    _rr(d,(0,0,cw2-1,ch2-1),22*SCALE,fill=(26,30,33,255))
    _rr(d,(0,0,cw2-1,ch2-1),22*SCALE,outline=(55,55,55,255),width=3)

    # Avatar
    acx=pad2+AV_R; acy=pad2+AV_R
    av = _get_snoo(AV_R*2)
    ring_r = AV_R+5*SCALE
    ring = Image.new("RGBA",(ring_r*2,ring_r*2),(0,0,0,0))
    ImageDraw.Draw(ring).ellipse([(0,0),(ring_r*2-1,ring_r*2-1)],fill=(255,255,255,255))
    card.paste(ring,(acx-ring_r,acy-ring_r),ring)
    card.paste(av,  (acx-AV_R, acy-AV_R),  av)

    # Username — vertically centered next to avatar, no checkmark
    tx = acx + AV_R + 18*SCALE
    name_h = font_name.getbbox(CHANNEL_NAME)[3] - font_name.getbbox(CHANNEL_NAME)[1]
    ty = acy - name_h//2
    d.text((tx,ty),CHANNEL_NAME,font=font_name,fill=(255,255,255,255))

    # Title
    ty2 = pad2 + HEADER_H + sp + AWARD_H + sp
    for line in title_lines:
        d.text((pad2,ty2),line,font=font_title,fill=(255,255,255,255))
        ty2 += line_h

    # Divider
    div_y = ty2 + sp//2
    d.line([(pad2,div_y),(cw2-pad2,div_y)], fill=(60,60,60,255), width=2)

    # Meta row — heart icon + likes, comment icon + count, share text
    ICON_PX  = 38 * SCALE
    meta_y   = div_y + 14*SCALE
    cursor_x = pad2

    def load_icon(name):
        p = Path(f"assets/meta_icons/{name}.png")
        if not p.exists(): return None
        ic = Image.open(str(p)).convert("RGBA")
        # Tint to grey to match reference
        arr = np.array(ic, dtype=np.float32)
        arr[:,:,0] = 180; arr[:,:,1] = 180; arr[:,:,2] = 180
        tinted = Image.fromarray(arr.astype(np.uint8), "RGBA")
        return tinted.resize((ICON_PX, ICON_PX), Image.LANCZOS)

    heart_icon   = load_icon("heart")
    comment_icon = load_icon("comment")

    icon_col = (180,180,180,255)

    # Heart + likes
    if heart_icon:
        iy = meta_y + (font_meta.getbbox("0")[3] - ICON_PX) // 2
        card.paste(heart_icon, (cursor_x, iy), heart_icon)
        cursor_x += ICON_PX + 8*SCALE
    d.text((cursor_x, meta_y), likes_str, font=font_meta, fill=icon_col)
    cursor_x += font_meta.getbbox(likes_str)[2] - font_meta.getbbox(likes_str)[0] + 28*SCALE

    # Comment bubble + count
    if comment_icon:
        iy = meta_y + (font_meta.getbbox("0")[3] - ICON_PX) // 2
        card.paste(comment_icon, (cursor_x, iy), comment_icon)
        cursor_x += ICON_PX + 8*SCALE
    d.text((cursor_x, meta_y), cmts_str, font=font_meta, fill=icon_col)

    # Share — right aligned
    share_str = "↑ Share"
    share_w   = font_meta.getbbox(share_str)[2] - font_meta.getbbox(share_str)[0]
    d.text((cw2-pad2-share_w, meta_y), share_str, font=font_meta, fill=icon_col)

    return card


def render_post_card(
    job_id: int,
    title: str,
    subreddit: str = "r/AITA",
    upvotes: str = "",
    comments: str = "",
    time_ago: str = None,
    animated: bool = True,
    duration: float = None,
):
    import random
    CARDS_DIR.mkdir(parents=True, exist_ok=True)

    rng = random.Random(job_id + 42)
    likes_str = f"{rng.randint(80,999)}+"
    cmts_str  = f"{rng.randint(80,999)}+"

    font_name  = _font(True,  30)
    font_title = _font(True,  48)
    font_meta  = _font(False, 32)   # bigger — was 22, too small

    cw2  = CARD_W * SCALE
    pad2 = PAD    * SCALE
    iw2  = cw2 - pad2*2
    sp   = 14 * SCALE
    AV_R = 52 * SCALE
    AW_PX = AWARD_SIZE * SCALE

    HEADER_H = AV_R * 2
    AWARD_H  = AW_PX + sp
    META_H   = 60 * SCALE

    title_lines = _wrap(title.upper(), font_title, iw2)
    bb      = font_title.getbbox("Ag")
    line_h  = max(bb[3]-bb[1]+10*SCALE, 48*SCALE)  # minimum guard in case font fallback is tiny
    title_h = len(title_lines)*line_h

    ch2 = pad2 + HEADER_H + sp + AWARD_H + sp + title_h + sp + META_H + pad2

    award_imgs = _load_awards(AW_PX)
    base = _build_base(title_lines, line_h, font_name, font_title, font_meta,
                       cw2, ch2, pad2, sp, AV_R, HEADER_H, AWARD_H,
                       likes_str, cmts_str)

    # Use dynamic duration if provided, otherwise fall back to ANIM_DURATION
    anim_duration = duration if duration is not None else ANIM_DURATION
    frame_dur     = anim_duration / ANIM_FRAMES

    final_h = ch2 // SCALE
    gap     = 6 * SCALE
    aw_y    = pad2 + HEADER_H + sp

    def paste_awards(frame, fi):
        if not award_imgs: return frame
        for i, aimg in enumerate(award_imgs):
            phase   = (fi/ANIM_FRAMES)*math.pi*2 + i*(math.pi*2/len(award_imgs))
            bob     = int(math.sin(phase) * 2*SCALE)
            scale_f = 1.0 + 0.03*math.sin(phase+math.pi/3)
            new_sz  = int(AW_PX*scale_f)
            resized = aimg.resize((new_sz,new_sz),Image.LANCZOS)
            ax = pad2 + i*(AW_PX+gap) + (AW_PX-new_sz)//2
            ay = aw_y + bob            + (AW_PX-new_sz)//2
            frame.paste(resized,(ax,ay),resized)
        return frame

    if not animated:
        out = CARDS_DIR / f"card_{job_id}.png"
        if out.exists(): return str(out)
        frame = base.copy()
        paste_awards(frame, 0)
        frame.resize((CARD_W,final_h),Image.LANCZOS).save(str(out))
        print(f"  [PostCard] {out}  ({CARD_W}x{final_h})")
        return str(out)

    frame_dir = CARDS_DIR / f"frames_{job_id}"
    # Always clear and regenerate — never serve stale frames from a previous run
    if frame_dir.exists():
        shutil.rmtree(str(frame_dir))
    frame_dir.mkdir(exist_ok=True)

    print(f"  [PostCard] Rendering {ANIM_FRAMES} frames...")
    paths = []
    for fi in range(ANIM_FRAMES):
        frame = base.copy()
        paste_awards(frame, fi)
        out = frame_dir / f"frame_{fi:03d}.png"
        frame.resize((CARD_W,final_h),Image.LANCZOS).save(str(out))
        paths.append(str(out))
    print(f"  [PostCard] Done: {CARD_W}x{final_h}")
    return [(p,i*frame_dur,frame_dur) for i,p in enumerate(paths)]


def extract_awards_from_strip(strip_path, out_dir="assets/award_icons_fixed"):
    import numpy as np
    os.makedirs(out_dir, exist_ok=True)
    ref = Image.open(strip_path).convert("RGBA")
    w,h = ref.size; arr = np.array(ref)
    bg = arr[2,2,:3].astype(int); tol=18
    is_c = ~((np.abs(arr[:,:,0].astype(int)-bg[0])<tol)&
             (np.abs(arr[:,:,1].astype(int)-bg[1])<tol)&
             (np.abs(arr[:,:,2].astype(int)-bg[2])<tol))
    col_p=is_c.any(axis=0); bands=[]; in_b=False; start=0; gap=0
    for i,v in enumerate(col_p):
        if not in_b:
            if v: in_b=True; start=i; gap=0
        else:
            if not v:
                gap+=1
                if gap>=8: bands.append((start,i-gap)); in_b=False; gap=0
            else: gap=0
    if in_b: bands.append((start,len(col_p)-1))
    PAD=4
    for i,(x0,x1) in enumerate(bands):
        rows=np.where(is_c[:,x0:x1+1].any(axis=1))[0]
        if not len(rows): continue
        y0,y1=rows[0],rows[-1]
        crop=ref.crop((max(0,x0-PAD),max(0,y0-PAD),min(w,x1+PAD+1),min(h,y1+PAD+1)))
        cw2,ch2=crop.size; side=max(cw2,ch2)
        sq=Image.new("RGBA",(side,side),(0,0,0,0))
        sq.paste(crop,((side-cw2)//2,(side-ch2)//2))
        sq.resize((80,80),Image.LANCZOS).save(f"{out_dir}/award_{i:02d}.png")
    print(f"Extracted {len(bands)} awards to {out_dir}/")


if __name__ == "__main__":
    import sys
    if "--extract" in sys.argv:
        idx=sys.argv.index("--extract")
        strip=sys.argv[idx+1] if idx+1<len(sys.argv) else None
        if strip: extract_awards_from_strip(strip)
    else:
        os.makedirs("assets/cards",exist_ok=True)
        for p in ["assets/cards/snoo_circle.png","assets/cards/card_0.png"]:
            if os.path.exists(p): os.remove(p)
        fd=Path("assets/cards/frames_0")
        if fd.exists(): shutil.rmtree(str(fd))
        r = render_post_card(job_id=0,
            title='My stepmom said "You\'re not invited to family events anymore," so I stopped inviting her to mine.',
            animated=False)
        print(f"Saved: {r}")
