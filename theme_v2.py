"""Design v2, "The Daily Capsule": page templates for the Daily Dose of DS site.

build_site.py still does everything else (fetching, Gemini, the database,
infographics). This file only decides how the pages look. A single 3D capsule
is drawn in code with Three.js behind a scroll-driven landing page; chapter
pages and the e-book share the same colours and type but stay light for reading.

Libraries load from a CDN with pinned versions, so GitHub Pages needs no build.
Set DDS_DESIGN=v1 to build the previous design instead.
"""

import json
import re
from datetime import datetime
from pathlib import Path

GSAP = "https://cdn.jsdelivr.net/npm/gsap@3.13.0/dist"
LENIS = "https://cdn.jsdelivr.net/npm/lenis@1.1.13/dist"
THREE = "https://cdn.jsdelivr.net/npm/three@0.169.0"
REPO = "https://github.com/Rishichamp/daily-dose-site"

# The pipeline, step by step, for the spec-sheet section.
PIPELINE = [
    ("Fetch", "Twice a day the workflow reads the newsletter's public archive. "
              "It re-checks the last 10 days, so a post that failed once is picked up later."),
    ("Clean", "Tracking links, ads and footers are stripped. Only the teaching content is kept."),
    ("Rewrite", "Gemini turns the issue into a chapter: TL;DR, sections, code, key takeaways "
                "and interview questions. If the model is down, a plain summary is used instead."),
    ("Sort", "Each chapter gets a topic from its title and text, and a number from its date."),
    ("Draw", "A one-page infographic is rendered for every chapter, ready to share."),
    ("Build", "Static pages are written: this roadmap, one page per chapter and the full e-book."),
    ("Ship", "The new pages and the database are committed, and GitHub Pages redeploys the site."),
]


def _attr(t) -> str:
    return (str(t).replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = r"""
:root{
  --ink:#0A0F0D;--ink-2:#111915;--ink-3:#1A241E;--cream:#E9F2EA;--mute:#8C9C91;
  --lime:#C6F432;--paper:#E4ECE1;
  --bg:var(--ink);--fg:var(--cream);--fg-2:var(--mute);--line:rgba(233,242,234,.14);--card:rgba(17,25,21,.72);
  --su:calc(min(100vw,1920px) / 1440);
  --pad:calc(var(--su) * 56);
  --f-head:'Manrope',system-ui,sans-serif;--f-body:'Inter',system-ui,sans-serif;--f-mono:'DM Mono',ui-monospace,monospace;
  --ease:cubic-bezier(.65,0,.35,1);--out:cubic-bezier(.16,1,.3,1);
}
@media (max-width:767px){:root{--su:calc(100vw / 375);--pad:18px}}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%;overflow-x:clip}
body{background:var(--bg);color:var(--fg);font-family:var(--f-body);font-size:clamp(15px,calc(var(--su)*17),18px);line-height:1.6;
  -webkit-font-smoothing:antialiased;transition:background-color .7s var(--ease),color .7s var(--ease);overflow-x:clip}
body.is-light{--bg:var(--paper);--fg:var(--ink);--fg-2:#4D5D53;--line:rgba(10,15,13,.18);--card:rgba(255,255,255,.55)}
a{color:inherit}
img{max-width:100%;display:block}
button{font:inherit;color:inherit;background:none;border:0;cursor:pointer}
::selection{background:var(--lime);color:var(--ink)}
:focus-visible{outline:2px solid var(--lime);outline-offset:3px;border-radius:4px}
@view-transition{navigation:auto}

/* code-made film grain for a tactile feel */
.grain{position:fixed;inset:0;pointer-events:none;z-index:60;opacity:.07;mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
#gl{position:fixed;inset:0;width:100vw;height:100vh;z-index:0;pointer-events:none}
main,.site-foot,.page{position:relative;z-index:1}
.wrap{width:100%;max-width:1680px;margin:0 auto;padding:0 var(--pad)}

/* type */
.mono{font-family:var(--f-mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase}
.label{font-family:var(--f-mono);font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--fg-2);display:inline-flex;gap:10px;align-items:center}
.label::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--lime)}
.h-xl{font-family:var(--f-head);font-weight:800;font-size:calc(var(--su)*96);line-height:.98;letter-spacing:-.035em}
.h-lg{font-family:var(--f-head);font-weight:800;font-size:calc(var(--su)*72);line-height:1;letter-spacing:-.03em}
.h-md{font-family:var(--f-head);font-weight:700;font-size:clamp(22px,calc(var(--su)*34),40px);line-height:1.1;letter-spacing:-.02em}
@media (max-width:767px){.h-xl{font-size:calc(var(--su)*48)}.h-lg{font-size:calc(var(--su)*40)}}
.lede{color:var(--fg-2);max-width:52ch;font-size:clamp(16px,calc(var(--su)*19),21px)}
.accent{color:var(--lime)}
body.is-light .accent{color:#4C6B00}
.sec-head{display:grid;gap:18px;margin-bottom:calc(var(--su)*56)}

/* letter-roll hover */
.roll{display:inline-flex;white-space:nowrap}
.roll .ch{display:inline-block;overflow:hidden;height:1.15em;line-height:1.15em;vertical-align:top}
.roll .ch>span{display:block;transition:transform .45s var(--out);transition-delay:calc(var(--i) * 16ms)}
a:hover .roll .ch>span,button:hover .roll .ch>span,.roll:hover .ch>span{transform:translateY(-100%)}

/* buttons */
.pill{display:inline-flex;align-items:center;gap:10px;height:48px;padding:0 22px;border-radius:999px;font-weight:600;font-size:15px;
  text-decoration:none;background:var(--ink-3);color:var(--cream);border:1px solid var(--line);transition:background .18s,color .18s,box-shadow .3s,border-color .18s}
.pill:hover{box-shadow:0 0 0 1px var(--lime),0 0 28px rgba(198,244,50,.35)}
.pill-lime{background:var(--lime);color:var(--ink);border-color:var(--lime)}
.pill-lime:hover{background:var(--cream);border-color:var(--cream);box-shadow:0 0 36px rgba(198,244,50,.45)}
.pill-ghost{background:transparent;color:var(--fg)}
.pill.sm{height:38px;padding:0 16px;font-size:13.5px}
.pill.on{background:var(--lime);color:var(--ink);border-color:var(--lime)}

/* nav */
.nav{position:fixed;top:0;left:0;right:0;z-index:50;transition:background .3s,backdrop-filter .3s}
.nav.scrolled{background:color-mix(in srgb,var(--bg) 72%,transparent);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
.nav-in{display:flex;align-items:center;justify-content:space-between;height:68px;max-width:1680px;margin:0 auto;padding:0 var(--pad)}
.nav-logo{display:inline-flex;align-items:center;gap:10px;text-decoration:none;font-family:var(--f-head);font-weight:800;letter-spacing:-.02em;font-size:18px;transition:opacity .3s}
.nav-logo svg{width:26px;height:26px;flex:none}
.motion .home:not(.logo-docked) .nav-logo{opacity:0;pointer-events:none}
.nav-links{display:flex;gap:4px;align-items:center}
.nav-links a{font-size:14px;font-weight:500;text-decoration:none;padding:8px 12px;border-radius:999px;transition:opacity .25s}
.nav-links:hover a{opacity:.45}
.nav-links a:hover{opacity:1}
.nav-right{display:flex;gap:10px;align-items:center}
.burger{display:none;width:44px;height:44px;border-radius:50%;border:1px solid var(--line);position:relative}
.burger i{position:absolute;left:13px;right:13px;height:1.5px;background:currentColor;transition:transform .35s var(--out),top .35s var(--out)}
.burger i:nth-child(1){top:17px}.burger i:nth-child(2){top:25px}
.menu-open .burger i:nth-child(1){top:21px;transform:rotate(45deg)}
.menu-open .burger i:nth-child(2){top:21px;transform:rotate(-45deg)}
.menu{position:fixed;inset:0;z-index:45;background:var(--ink);display:flex;flex-direction:column;justify-content:center;gap:6px;padding:90px var(--pad) 40px;
  clip-path:inset(0 0 100% 0);transition:clip-path .6s var(--ease);color:var(--cream)}
.menu-open .menu{clip-path:inset(0 0 0 0)}
.menu a{font-family:var(--f-head);font-weight:800;font-size:40px;letter-spacing:-.03em;text-decoration:none;line-height:1.15}
.menu .mono{margin-top:28px;color:var(--mute)}
@media (max-width:900px){.nav-links{display:none}.burger{display:block}.nav-cta{display:none}}

/* side scroll indicator */
.scroll-ind{position:fixed;right:10px;top:50%;height:120px;width:2px;margin-top:-60px;background:var(--line);z-index:40;border-radius:2px;overflow:hidden}
.scroll-ind i{position:absolute;inset:0;background:var(--lime);transform-origin:top;transform:scaleY(0)}
@media (max-width:767px){.scroll-ind{display:none}}

/* loader */
#loader{position:fixed;inset:0;z-index:100;background:var(--ink);color:var(--cream);display:none;place-items:center;
  transition:clip-path 1s var(--ease);clip-path:inset(0 0 0 0)}
.js #loader{display:grid;animation:ldFailsafe 0s 7s forwards}
#loader.done{clip-path:inset(0 0 100% 0)}
@keyframes ldFailsafe{to{visibility:hidden}}
#loader svg{width:min(78vw,520px);height:auto;overflow:visible}
#loader .ld-guide{stroke:rgba(233,242,234,.22);stroke-dasharray:4 6;fill:none}
#loader .ld-draw{stroke:var(--lime);fill:none;stroke-width:2;stroke-dasharray:1;stroke-dashoffset:1}
#loader .ld-handle{fill:var(--ink);stroke:var(--lime);stroke-width:1.5}
#loader .ld-txt{font-family:var(--f-mono);font-size:11px;fill:var(--mute);letter-spacing:.12em}
.ld-pct{position:absolute;left:var(--pad);bottom:28px;font-family:var(--f-head);font-weight:800;font-size:calc(var(--su)*120);line-height:.8;letter-spacing:-.04em}
.ld-note{position:absolute;right:var(--pad);bottom:32px;color:var(--mute)}
.is-loading body{overflow:hidden}

/* hero */
.hero{position:relative;height:100vh;min-height:560px}
.hero-in{position:relative;height:100%;display:flex;flex-direction:column;justify-content:flex-end;padding-bottom:calc(var(--su)*48)}
#heroLogo{position:absolute;left:var(--pad);top:calc(68px + var(--su)*40);font-family:var(--f-head);font-weight:800;line-height:.82;letter-spacing:-.055em;
  font-size:calc(var(--su)*190);transform-origin:0 0;will-change:transform;transition:opacity .25s}
#heroLogo .sub{display:block;font-size:.27em;letter-spacing:-.02em;color:var(--fg-2);margin-top:.18em;line-height:1}
.logo-docked #heroLogo{opacity:0}
.hero-copy{display:grid;gap:22px;max-width:600px}
.hero-btns{display:flex;flex-wrap:wrap;gap:10px}
.hero-stats{position:absolute;right:var(--pad);bottom:calc(var(--su)*48);display:flex;gap:calc(var(--su)*40);text-align:right}
.hero-stats b{display:block;font-family:var(--f-head);font-weight:800;font-size:calc(var(--su)*44);letter-spacing:-.03em;line-height:1}
.hero-stats span{color:var(--fg-2)}
.scroll-cue{position:absolute;left:50%;bottom:18px;transform:translateX(-50%);color:var(--fg-2);display:flex;flex-direction:column;align-items:center;gap:8px}
.scroll-cue i{width:1px;height:34px;background:linear-gradient(var(--lime),transparent);animation:cue 1.8s var(--ease) infinite}
@keyframes cue{0%{transform:scaleY(0);transform-origin:top}50%{transform:scaleY(1);transform-origin:top}51%{transform-origin:bottom}100%{transform:scaleY(0);transform-origin:bottom}}
.cap-fallback{display:none}
html:not(.gl-on) .cap-fallback{display:block;position:absolute;right:calc(var(--pad) + 4vw);top:22%;width:clamp(120px,16vw,240px);aspect-ratio:1/2.3;border-radius:999px;transform:rotate(32deg);
  background:linear-gradient(180deg,var(--lime) 0 50%,var(--cream) 50% 100%);box-shadow:inset -18px -10px 40px rgba(0,0,0,.35),0 0 80px rgba(198,244,50,.25)}
@media (max-width:767px){
  #heroLogo{font-size:calc(var(--su)*96);top:92px}
  .hero-in{padding-bottom:90px}
  .hero-stats{position:static;justify-content:flex-start;text-align:left;margin-top:26px;gap:26px}
  .hero-stats b{font-size:28px}
  html:not(.gl-on) .cap-fallback{top:auto;bottom:52%;right:12%;width:90px}
}

/* edge glow (AI moment) */
.edge-glow{position:fixed;inset:0;z-index:30;pointer-events:none;opacity:0;padding:14px;
  -webkit-mask:linear-gradient(#000 0 0) content-box exclude,linear-gradient(#000 0 0);mask:linear-gradient(#000 0 0) content-box exclude,linear-gradient(#000 0 0)}
.edge-glow::before{content:"";position:absolute;inset:-50%;background:conic-gradient(from var(--a,0deg),#C6F432,#2FE6B0,#E9F2EA,#7DFF6A,#C6F432);filter:blur(22px);animation:spin 6s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* pitch: "Isn't just a newsletter." */
.pitch{min-height:100vh;display:flex;align-items:center}
.pitch .wrap{display:grid;gap:calc(var(--su)*40)}
#pitchText{font-family:var(--f-head);font-weight:800;font-size:calc(var(--su)*120);line-height:.95;letter-spacing:-.045em;max-width:9.5em}
#pitchAi{font-family:var(--f-head);font-weight:800;font-size:calc(var(--su)*64);line-height:1;letter-spacing:-.03em}
#pitchAi sup{font-size:.45em;color:var(--lime);vertical-align:.9em}
.footnote{color:var(--fg-2);max-width:46ch}
@media (max-width:767px){#pitchText{font-size:calc(var(--su)*56)}#pitchAi{font-size:calc(var(--su)*36)}}

/* daily: giant word through a frame, then a gallery */
.daily{position:relative;padding:calc(var(--su)*80) 0}
.daily-word{font-family:var(--f-head);font-weight:800;font-size:calc(var(--su)*96);letter-spacing:-.045em;line-height:1;padding:0 var(--pad);margin-bottom:40px}
.daily-word em{font-style:normal;color:var(--lime)}
.daily-frame{display:none}
.daily-track{display:flex;gap:22px;overflow-x:auto;padding:10px var(--pad) 26px;scroll-snap-type:x mandatory}
.motion .daily{height:100vh;padding:0;overflow:hidden}
.motion .daily-word{position:absolute;top:50%;left:0;white-space:nowrap;font-size:calc(var(--su)*300);line-height:1;padding:0;margin:-.5em 0 0}
.motion .daily-frame{display:block;position:absolute;left:50%;top:50%;width:var(--cw);height:var(--chh);transform:translate(-50%,-50%);border:1.5px dashed var(--fg-2);z-index:2;pointer-events:none}
.motion .daily-track{position:absolute;left:0;top:50%;margin-top:calc(var(--chh) / -2);width:max-content;overflow:visible;padding:0 calc((100vw - var(--cw)) / 2);scroll-snap-type:none}
.daily{--cw:min(420px,78vw);--chh:clamp(300px,46vh,380px)}
.frame-tag{position:absolute;top:-26px;left:0;color:var(--fg-2)}
.frame-dim{position:absolute;bottom:-26px;right:0;color:var(--fg-2)}
.daily-frame b{position:absolute;width:9px;height:9px;border:1.5px solid var(--lime);background:var(--bg)}
.daily-frame b:nth-of-type(1){left:-5px;top:-5px}.daily-frame b:nth-of-type(2){right:-5px;top:-5px}
.daily-frame b:nth-of-type(3){left:-5px;bottom:-5px}.daily-frame b:nth-of-type(4){right:-5px;bottom:-5px}
.dcard{flex:none;width:var(--cw);height:var(--chh);scroll-snap-align:center;border-radius:22px;background:var(--ink-2);border:1px solid var(--line);
  padding:26px;display:flex;flex-direction:column;justify-content:space-between;text-decoration:none;position:relative;overflow:hidden;transition:border-color .3s,transform .5s var(--out)}
.dcard::after{content:"";position:absolute;inset:auto -30% -60% -30%;height:70%;background:radial-gradient(closest-side,rgba(198,244,50,.18),transparent);opacity:0;transition:opacity .4s}
.dcard:hover{border-color:var(--lime)}
.dcard:hover::after{opacity:1}
.dcard-top{display:flex;justify-content:space-between;color:var(--mute)}
.dcard-num{font-family:var(--f-head);font-weight:800;font-size:72px;line-height:.9;letter-spacing:-.05em;color:var(--lime)}
.dcard h3{font-family:var(--f-head);font-weight:700;font-size:23px;line-height:1.15;letter-spacing:-.02em;color:var(--cream)}
.dcard-go{display:flex;justify-content:space-between;align-items:center;color:var(--mute)}
.dcard-go span:last-child{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;background:var(--lime);color:var(--ink);font-size:18px}
.dcard.end{background:var(--lime);color:var(--ink);border-color:var(--lime);justify-content:flex-end}
.dcard.end h3{color:var(--ink);font-size:40px}

/* how it runs: blueprint spec sheet */
.how{padding:calc(var(--su)*140) 0}
.how-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:calc(var(--su)*60)}
.how-steps{position:relative;display:grid;gap:14px;padding-left:34px}
.how-line{position:absolute;left:8px;top:8px;bottom:8px;width:1px;border-left:1px dashed var(--line)}
.how-line i{position:absolute;left:-1px;top:0;bottom:0;width:2px;background:var(--lime);transform-origin:top;transform:scaleY(0)}
.motion-none .how-line i{transform:none}
.step{position:relative;padding:20px 22px;border:1px dashed var(--line);border-radius:4px;background:var(--card);transition:border-color .5s,opacity .5s}
.step::before{content:"";position:absolute;left:-31px;top:24px;width:11px;height:11px;border-radius:50%;border:1.5px solid var(--fg-2);background:var(--bg);transition:background .4s,border-color .4s}
.step.on{border-color:rgba(198,244,50,.55)}
.step.on::before{background:var(--lime);border-color:var(--lime)}
.motion .step{opacity:.35}
.motion .step.on{opacity:1}
.step .mono{color:var(--lime)}
.step h3{font-family:var(--f-head);font-weight:700;font-size:22px;letter-spacing:-.02em;margin:4px 0 6px}
.step p{color:var(--fg-2);font-size:15px}
.step i.c{position:absolute;width:8px;height:8px;border-color:var(--fg-2);border-style:solid;border-width:0}
.step i.c1{left:-1px;top:-1px;border-left-width:1.5px;border-top-width:1.5px}
.step i.c2{right:-1px;bottom:-1px;border-right-width:1.5px;border-bottom-width:1.5px}
.xray-col{position:relative}
.xray-sticky{position:sticky;top:18vh;height:64vh}
.callout{position:absolute;display:flex;align-items:center;gap:10px;color:var(--fg-2);white-space:nowrap}
.callout::before{content:"";width:60px;border-top:1px dashed var(--lime)}
.callout b{color:var(--lime);font-weight:500}
.callout.c-a{top:8%;left:2%}.callout.c-b{top:46%;right:0;flex-direction:row-reverse}.callout.c-c{bottom:8%;left:8%}
.xray-ruler{position:absolute;left:0;right:0;bottom:-8px;border-top:1px solid var(--line);display:flex;justify-content:space-between;color:var(--fg-2);padding-top:8px}
@media (max-width:900px){.how-grid{grid-template-columns:1fr}.xray-col{display:none}}

/* tutor decode box */
.decode{padding:calc(var(--su)*120) 0}
.decode-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.1fr);gap:calc(var(--su)*60);align-items:center}
.decode-box{border:1px solid var(--line);border-radius:18px;background:var(--ink-2);overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,.35)}
.decode-bar{display:flex;justify-content:space-between;align-items:center;padding:14px 18px;border-bottom:1px solid var(--line);color:var(--mute)}
.decode-bar span:first-child::before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--lime);margin-right:10px;box-shadow:0 0 12px var(--lime)}
.decode-screen{padding:26px 22px;font-family:var(--f-mono);font-size:15px;color:var(--cream);min-height:150px;line-height:1.7}
.decode-screen .dim{color:var(--mute)}
.decode-form{display:flex;gap:10px;padding:16px;border-top:1px solid var(--line)}
.decode-form input{flex:1;min-width:0;height:48px;border-radius:999px;border:1px solid var(--line);background:var(--ink);color:var(--cream);padding:0 18px;font-family:var(--f-mono);font-size:14px}
.decode-form input:focus{outline:none;border-color:var(--lime)}
@media (max-width:900px){.decode-grid{grid-template-columns:1fr}}

/* topics under the microscope */
.topics{padding:calc(var(--su)*120) 0}
.topics-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:calc(var(--su)*60);align-items:center}
.lens{position:relative;width:min(100%,460px);aspect-ratio:1;margin:0 auto;border-radius:50%;border:1px solid var(--line)}
.lens svg{position:absolute;inset:0;width:100%;height:100%}
.lens .tick{stroke:var(--fg-2)}
.lens-read{position:absolute;left:50%;bottom:-6px;transform:translate(-50%,100%);text-align:center;color:var(--fg-2)}
.readout{display:grid;border-top:1px solid var(--line)}
.rd{display:grid;grid-template-columns:1fr auto;gap:6px 16px;padding:16px 4px;border-bottom:1px solid var(--line);text-align:left;width:100%;transition:padding .3s var(--out)}
.rd:hover{padding-left:12px}
.rd:hover .rd-name{color:var(--lime)}
.rd-name{font-family:var(--f-head);font-weight:700;font-size:19px;letter-spacing:-.01em;transition:color .2s}
.rd-n{font-family:var(--f-mono);color:var(--fg-2)}
.rd-bar{grid-column:1/-1;height:3px;background:var(--line);border-radius:3px;overflow:hidden}
.rd-bar i{display:block;height:100%;width:var(--w);background:var(--lime);transform-origin:left;transform:scaleX(0);transition:transform 1.2s var(--out)}
.readout.on .rd-bar i,.motion-none .rd-bar i{transform:scaleX(1)}
@media (max-width:900px){.topics-grid{grid-template-columns:1fr}.lens{width:min(70vw,320px)}}

/* consistency (light section) */
.steady{min-height:100vh;display:flex;flex-direction:column;justify-content:center;padding:calc(var(--su)*100) 0;position:relative;overflow:hidden}
.steady::before{content:"";position:absolute;inset:0;pointer-events:none;opacity:.5;
  background:repeating-linear-gradient(115deg,transparent 0 46px,rgba(10,15,13,.035) 46px 92px),radial-gradient(60% 50% at 70% 30%,rgba(198,244,50,.18),transparent 70%)}
#steadyWord{font-family:var(--f-head);font-weight:800;font-size:calc(var(--su)*230);letter-spacing:-.06em;line-height:.9;text-align:center;position:relative}
.steady .label{justify-content:center;width:100%;margin-bottom:18px}
.steady-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin-top:calc(var(--su)*70);position:relative}
.sc{border-radius:22px;padding:26px;background:var(--card);border:1px solid var(--line);display:grid;gap:10px;align-content:start}
.sc b{font-family:var(--f-head);font-weight:800;font-size:calc(var(--su)*64);line-height:1;letter-spacing:-.04em}
.sc:nth-child(2){background:var(--ink);color:var(--cream);border-color:var(--ink)}
.sc:nth-child(3){background:var(--lime);color:var(--ink);border-color:var(--lime)}
.sc p{color:inherit;opacity:.75;font-size:15px}
@media (max-width:767px){#steadyWord{font-size:calc(var(--su)*76)}.steady-cards{grid-template-columns:1fr}.sc b{font-size:44px}}

/* roadmap */
.roadmap{padding:calc(var(--su)*140) 0 calc(var(--su)*100)}
.rm-tools{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px}
.rm-search{position:relative;flex:1 1 280px;max-width:420px}
.rm-search input{width:100%;height:48px;border-radius:999px;border:1px solid var(--line);background:var(--ink-2);color:var(--cream);padding:0 52px 0 20px;font-size:15px}
.rm-search input:focus{outline:none;border-color:var(--lime)}
.rm-search kbd{position:absolute;right:12px;top:12px;font-family:var(--f-mono);font-size:12px;border:1px solid var(--line);border-radius:6px;padding:2px 8px;color:var(--mute)}
.rm-pills{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px}
.rm-count{min-height:20px;color:var(--fg-2);margin-bottom:10px}
.wk{border-top:1px solid var(--line)}
.wk:last-child{border-bottom:1px solid var(--line)}
.wk-head{display:flex;align-items:center;gap:16px;width:100%;padding:20px 4px;text-align:left}
.wk-head .mono{color:var(--fg-2);min-width:180px}
.wk-title{font-family:var(--f-head);font-weight:700;font-size:clamp(18px,calc(var(--su)*24),26px);letter-spacing:-.02em;flex:1}
.wk-n{color:var(--fg-2)}
.wk-ico{width:30px;height:30px;border-radius:50%;border:1px solid var(--line);position:relative;flex:none;transition:background .3s,border-color .3s}
.wk-ico::before,.wk-ico::after{content:"";position:absolute;left:8px;right:8px;top:14px;height:1.5px;background:currentColor;transition:transform .35s var(--out)}
.wk-ico::after{transform:rotate(90deg)}
.wk-head.open .wk-ico{background:var(--lime);border-color:var(--lime);color:var(--ink)}
.wk-head.open .wk-ico::after{transform:rotate(0)}
.wk-panel{display:grid;grid-template-rows:0fr;transition:grid-template-rows .55s var(--ease)}
.wk-panel.open{grid-template-rows:1fr}
.wk-panel>div{overflow:hidden}
.row{display:grid;grid-template-columns:70px minmax(0,1fr) auto auto 44px;gap:18px;align-items:center;padding:14px 16px;margin:0 0 6px;border-radius:12px;
  text-decoration:none;position:relative;isolation:isolate;transition:color .25s}
.row::before{content:"";position:absolute;inset:0;border-radius:12px;background:var(--lime);z-index:-1;transform:scaleX(0);transform-origin:left;transition:transform .45s var(--out)}
.row:hover{color:var(--ink)}
.row:hover::before{transform:scaleX(1)}
.row:hover .row-cat,.row:hover .row-date,.row:hover .row-num{color:var(--ink)}
.row-num{font-family:var(--f-mono);color:var(--lime);font-size:14px}
.row-title{font-weight:600;font-size:16.5px;line-height:1.3}
.row-cat{font-family:var(--f-mono);font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--fg-2);white-space:nowrap}
.row-date{font-family:var(--f-mono);font-size:12px;color:var(--fg-2);white-space:nowrap}
.row-read{font-family:var(--f-mono);font-size:11px;color:var(--lime);margin-left:8px}
.row:hover .row-read{color:var(--ink)}
.bm{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;font-size:17px;color:var(--fg-2);transition:background .2s,color .2s}
.bm:hover{background:rgba(10,15,13,.12)}
.bm.on{color:var(--lime)}
.row:hover .bm,.row:hover .bm.on{color:var(--ink)}
@media (max-width:767px){
  .row{grid-template-columns:52px minmax(0,1fr) 40px;gap:6px 10px}
  .row-cat,.row-date{grid-column:2;font-size:10.5px}
  .row-date{display:none}
  .bm{grid-row:1;grid-column:3}
  .wk-head .mono{display:none}
}
.rm-empty{display:none;text-align:center;padding:60px 20px;border:1px dashed var(--line);border-radius:18px;gap:12px;justify-items:center}
.rm-empty.show{display:grid}

/* open-source terminal card */
.opensrc{padding:calc(var(--su)*80) 0 calc(var(--su)*140)}
.term{max-width:760px;border:1px solid var(--line);border-radius:18px;background:#070B09;overflow:hidden;color:var(--cream)}
.term-bar{display:flex;gap:8px;align-items:center;padding:13px 16px;border-bottom:1px solid var(--line);color:var(--mute)}
.term-bar i{width:10px;height:10px;border-radius:50%;background:var(--ink-3)}
.term-bar i:first-child{background:var(--lime)}
.term-bar span{margin-left:8px}
.term pre{font-family:var(--f-mono);font-size:14px;line-height:1.85;padding:22px;white-space:pre-wrap;color:var(--mute)}
.term pre b{color:var(--cream);font-weight:400}
.term pre .k{color:var(--lime)}
.term-links{display:flex;flex-wrap:wrap;gap:10px;padding:0 22px 22px}

/* footer */
.site-foot{border-top:1px solid var(--line);padding:calc(var(--su)*80) 0 30px;overflow:hidden}
.foot-grid{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:30px;margin-bottom:calc(var(--su)*60)}
.foot-grid h4{font-family:var(--f-mono);font-weight:400;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--fg-2);margin-bottom:12px}
.foot-grid a{display:block;text-decoration:none;padding:3px 0;font-weight:500}
.foot-grid p{color:var(--fg-2);max-width:40ch;font-size:15px}
.foot-word{font-family:var(--f-head);font-weight:800;font-size:calc(var(--su)*250);letter-spacing:-.06em;line-height:.8;white-space:nowrap;
  color:transparent;-webkit-text-stroke:1px var(--line);user-select:none;margin-bottom:24px}
.foot-base{display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px;color:var(--fg-2)}
@media (max-width:767px){.foot-grid{grid-template-columns:1fr 1fr}.foot-grid>div:first-child{grid-column:1/-1}.foot-word{font-size:calc(var(--su)*92)}}

/* reveal helpers */
[data-reveal]{visibility:visible}
.js.motion [data-fade]{opacity:0;transform:translateY(26px);transition:opacity .9s var(--out),transform .9s var(--out)}
.js.motion [data-fade].in{opacity:1;transform:none}

/* tutor panel */
.fab{position:fixed;right:20px;bottom:20px;z-index:55;height:52px;padding:0 20px;border-radius:999px;background:var(--lime);color:var(--ink);font-family:var(--f-mono);font-size:14px;font-weight:500;
  box-shadow:0 10px 40px rgba(198,244,50,.3);transition:transform .3s var(--out),opacity .3s}
.fab:hover{transform:translateY(-3px)}
.fab.hidden{opacity:0;pointer-events:none}
.tutor{position:fixed;right:20px;bottom:20px;z-index:56;width:min(420px,calc(100vw - 40px));height:min(560px,calc(100vh - 110px));background:#070B09;color:var(--cream);
  border:1px solid var(--line);border-radius:18px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 30px 90px rgba(0,0,0,.55);
  transform:translateY(20px) scale(.97);opacity:0;pointer-events:none;transition:transform .45s var(--out),opacity .3s}
.tutor.open{transform:none;opacity:1;pointer-events:auto}
.tutor-head{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid var(--line);color:var(--mute)}
.t-close{width:32px;height:32px;border-radius:50%;border:1px solid var(--line);color:var(--cream)}
.tutor-hint{padding:10px 16px;font-size:13px;color:var(--mute);border-bottom:1px solid var(--line)}
.tutor-body{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;overscroll-behavior:contain}
.msg{max-width:88%;padding:10px 14px;border-radius:14px;font-size:14px;line-height:1.55;white-space:pre-wrap}
.msg.bot{background:var(--ink-3);align-self:flex-start}
.msg.user{background:var(--lime);color:var(--ink);align-self:flex-end}
.msg.error{border:1px solid #FF7A59;color:#FFB4A0}
.typing{display:flex;gap:4px}.typing span{width:6px;height:6px;border-radius:50%;background:var(--mute);animation:blink 1s infinite}
.typing span:nth-child(2){animation-delay:.15s}.typing span:nth-child(3){animation-delay:.3s}
@keyframes blink{50%{opacity:.25}}
.chips{display:flex;gap:6px;flex-wrap:wrap;padding:0 16px 10px}
.chip{font-family:var(--f-mono);font-size:12px;border:1px solid var(--line);border-radius:999px;padding:5px 11px;color:var(--mute);cursor:pointer}
.chip:hover{border-color:var(--lime);color:var(--lime)}
.tutor-inp{display:flex;gap:8px;padding:12px;border-top:1px solid var(--line)}
.tutor-inp input{flex:1;min-width:0;height:42px;border-radius:999px;border:1px solid var(--line);background:var(--ink);color:var(--cream);padding:0 16px;font-family:var(--f-mono);font-size:13px}
.tutor-inp input:focus{outline:none;border-color:var(--lime)}
.tsend{height:42px;padding:0 16px;border-radius:999px;background:var(--lime);color:var(--ink);font-family:var(--f-mono);font-size:13px}
.tsend:disabled{opacity:.5}

/* ── chapter + e-book pages ── */
.page{padding-top:68px}
.ch-hero{max-width:980px;margin:0 auto;padding:calc(var(--su)*90) var(--pad) calc(var(--su)*50)}
.ch-meta{display:flex;flex-wrap:wrap;gap:8px 18px;color:var(--fg-2);margin-bottom:22px}
.ch-meta span:first-child{color:var(--lime)}
.ch-title{font-family:var(--f-head);font-weight:800;font-size:clamp(34px,calc(var(--su)*76),84px);line-height:1;letter-spacing:-.04em}
.ch-actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:30px}
.ch-body{max-width:740px;margin:0 auto;padding:0 var(--pad) calc(var(--su)*100)}
.ch-body p{margin-bottom:1em;color:color-mix(in srgb,var(--fg) 86%,transparent)}
.ch-body ul{padding-left:1.2em;margin-bottom:1em}
.ch-body li{margin-bottom:.55em;color:color-mix(in srgb,var(--fg) 86%,transparent)}
.ch-body li::marker{color:var(--lime)}
.tldr{border:1px solid rgba(198,244,50,.45);border-radius:18px;padding:22px 24px;margin-bottom:48px;background:linear-gradient(135deg,rgba(198,244,50,.09),transparent 60%)}
.tldr .mono{color:var(--lime);display:block;margin-bottom:8px}
.tldr p{margin:0;font-size:1.06em;color:var(--fg)}
.blk{padding-top:40px;margin-top:40px;border-top:1px solid var(--line)}
.blk:first-of-type{border-top:0;margin-top:0;padding-top:0}
.blk h2{font-family:var(--f-head);font-weight:700;font-size:clamp(24px,calc(var(--su)*34),36px);line-height:1.15;letter-spacing:-.025em;margin-bottom:18px;display:grid;gap:8px}
.blk h2 .mono{color:var(--lime);font-weight:400}
.code-wrap{border:1px solid var(--line);border-radius:14px;overflow:hidden;margin:18px 0 22px;background:#070B09}
.code-head{display:flex;justify-content:space-between;align-items:center;padding:8px 14px;border-bottom:1px solid var(--line);color:var(--mute)}
.code-copy{font-family:var(--f-mono);font-size:12px;border:1px solid var(--line);border-radius:999px;padding:4px 12px;color:var(--cream)}
.code-copy.copied{background:var(--lime);color:var(--ink);border-color:var(--lime)}
.code-wrap pre{padding:16px;overflow-x:auto;font-family:var(--f-mono);font-size:13.5px;line-height:1.65;color:#D8E4DA}
.iq{border-left:2px solid var(--lime);padding:10px 16px;margin-bottom:12px;background:var(--card);border-radius:0 10px 10px 0}
.ig-frame{border:1px solid var(--line);border-radius:16px;overflow:hidden;margin:16px 0}
.ig-actions{display:flex;flex-wrap:wrap;gap:10px}
.read-ring{position:fixed;left:18px;bottom:18px;z-index:40;opacity:0;transition:opacity .3s}
.read-ring.show{opacity:1}
.read-ring circle{fill:none;stroke-width:3}
.read-ring .rr-bg{stroke:var(--line)}
.read-ring .rr-prog{stroke:var(--lime);transform:rotate(-90deg);transform-origin:50% 50%;stroke-linecap:round}
.ch-foot{border-top:1px solid var(--line);padding:30px var(--pad);display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px;color:var(--fg-2);position:relative;z-index:1}
.ch-foot a{text-decoration:none}
.toc{display:grid;border-top:1px solid var(--line);margin-bottom:80px}
.toc a{display:grid;grid-template-columns:64px 1fr auto;gap:14px;align-items:baseline;padding:13px 6px;border-bottom:1px solid var(--line);text-decoration:none;transition:padding .3s var(--out),color .2s}
.toc a:hover{padding-left:14px;color:var(--lime)}
.toc .mono{color:var(--lime)}
.toc small{font-family:var(--f-mono);color:var(--fg-2);font-size:12px}
.eb-ch{padding:60px 0;border-top:1px solid var(--line)}
.eb-ch h2{font-family:var(--f-head);font-weight:800;font-size:clamp(28px,calc(var(--su)*48),52px);line-height:1.02;letter-spacing:-.035em;margin:10px 0 24px}
.eb-ch h3{font-family:var(--f-head);font-weight:700;font-size:21px;margin:26px 0 10px;letter-spacing:-.015em}
.eb-top{display:inline-block;margin-top:14px;color:var(--fg-2);text-decoration:none}
@media (max-width:767px){.toc a{grid-template-columns:52px 1fr}.toc small{display:none}.ch-title{font-size:38px;overflow-wrap:break-word;hyphens:auto}}

/* calm mode for people who turn off motion */
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.01ms!important;transition-duration:.01ms!important}
  .edge-glow{display:none}
}
"""


# ── Shared page JS (every page) ───────────────────────────────────────────────

JS = r"""
(function(){
'use strict';
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>Array.from(r.querySelectorAll(s));
const root=document.documentElement, body=document.body;
// ?motion=on shows the full animation even when the system asks for less motion
const reduce=!/[?&]motion=on/.test(location.search)&&matchMedia('(prefers-reduced-motion: reduce)').matches;
const isMobile=()=>innerWidth<768;
const HAS=!!(window.gsap&&window.ScrollTrigger);
const MOTION=HAS&&!reduce;
const DDS=window.DDS=window.DDS||{};
DDS.target=DDS.target||{x:.42,y:0,s:1,open:0,xray:0,alpha:1};
DDS.vel=0;
root.classList.add(MOTION?'motion':'motion-none');
if(HAS){ gsap.registerPlugin(ScrollTrigger); if(window.SplitText) gsap.registerPlugin(SplitText); }

/* letter-roll: every char gets a two-line mask */
$$('.roll').forEach(el=>{
  const t=el.textContent.trim(); el.setAttribute('aria-label',t); el.textContent='';
  [...t].forEach((c,i)=>{
    const s=document.createElement('span'); s.className='ch'; s.setAttribute('aria-hidden','true'); s.style.setProperty('--i',i);
    for(let k=0;k<2;k++){ const x=document.createElement('span'); x.textContent=c===' '?' ':c; s.appendChild(x); }
    el.appendChild(s);
  });
});

/* smooth scroll */
let lenis=null;
if(window.Lenis&&!reduce){
  lenis=new Lenis({lerp:.1});
  if(HAS){ lenis.on('scroll',ScrollTrigger.update); gsap.ticker.add(t=>lenis.raf(t*1000)); gsap.ticker.lagSmoothing(0); }
  else { const raf=t=>{lenis.raf(t);requestAnimationFrame(raf);}; requestAnimationFrame(raf); }
  lenis.on('scroll',e=>{DDS.vel=e.velocity||0;});
}
DDS.lenis=lenis;
function scrollToEl(el){
  if(typeof el==='string'){ try{el=$(el);}catch(e){el=null;} }
  if(!el) return;
  const y=Math.max(0,el.getBoundingClientRect().top+scrollY-70);
  if(lenis) lenis.scrollTo(y,{duration:1.4}); else scrollTo({top:y,behavior:reduce?'auto':'smooth'});
}
DDS.scrollTo=scrollToEl;

/* menu */
const burger=$('#burger');
function closeMenu(){ body.classList.remove('menu-open'); if(burger) burger.setAttribute('aria-expanded','false'); if(lenis) lenis.start(); }
if(burger){ burger.addEventListener('click',()=>{ const o=body.classList.toggle('menu-open'); burger.setAttribute('aria-expanded',o?'true':'false'); if(lenis){ o?lenis.stop():lenis.start(); } }); }
$$('a[href^="#"]').forEach(a=>a.addEventListener('click',e=>{
  const id=a.getAttribute('href'); if(id.length<2) return;
  const el=$(id); if(!el) return;
  e.preventDefault(); closeMenu(); scrollToEl(el); history.replaceState(null,'',id);
}));

/* nav state, side indicator, reading ring */
const nav=$('.nav'), ind=$('.scroll-ind i'), rr=$('#readRing');
let rrC=null, rrLen=0, doneFired=false;
if(rr){ rrC=rr.querySelector('.rr-prog'); rrLen=2*Math.PI*rrC.r.baseVal.value; rrC.style.strokeDasharray=rrLen; rrC.style.strokeDashoffset=rrLen; }
function onScroll(){
  const h=document.documentElement.scrollHeight-innerHeight, p=h>0?scrollY/h:0;
  if(nav) nav.classList.toggle('scrolled',scrollY>20);
  if(ind) ind.style.transform='scaleY('+p+')';
  if(rrC){
    rrC.style.strokeDashoffset=rrLen-p*rrLen; rr.classList.toggle('show',p>.03);
    if(p>.92&&!doneFired&&typeof CURRENT_ISSUE!=='undefined'){
      doneFired=true; const d=getList('dds-completed'); if(!d.includes(CURRENT_ISSUE)){ d.push(CURRENT_ISSUE); setList('dds-completed',d); refreshChapter(); }
    }
  }
}
addEventListener('scroll',onScroll,{passive:true}); onScroll();

/* storage helpers */
function getList(k){ try{ return JSON.parse(localStorage.getItem(k)||'[]'); }catch(e){ return []; } }
function setList(k,v){ try{ localStorage.setItem(k,JSON.stringify(v)); }catch(e){} }

/* reveals: masked lines on headings, fade-ups elsewhere */
function setupReveals(){
  if(!MOTION||!window.SplitText) return;
  $$('[data-reveal]').forEach(el=>{
    SplitText.create(el,{type:'lines',mask:'lines',autoSplit:true,onSplit(self){
      return gsap.from(self.lines,{yPercent:110,duration:1.1,ease:'expo.out',stagger:.08,scrollTrigger:{trigger:el,start:'top 88%',once:true}});
    }});
  });
}
const fio=new IntersectionObserver(es=>es.forEach(e=>{ if(e.isIntersecting){ e.target.classList.add('in'); fio.unobserve(e.target); } }),{rootMargin:'0px 0px -8% 0px'});
$$('[data-fade]').forEach(el=>fio.observe(el));

/* code copy */
$$('.code-copy').forEach(b=>b.addEventListener('click',async()=>{
  const code=b.closest('.code-wrap').querySelector('pre code').textContent;
  try{ await navigator.clipboard.writeText(code); b.textContent='Copied'; b.classList.add('copied'); }
  catch(e){ b.textContent='Failed'; }
  setTimeout(()=>{ b.textContent='Copy'; b.classList.remove('copied'); },1800);
}));

/* chapter page: bookmark + complete */
const bmBtn=$('#chapterBookmark'), cmBtn=$('#chapterComplete');
function refreshChapter(){
  if(typeof CURRENT_ISSUE==='undefined') return;
  const m=getList('dds-bookmarks'), d=getList('dds-completed');
  if(bmBtn){ const on=m.includes(CURRENT_ISSUE); bmBtn.classList.toggle('on',on); bmBtn.textContent=on?'★ Bookmarked':'☆ Bookmark'; }
  if(cmBtn){ const on=d.includes(CURRENT_ISSUE); cmBtn.classList.toggle('on',on); cmBtn.textContent=on?'✓ Completed':'○ Mark complete'; }
}
if(bmBtn) bmBtn.addEventListener('click',()=>{ let m=getList('dds-bookmarks'); m=m.includes(CURRENT_ISSUE)?m.filter(n=>n!==CURRENT_ISSUE):m.concat(CURRENT_ISSUE); setList('dds-bookmarks',m); refreshChapter(); });
if(cmBtn) cmBtn.addEventListener('click',()=>{ let d=getList('dds-completed'); d=d.includes(CURRENT_ISSUE)?d.filter(n=>n!==CURRENT_ISSUE):d.concat(CURRENT_ISSUE); setList('dds-completed',d); refreshChapter(); });
refreshChapter();

/* roadmap: weeks, filters, search, bookmarks */
function refreshST(){ if(HAS){ clearTimeout(refreshST.t); refreshST.t=setTimeout(()=>{ ScrollTrigger.sort(); ScrollTrigger.refresh(); },620); } }
$$('.wk-head').forEach(h=>h.addEventListener('click',()=>{
  const p=h.nextElementSibling, o=!p.classList.contains('open');
  p.classList.toggle('open',o); h.classList.toggle('open',o); h.setAttribute('aria-expanded',o?'true':'false'); refreshST();
}));
function refreshBookmarks(){
  const m=getList('dds-bookmarks');
  $$('.bm[data-issue]').forEach(b=>{ const on=m.includes(+b.dataset.issue); b.classList.toggle('on',on); b.textContent=on?'★':'☆'; b.setAttribute('aria-pressed',on?'true':'false'); });
}
$$('.bm[data-issue]').forEach(b=>b.addEventListener('click',e=>{
  e.preventDefault(); e.stopPropagation();
  const n=+b.dataset.issue; let m=getList('dds-bookmarks'); m=m.includes(n)?m.filter(x=>x!==n):m.concat(n); setList('dds-bookmarks',m); refreshBookmarks();
}));
refreshBookmarks();
(function(){ const d=getList('dds-completed'); $$('.row[data-issue]').forEach(r=>{ if(d.includes(+r.dataset.issue)){ const t=r.querySelector('.row-title'); if(t&&!t.querySelector('.row-read')){ const s=document.createElement('span'); s.className='row-read'; s.textContent='✓ READ'; t.appendChild(s); } } }); })();

const q=$('#q'), qCount=$('#qCount'), qEmpty=$('#qEmpty'), weeks=$('#weeks');
let activeCat='', qT;
function applyFilters(){
  if(!weeks) return;
  const s=(q?q.value.trim():'').toLowerCase(); let v=0;
  $$('.wk',weeks).forEach(w=>{
    let any=false;
    $$('.row',w).forEach(r=>{ const ok=(!s||r.textContent.toLowerCase().includes(s))&&(!activeCat||r.dataset.cat===activeCat); r.style.display=ok?'':'none'; if(ok){any=true;v++;} });
    w.style.display=any?'':'none';
    if((s||activeCat)&&any){ const h=$('.wk-head',w), p=$('.wk-panel',w); p.classList.add('open'); h.classList.add('open'); h.setAttribute('aria-expanded','true'); }
  });
  const filtering=!!(s||activeCat);
  if(qCount) qCount.textContent=filtering?(v+' chapter'+(v!==1?'s':'')+' found'):'';
  if(qEmpty) qEmpty.classList.toggle('show',filtering&&v===0);
  weeks.style.display=(filtering&&v===0)?'none':'';
  refreshST();
}
function setCat(c){
  activeCat=c||''; $$('.cat-pill').forEach(p=>{ const on=(p.dataset.cat||'')===activeCat; p.classList.toggle('on',on); p.setAttribute('aria-pressed',on?'true':'false'); });
  applyFilters();
}
DDS.setCat=setCat;
$$('.cat-pill').forEach(p=>p.addEventListener('click',()=>setCat(activeCat===(p.dataset.cat||'')&&p.dataset.cat?'':p.dataset.cat)));
if(q){
  q.addEventListener('input',()=>{ clearTimeout(qT); qT=setTimeout(applyFilters,220); });
  addEventListener('keydown',e=>{
    if(e.key==='/'&&document.activeElement!==q&&!/INPUT|TEXTAREA/.test(document.activeElement.tagName)){ e.preventDefault(); scrollToEl('#roadmap'); q.focus({preventScroll:true}); }
    if(e.key==='Escape'&&document.activeElement===q){ q.value=''; q.blur(); setCat(''); }
  });
}
const qClear=$('#qClear'); if(qClear) qClear.addEventListener('click',()=>{ if(q) q.value=''; setCat(''); });
$$('[data-jump-cat]').forEach(b=>b.addEventListener('click',()=>{ setCat(b.dataset.jumpCat); scrollToEl('#roadmap'); }));

/* tutor */
const tp=$('#tutorPanel'), fab=$('#tutorFab'), tin=$('#tutorIn');
function openTutor(question){
  if(!tp) return; tp.classList.add('open'); if(fab) fab.classList.add('hidden');
  if(question&&tin){ tin.value=question; tutorSend(); } else if(tin){ setTimeout(()=>tin.focus(),300); }
}
function closeTutor(){ if(!tp) return; tp.classList.remove('open'); if(fab) fab.classList.remove('hidden'); }
function addMsg(text,role){ const b=$('#tutorBody'), d=document.createElement('div'); d.className='msg '+role; d.textContent=text; b.appendChild(d); b.scrollTop=b.scrollHeight; }
async function tutorSend(){
  const btn=$('#tSend'), msg=tin.value.trim(); if(!msg) return;
  addMsg(msg,'user'); tin.value=''; btn.disabled=true;
  const b=$('#tutorBody'), w=document.createElement('div'); w.className='msg bot'; w.innerHTML='<div class="typing"><span></span><span></span><span></span></div>'; b.appendChild(w); b.scrollTop=b.scrollHeight;
  const r=await callGemini(msg); w.remove(); addMsg(r.text,r.error?'bot error':'bot'); btn.disabled=false;
}
async function callGemini(msg){
  let k=localStorage.getItem('dds-gemini')||'';
  if(!k){ const nk=prompt('Enter your free Gemini API key (from aistudio.google.com). It is saved only in this browser.'); if(nk&&nk.trim()){ localStorage.setItem('dds-gemini',nk.trim()); k=nk.trim(); } else return {text:'No API key found. Get a free Gemini key at aistudio.google.com',error:true}; }
  try{
    const ctx=typeof TUTOR_CTX!=='undefined'?TUTOR_CTX:'';
    const p='You are an expert AI tutor for Daily Dose of DS newsletter content. Use this index to answer:\n\n'+ctx+'\n\nUser: '+msg+'\n\nRules: Answer from the index above. If asked to explain an issue by number, explain thoroughly and cite issue number + date.';
    const res=await fetch('https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key='+encodeURIComponent(k),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({contents:[{parts:[{text:p}]}]})});
    if(!res.ok){
      if(res.status===400||res.status===403){ localStorage.removeItem('dds-gemini'); return {text:'That API key was rejected. Ask again to enter a new one.',error:true}; }
      if(res.status===429) return {text:'Rate limit hit on the free Gemini tier. Try again in a few seconds.',error:true};
      return {text:'Gemini request failed (HTTP '+res.status+'). Please try again.',error:true};
    }
    const d=await res.json(), t=d.candidates&&d.candidates[0]&&d.candidates[0].content&&d.candidates[0].content.parts&&d.candidates[0].content.parts[0]&&d.candidates[0].content.parts[0].text;
    return t?{text:t,error:false}:{text:'Gemini returned an empty answer. Try rephrasing.',error:true};
  }catch(e){ return {text:"Couldn't reach Gemini. Check your connection and try again.",error:true}; }
}
window.openTutor=openTutor; window.closeTutor=closeTutor; window.tutorSend=tutorSend;
if(fab) fab.addEventListener('click',()=>openTutor());
$$('[data-open-tutor]').forEach(a=>a.addEventListener('click',e=>{ e.preventDefault(); closeMenu(); openTutor(); }));
const tc=$('#tutorClose'); if(tc) tc.addEventListener('click',closeTutor);
const ts=$('#tSend'); if(ts) ts.addEventListener('click',tutorSend);
if(tin) tin.addEventListener('keydown',e=>{ if(e.key==='Enter') tutorSend(); });
$$('.chip[data-q]').forEach(c=>c.addEventListener('click',()=>{ if(tin){ tin.value=c.dataset.q; tutorSend(); } }));
addEventListener('keydown',e=>{ if(e.key==='Escape'&&tp&&tp.classList.contains('open')) closeTutor(); });

DDS.motion=MOTION; DDS.HAS=HAS; DDS.setupReveals=setupReveals; DDS.closeMenu=closeMenu;
if(!$('#loader')){ setupReveals(); }
})();
"""


# ── Landing page JS (scroll story) ────────────────────────────────────────────

JS_HOME = r"""
(function(){
'use strict';
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>Array.from(r.querySelectorAll(s));
const root=document.documentElement, body=document.body, DDS=window.DDS, MOTION=DDS.motion;
const isMobile=()=>innerWidth<768;
const clamp=(v,a,b)=>Math.min(b,Math.max(a,v));

/* where the capsule sits in each section: x,y in half-screen units */
const STAGES={
  hero:{x:.44,y:.02,s:1.05,open:0,xray:0,alpha:1},
  pitch:{x:.52,y:-.05,s:.95,open:0,xray:0,alpha:1},
  daily:{x:.7,y:-.6,s:.4,open:1,xray:0,alpha:0},
  how:{x:.5,y:-.02,s:1.05,open:0,xray:1,alpha:1},
  decode:{x:-.52,y:0,s:.8,open:1,xray:0,alpha:1},
  topics:{x:-.5,y:.04,s:.62,open:1,xray:0,alpha:1},
  steady:{x:0,y:-.7,s:.5,open:0,xray:0,alpha:0},
  roadmap:{x:.8,y:0,s:.5,open:0,xray:0,alpha:0},
  opensrc:{x:.55,y:0,s:.85,open:0,xray:0,alpha:1},
  foot:{x:.74,y:-.5,s:.5,open:1,xray:0,alpha:1}
};
const STAGES_M={
  hero:{x:.35,y:.12,s:.55,alpha:.42},pitch:{x:.45,y:.6,s:.42},how:{x:.6,y:.5,s:.5,alpha:.3},
  decode:{alpha:0},topics:{alpha:0},opensrc:{x:.5,y:.66,s:.38},foot:{alpha:0}
};
function setStage(n){
  const t=Object.assign({},STAGES[n]||STAGES.hero,isMobile()?(STAGES_M[n]||{}):{});
  Object.assign(DDS.target,t); DDS.stage=n;
}
setStage('hero');

/* loader: draws the capsule outline while fonts, page and 3D get ready */
const loader=$('#loader');
let started=false;
function start(){
  if(started) return; started=true;
  root.classList.remove('is-loading');
  if(DDS.lenis) DDS.lenis.start();
  // split text only after the web fonts are in (or 1.5 s), so line breaks are measured right
  const fonts=document.fonts&&document.fonts.ready?Promise.race([document.fonts.ready,new Promise(r=>setTimeout(r,1500))]):Promise.resolve();
  fonts.then(ready);
}
function ready(){
  build();
  if(DDS.setupReveals) DDS.setupReveals();
  // arriving with #roadmap: jump once the layout is ready, then correct if pins moved it
  const toHash=()=>{
    if(!(location.hash&&location.hash.length>1)) return;
    let el=null; try{ el=$(location.hash); }catch(e){}
    if(!el) return;
    setTimeout(()=>DDS.scrollTo(el),150);
    setTimeout(()=>{
      if(MOTION){ ScrollTrigger.sort(); ScrollTrigger.refresh(); }
      const off=el.getBoundingClientRect().top-70;
      if(Math.abs(off)>8){ const y=scrollY+off; if(DDS.lenis) DDS.lenis.scrollTo(y,{immediate:true}); else scrollTo(0,y); }
    },1900);
  };
  if(MOTION){
    // measure pins top to bottom, so each one knows the space taken by the pins above it
    const fix=()=>{ ScrollTrigger.sort(); ScrollTrigger.refresh(); };
    fix(); setTimeout(fix,500);
  }
  toHash();
}
// the loader plays once per visit; coming back from a chapter skips it
let seen=false; try{ seen=!!sessionStorage.getItem('dds-seen'); sessionStorage.setItem('dds-seen','1'); }catch(e){}
if(loader&&(!MOTION||seen)){ loader.remove(); start(); }
else if(loader){
  root.classList.add('is-loading');
  if(DDS.lenis) DDS.lenis.stop();
  const pct=$('#ldPct'), draw=$$('.ld-draw',loader);
  const got={fonts:0,load:0,gl:0};
  const target=()=>8+(got.fonts?22:0)+(got.load?30:0)+(got.gl?40:0);
  if(document.fonts&&document.fonts.ready) document.fonts.ready.then(()=>got.fonts=1); else got.fonts=1;
  if(document.readyState==='complete') got.load=1; else addEventListener('load',()=>got.load=1);
  if(DDS.glReady) got.gl=1; else addEventListener('dds:gl',()=>got.gl=1,{once:true});
  setTimeout(()=>{got.fonts=got.load=got.gl=1;},5200);
  let shown=0, finished=false;
  function finish(){
    if(finished) return; finished=true;
    pct.textContent='100'; draw.forEach(p=>p.style.strokeDashoffset='0');
    loader.classList.add('done'); setTimeout(()=>loader.remove(),1100); start();
  }
  (function tick(){
    if(finished) return;
    const t=target(); shown+=Math.max(.35,(t-shown)*.07); if(shown>t) shown=t;
    pct.textContent=String(Math.floor(shown)).padStart(3,'0');
    draw.forEach(p=>p.style.strokeDashoffset=String(1-shown/100));
    if(shown>=100){ finish(); return; }
    requestAnimationFrame(tick);
  })();
  setTimeout(finish,6500);   // never hold the page if animation frames are paused
} else start();

function build(){
  /* no animation library or reduced motion: show everything in its final state */
  if(!MOTION){
    const io=new IntersectionObserver(es=>es.forEach(e=>{ if(e.isIntersecting) setStage(e.target.dataset.stage); }),{rootMargin:'-45% 0px -45% 0px'});
    $$('[data-stage]').forEach(s=>io.observe(s));
    $$('.step').forEach(s=>s.classList.add('on'));
    const ro=$('.readout'); if(ro) ro.classList.add('on');
    const st=$('#steady'); if(st){ new IntersectionObserver(es=>es.forEach(e=>body.classList.toggle('is-light',e.isIntersecting)),{rootMargin:'-40% 0px -40% 0px'}).observe(st); }
    return;
  }

  const ST=ScrollTrigger;
  const mm=gsap.matchMedia();

  /* hero intro: logo letters rise */
  if(window.SplitText){
    const hs=SplitText.create('#heroLogo .main',{type:'words,chars',mask:'chars'});
    gsap.from(hs.chars,{yPercent:110,duration:1.2,ease:'expo.out',stagger:.035,delay:.05});
  }
  gsap.from('#heroCopy > *, .hero-stats > div',{y:30,opacity:0,duration:1,ease:'expo.out',stagger:.07,delay:.35});

  /* 1. hero: the giant logo shrinks into the nav, the copy blurs out */
  const hl=$('#heroLogo'), nl=$('.nav-logo span'), hero=$('#hero');
  function measure(){
    const prev=hl.style.transform; hl.style.transform='none';
    const a=hl.getBoundingClientRect(), h=hero.getBoundingClientRect(), b=nl.getBoundingClientRect();
    hl.style.transform=prev;
    const main=hl.querySelector('.main').getClientRects()[0];
    return {x:b.left-a.left, y:b.top-(a.top-h.top)-(main.top-a.top)*(b.height/main.height), s:b.height/main.height};
  }
  let M=measure();
  const heroTl=gsap.timeline({scrollTrigger:{trigger:hero,start:'top top',end:()=>'+='+innerHeight*.9,pin:true,scrub:.6,invalidateOnRefresh:true,
    onRefresh:()=>{M=measure();},
    onUpdate:s=>body.classList.toggle('logo-docked',s.progress>.985)}});
  heroTl.to(hl,{x:()=>M.x,y:()=>M.y,scale:()=>M.s,ease:'power2.inOut',duration:1},0)
        .to('#heroCopy, .hero-stats, .scroll-cue',{filter:'blur(14px)',opacity:0,y:-30,ease:'none',duration:.55},0);

  /* 2. pitch: words fill in, then "Rewritten by AI*" and the edge glow */
  if(window.SplitText){
    const words=SplitText.create('#pitchText',{type:'words'}).words;
    const ai=SplitText.create('#pitchAi',{type:'lines',mask:'lines'}).lines;
    const glow=$('.edge-glow');
    const tl=gsap.timeline({scrollTrigger:{trigger:'#pitch',start:'top top',end:()=>'+='+innerHeight*(isMobile()?1.6:2.4),pin:true,scrub:.5,
      onUpdate:s=>{ if(DDS.stage==='pitch') DDS.target.open=clamp((s.progress-.55)/.35,0,1); }}});
    tl.fromTo(words,{opacity:.12},{opacity:1,stagger:.12,ease:'none',duration:.12})
      .fromTo(ai,{yPercent:115},{yPercent:0,duration:.5,ease:'power3.out'},'+=.1')
      .fromTo('#pitch .footnote',{opacity:0,y:20},{opacity:1,y:0,duration:.4},'<.2')
      .to(glow,{opacity:1,duration:.5},'<')
      .to(glow,{opacity:0,duration:.6},'+=.6');
  }

  /* 3. daily: giant line passes through the dashed frame, which becomes a gallery */
  const word=$('#dailyWord'), track=$('#dailyTrack'), frame=$('#dailyFrame');
  if(word&&track){
    const dist=()=>word.scrollWidth+innerWidth+Math.max(0,track.scrollWidth-innerWidth);
    const tl=gsap.timeline({scrollTrigger:{trigger:'#daily',start:'top top',end:()=>'+='+dist()*.55,pin:true,scrub:.6,invalidateOnRefresh:true}});
    tl.fromTo(word,{x:()=>innerWidth},{x:()=>-word.scrollWidth,ease:'none',duration:3})
      .fromTo(track,{autoAlpha:0,y:40},{autoAlpha:1,y:0,duration:.6,ease:'power2.out'},'-=.9')
      .to(frame,{autoAlpha:0,duration:.5},'+=.15')
      .to(track,{x:()=>-Math.max(0,track.scrollWidth-innerWidth),ease:'none',duration:3},'<');
  }

  /* 4. how it runs: the line draws and steps light up */
  gsap.fromTo('.how-line i',{scaleY:0},{scaleY:1,ease:'none',scrollTrigger:{trigger:'.how-steps',start:'top 65%',end:'bottom 65%',scrub:true}});
  $$('.step').forEach(s=>ST.create({trigger:s,start:'top 68%',onEnter:()=>s.classList.add('on'),onLeaveBack:()=>s.classList.remove('on')}));
  gsap.from('.callout',{opacity:0,x:-20,stagger:.15,duration:.8,ease:'expo.out',scrollTrigger:{trigger:'#how',start:'top 40%'}});

  /* 5. decode: the headline unscrambles when it arrives */
  const dh=$('#decodeTitle');
  if(dh){
    const final=dh.textContent, chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ#%&*01';
    ST.create({trigger:dh,start:'top 80%',once:true,onEnter:()=>{
      let f=0; const n=final.length;
      const iv=setInterval(()=>{ f++; dh.textContent=final.split('').map((c,i)=>c===' '||i<f/1.6?c:chars[Math.floor(Math.random()*chars.length)]).join(''); if(f/1.6>=n){ clearInterval(iv); dh.textContent=final; } },28);
    }});
  }

  /* 6. topics: bars fill */
  const ro=$('.readout'); if(ro) ST.create({trigger:ro,start:'top 75%',once:true,onEnter:()=>ro.classList.add('on')});
  gsap.from('.lens',{rotate:-40,scale:.85,opacity:0,duration:1.4,ease:'expo.out',scrollTrigger:{trigger:'#topics',start:'top 65%'}});

  /* 7. consistency: page turns light, the giant word goes ghost to solid */
  const stl=gsap.timeline({scrollTrigger:{trigger:'#steady',start:'top top',end:()=>'+='+innerHeight*(isMobile()?.9:1.4),pin:true,scrub:.5}});
  stl.fromTo('#steadyWord',{opacity:.08,scale:.94},{opacity:1,scale:1,duration:1,ease:'none'})
     .fromTo('.sc',{y:80,opacity:0},{y:0,opacity:1,stagger:.15,duration:.6,ease:'power2.out'},'-=.3');
  // pinned sections sit inside a pin-spacer that covers their whole scroll length
  const box=sec=>sec.parentElement&&sec.parentElement.classList.contains('pin-spacer')?sec.parentElement:sec;
  ST.create({trigger:box($('#steady')),start:'top 55%',end:'bottom 45%',toggleClass:{targets:body,className:'is-light'}});

  /* capsule stages: created last so they measure after the pins */
  $$('[data-stage]').forEach(sec=>ST.create({trigger:box(sec),start:'top 55%',end:'bottom 55%',onToggle:s=>{ if(s.isActive) setStage(sec.dataset.stage); }}));
  addEventListener('resize',()=>setStage(DDS.stage||'hero'));
}
})();
"""


# ── Three.js capsule (landing page only) ──────────────────────────────────────

JS_GL = r"""
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const DDS = window.DDS = window.DDS || {};
DDS.target = DDS.target || {x:.44,y:0,s:1,open:0,xray:0,alpha:1};
const ready = () => { DDS.glReady = true; window.dispatchEvent(new Event('dds:gl')); };
const canvas = document.getElementById('gl');

function start(){
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' }); }
  catch (e) { ready(); return; }
  const mobile = matchMedia('(max-width: 767px)').matches;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  renderer.setPixelRatio(Math.min(devicePixelRatio, mobile ? 1.5 : 1.75));
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = 1.0;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, .1, 100);
  camera.position.set(0, 0, 10);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), .04).texture;
  const key = new THREE.DirectionalLight(0xffffff, 1.6); key.position.set(3, 4, 5); scene.add(key);
  const rim = new THREE.DirectionalLight(0xC6F432, 2.2); rim.position.set(-4, -2, -3); scene.add(rim);

  // capsule: two lathe halves, radius R, straight part H on each side of the seam
  const R = .82, H = .78;
  function halfGeo(seg, rad) {
    const pts = [];
    for (let i = 0; i <= seg; i++) { const a = i / seg * Math.PI / 2; pts.push(new THREE.Vector2(Math.sin(a) * R, H + Math.cos(a) * R)); }
    pts.push(new THREE.Vector2(R, 0));
    return new THREE.LatheGeometry(pts, rad);
  }
  const geo = halfGeo(28, 72), wireGeo = new THREE.WireframeGeometry(halfGeo(7, 22));
  const matTop = new THREE.MeshPhysicalMaterial({ color: '#C6F432', roughness: .32, clearcoat: 1, clearcoatRoughness: .12, transparent: true });
  const matBot = new THREE.MeshPhysicalMaterial({ color: '#E9F2EA', roughness: .22, clearcoat: 1, clearcoatRoughness: .08, sheen: .4, transparent: true });
  const wireMat = new THREE.LineBasicMaterial({ color: '#C6F432', transparent: true, opacity: 0, depthWrite: false });

  const rootG = new THREE.Group(), tilt = new THREE.Group(), spin = new THREE.Group();
  tilt.rotation.z = -.62; rootG.add(tilt); tilt.add(spin); scene.add(rootG);
  const top = new THREE.Group(), bot = new THREE.Group();
  top.add(new THREE.Mesh(geo, matTop), new THREE.LineSegments(wireGeo, wireMat));
  const botMesh = new THREE.Mesh(geo, matBot), botWire = new THREE.LineSegments(wireGeo, wireMat);
  botMesh.rotation.x = botWire.rotation.x = Math.PI;
  bot.add(botMesh, botWire);
  const seam = new THREE.Mesh(new THREE.TorusGeometry(R * 1.003, .018, 8, 96), new THREE.MeshBasicMaterial({ color: '#0A0F0D', transparent: true }));
  seam.rotation.x = Math.PI / 2; bot.add(seam);
  spin.add(top, bot);

  // particles: start inside the capsule, drift out into an orbit when it opens
  const N = mobile ? 700 : 1600;
  const start = new Float32Array(N * 3), end = new Float32Array(N * 3), seed = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    const r = Math.sqrt(Math.random()) * R * .7, a = Math.random() * Math.PI * 2;
    start.set([Math.cos(a) * r, (Math.random() * 2 - 1) * (H + R * .55), Math.sin(a) * r], i * 3);
    const d = new THREE.Vector3().randomDirection(), rr = 1.9 + Math.random() * 1.9;
    end.set([d.x * rr, d.y * rr * .55 + .9, d.z * rr], i * 3);
    seed[i] = Math.random();
  }
  const pg = new THREE.BufferGeometry();
  pg.setAttribute('position', new THREE.BufferAttribute(start, 3));
  pg.setAttribute('aEnd', new THREE.BufferAttribute(end, 3));
  pg.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));
  const pMat = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    uniforms: { uOpen: { value: 0 }, uTime: { value: 0 }, uAlpha: { value: 0 }, uPR: { value: renderer.getPixelRatio() }, uColor: { value: new THREE.Color('#D8FF6A') } },
    vertexShader: `
      uniform float uOpen; uniform float uTime; uniform float uPR;
      attribute vec3 aEnd; attribute float aSeed; varying float vA;
      void main(){
        float o = smoothstep(0., 1., clamp(uOpen * 1.3 - aSeed * .3, 0., 1.));
        vec3 p = mix(position, aEnd, o);
        float a = uTime * (.12 + aSeed * .25) * (.25 + o);
        p.xz = mat2(cos(a), -sin(a), sin(a), cos(a)) * p.xz;
        p.y += sin(uTime * .9 + aSeed * 6.283) * .07;
        vec4 mv = modelViewMatrix * vec4(p, 1.);
        gl_Position = projectionMatrix * mv;
        gl_PointSize = (14. + aSeed * 22.) * uPR / -mv.z;
        vA = .45 + .55 * o;
      }`,
    fragmentShader: `
      uniform vec3 uColor; uniform float uAlpha; varying float vA;
      void main(){ float d = length(gl_PointCoord - .5); if (d > .5) discard; gl_FragColor = vec4(uColor, smoothstep(.5, 0., d) * vA * uAlpha); }`
  });
  tilt.add(new THREE.Points(pg, pMat));

  // soft glow behind, drawn into a small canvas
  const gc = document.createElement('canvas'); gc.width = gc.height = 128;
  const gx = gc.getContext('2d'), grd = gx.createRadialGradient(64, 64, 0, 64, 64, 64);
  grd.addColorStop(0, 'rgba(198,244,50,.55)'); grd.addColorStop(1, 'rgba(198,244,50,0)');
  gx.fillStyle = grd; gx.fillRect(0, 0, 128, 128);
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(gc), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: .25 }));
  glow.scale.setScalar(7); glow.position.z = -2; rootG.add(glow);

  function resize() {
    const w = innerWidth, h = innerHeight;
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  resize(); addEventListener('resize', resize);

  let px = 0, py = 0;
  addEventListener('pointermove', e => { px = e.clientX / innerWidth * 2 - 1; py = e.clientY / innerHeight * 2 - 1; }, { passive: true });

  const damp = (a, b, l, dt) => a + (b - a) * (1 - Math.exp(-l * dt));
  const cur = Object.assign({}, DDS.target);
  const clock = new THREE.Clock();
  let t = 0, first = true;
  document.documentElement.classList.add('gl-on');

  function frame() {
    requestAnimationFrame(frame);
    if (document.hidden) return;
    const dt = Math.min(clock.getDelta(), .05); t += dt;
    const T = DDS.target;
    for (const k of ['x', 'y', 's', 'xray', 'alpha']) cur[k] = damp(cur[k], T[k], first ? 99 : 3.2, dt);
    cur.open = damp(cur.open, T.open, first ? 99 : 4.5, dt);
    canvas.style.opacity = cur.alpha.toFixed(3);
    if (cur.alpha < .01 && T.alpha === 0 && !first) return;   // hidden: skip the render
    const hh = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.position.z, hw = hh * camera.aspect;
    rootG.position.set(cur.x * hw, cur.y * hh, 0);
    rootG.scale.setScalar(cur.s * (mobile ? 1 : Math.min(1.15, Math.max(.8, camera.aspect / 1.6))));
    rootG.rotation.x = damp(rootG.rotation.x, py * .22, 3, dt);
    rootG.rotation.y = damp(rootG.rotation.y, px * .35, 3, dt);
    const v = Math.min(Math.abs(DDS.vel || 0), 80);
    spin.rotation.y += dt * (reduce ? .08 : (.32 + v * .03));
    tilt.rotation.z = -.62 + Math.sin(t * .4) * .05;
    const o = cur.open;
    top.position.set(o * .35, o * 1.35, 0); top.rotation.z = o * .45;
    bot.position.y = -o * .25;
    const solid = 1 - .9 * cur.xray;
    matTop.opacity = matBot.opacity = solid; matTop.depthWrite = matBot.depthWrite = solid > .95;
    seam.material.opacity = solid;
    wireMat.opacity = cur.xray * .85;
    pMat.uniforms.uOpen.value = o; pMat.uniforms.uTime.value = t;
    pMat.uniforms.uAlpha.value = Math.min(1, o * 1.1 + cur.xray);
    glow.material.opacity = .16 + .22 * Math.max(o, cur.xray);
    renderer.render(scene, camera);
    if (first) { first = false; ready(); }
  }
  frame();
}
try { start(); } catch (e) { ready(); }
"""


def make_site_builder(Base, g):
    """Return a SiteBuilder subclass that writes the v2 pages.

    `g` is build_site's globals(), so the helpers stay defined in one place.
    """
    esc = g["esc"]
    SITE_TITLE = g["SITE_TITLE"]
    log = g["log"]
    estimate_minutes = g["estimate_minutes"]
    week_start = g["week_start"]

    capsule_svg = ('<svg viewBox="0 0 32 32" aria-hidden="true"><g transform="rotate(-38 16 16)">'
                   '<rect x="10" y="2" width="12" height="28" rx="6" fill="none" stroke="currentColor" stroke-width="1.6"/>'
                   '<path d="M10 16V8a6 6 0 0 1 12 0v8z" fill="#C6F432"/></g></svg>')

    def head(title: str, home: bool = False) -> str:
        importmap = f"""
<script type="importmap">{{"imports":{{"three":"{THREE}/build/three.module.min.js","three/addons/":"{THREE}/examples/jsm/"}}}}</script>
<link rel="modulepreload" href="{THREE}/build/three.module.min.js">""" if home else ""
        return f"""<!DOCTYPE html>
<html lang="en" class="no-js">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="A self-running AI learning roadmap built from the Daily Dose of Data Science newsletter. New chapters arrive by themselves, twice a day.">
<meta name="theme-color" content="#0A0F0D">
<script>document.documentElement.classList.replace('no-js','js')</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Inter:wght@400;500;600&family=Manrope:wght@600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{LENIS}/lenis.css">
<style>{CSS}</style>{importmap}
</head>"""

    def nav(base: str, home: bool = False) -> str:
        idx = "" if home else f"{base}index.html"
        links = [
            (f"{idx}#roadmap", "Roadmap"),
            (f"{base}ebook.html", "E-book"),
            (f"{idx}#how", "How it works"),
        ]
        link_html = "".join(f'<a href="{h}"><span class="roll">{t}</span></a>' for h, t in links)
        menu_html = "".join(f'<a href="{h}">{t}</a>' for h, t in links)
        return f"""
<header class="nav">
  <div class="nav-in">
    <a href="{base}index.html" class="nav-logo" aria-label="{SITE_TITLE} home">{capsule_svg}<span>DAILY DOSE</span></a>
    <nav class="nav-links" aria-label="Main">
      {link_html}
      <a href="#" data-open-tutor><span class="roll">AI Tutor</span></a>
      <a href="{REPO}" target="_blank" rel="noopener"><span class="roll">GitHub</span></a>
    </nav>
    <div class="nav-right">
      <a href="{idx}#roadmap" class="pill sm pill-lime nav-cta"><span class="roll">Start learning</span></a>
      <button class="burger" id="burger" aria-label="Open menu" aria-expanded="false"><i></i><i></i></button>
    </div>
  </div>
</header>
<div class="menu" aria-label="Menu">
  {menu_html}
  <a href="#" data-open-tutor>AI Tutor</a>
  <a href="{REPO}" target="_blank" rel="noopener">GitHub</a>
  <div class="mono">Auto-updated twice a day</div>
</div>"""

    def tutor(tutor_ctx_js: str, topic_hint: str = "") -> str:
        hint = f" You are reading: {esc(topic_hint)}." if topic_hint else ""
        return f"""
<button class="fab" id="tutorFab" aria-label="Open the AI tutor">&gt;_ ask the tutor</button>
<div class="tutor" id="tutorPanel" role="dialog" aria-label="AI tutor">
  <div class="tutor-head"><span class="mono">ai-tutor</span><button class="t-close" id="tutorClose" aria-label="Close">&#x2715;</button></div>
  <div class="tutor-hint">Ask about any chapter by number, for example "explain issue #5". Uses your own free Gemini key, saved only in this browser.</div>
  <div class="tutor-body" id="tutorBody"><div class="msg bot">Hi! I know every chapter published so far.{hint}</div></div>
  <div class="chips">
    <span class="chip" data-q="Explain issue #1">issue #1</span>
    <span class="chip" data-q="What topics have been covered?">all topics</span>
    <span class="chip" data-q="Which issues cover LLMs?">llms</span>
  </div>
  <div class="tutor-inp"><input id="tutorIn" placeholder="explain issue #7..." aria-label="Your question"><button class="tsend" id="tSend">run</button></div>
</div>
<script>const TUTOR_CTX={tutor_ctx_js};</script>"""

    def tail(home: bool = False) -> str:
        libs = (f'<script src="{GSAP}/gsap.min.js"></script>'
                f'<script src="{GSAP}/ScrollTrigger.min.js"></script>'
                f'<script src="{GSAP}/SplitText.min.js"></script>'
                f'<script src="{LENIS}/lenis.min.js"></script>')
        home_js = f"<script>{JS_HOME}</script><script type=\"module\">{JS_GL}</script>" if home else ""
        return f"""
<div class="grain" aria-hidden="true"></div>
{libs}
<script>{JS}</script>{home_js}"""

    def footer(base: str, home: bool = False) -> str:
        idx = "" if home else f"{base}index.html"
        return f"""
<footer class="site-foot" data-stage="foot">
  <div class="wrap">
    <div class="foot-grid">
      <div>
        <h4>About</h4>
        <p>An unofficial learning project. Chapters are AI-rewritten study notes from the Daily Dose of Data Science newsletter; all credit for the original ideas goes to its authors. Built by Rishi Singh.</p>
      </div>
      <div><h4>Explore</h4>
        <a href="{idx}#roadmap"><span class="roll">Roadmap</span></a>
        <a href="{base}ebook.html"><span class="roll">E-book</span></a>
        <a href="{idx}#how"><span class="roll">How it works</span></a>
        <a href="#" data-open-tutor><span class="roll">AI Tutor</span></a>
      </div>
      <div><h4>Project</h4>
        <a href="{REPO}" target="_blank" rel="noopener"><span class="roll">Source code</span></a>
        <a href="{REPO}#readme" target="_blank" rel="noopener"><span class="roll">Read me</span></a>
        <a href="https://github.com/Rishichamp" target="_blank" rel="noopener"><span class="roll">Rishi on GitHub</span></a>
      </div>
      <div><h4>Source</h4>
        <a href="https://www.dailydoseofds.com" target="_blank" rel="noopener"><span class="roll">dailydoseofds.com</span></a>
        <a href="https://blog.dailydoseofds.com" target="_blank" rel="noopener"><span class="roll">Newsletter archive</span></a>
      </div>
    </div>
    <div class="foot-word" aria-hidden="true">DAILY DOSE</div>
    <div class="foot-base mono"><span>Updated by itself, twice a day</span><span>No accounts. Bookmarks stay in your browser.</span></div>
  </div>
</footer>"""

    class SiteBuilderV2(Base):

        # ── chapter page ───────────────────────────────────────────────
        def build_entry(self, email, note, tutor_ctx_js: str) -> str:
            safe = re.sub(r'[^\w\s-]', '', note.topic).strip().replace(' ', '-')[:50]
            fname = f"entries/{note.date}_issue{note.issue_number:03d}_{safe}.html"
            fpath = self.out / fname
            d_disp = datetime.strptime(note.date, "%Y-%m-%d").strftime("%d %B %Y")
            mins = estimate_minutes(note)

            blocks = []
            n = 0

            def block(title, inner):
                nonlocal n
                n += 1
                blocks.append(f'<section class="blk"><h2><span class="mono">{n:02d} /</span>'
                              f'<span data-reveal>{esc(title)}</span></h2>{inner}</section>')

            def paras(text):
                return "".join(f"<p>{esc(p)}</p>" for p in text.split("\n") if p.strip())

            if note.overview:
                block("Overview", paras(note.overview))
            for sec in note.sections:
                code = ""
                if sec.get("code"):
                    code = (f'<div class="code-wrap"><div class="code-head"><span class="mono">python</span>'
                            f'<button class="code-copy">Copy</button></div><pre><code>{esc(sec["code"])}</code></pre></div>')
                block(sec.get("title", ""), paras(sec.get("body", "")) + code)
            if note.key_points:
                block("Key takeaways", "<ul>" + "".join(f"<li>{esc(k)}</li>" for k in note.key_points) + "</ul>")
            if note.interview_qs:
                block("Interview questions", "".join(f'<div class="iq">{esc(q)}</div>' for q in note.interview_qs))
            if note.further:
                block("Further reading", "<ul>" + "".join(f"<li>{esc(f)}</li>" for f in note.further) + "</ul>")

            ig_rel = f"../assets/infographics/issue_{note.issue_number:03d}.png"
            ig_abs = self.out / "assets" / "infographics" / f"issue_{note.issue_number:03d}.png"
            if ig_abs.exists():
                share_url = f"https://rishichamp.github.io/daily-dose-site/{fname}"
                block("Chapter infographic", f"""
<p>A one-glance summary of this chapter. Save it and share what you learned.</p>
<div class="ig-frame"><img src="{ig_rel}" alt="Infographic summary of {_attr(note.topic)}" loading="lazy"></div>
<div class="ig-actions">
  <a href="{ig_rel}" download="daily-dose-of-ds-issue-{note.issue_number:03d}.png" class="pill sm pill-lime">Download for LinkedIn</a>
  <a href="https://www.linkedin.com/sharing/share-offsite/?url={share_url}" target="_blank" rel="noopener" class="pill sm">Share on LinkedIn &#x2197;</a>
</div>""")

            tldr = (f'<div class="tldr"><span class="mono">TL;DR</span><p>{esc(note.tldr)}</p></div>'
                    if note.tldr else "")

            html = f"""{head(f"{note.topic} | {SITE_TITLE}")}
<body>
{nav("../")}
<div class="scroll-ind" aria-hidden="true"><i></i></div>
<div class="read-ring" id="readRing" aria-hidden="true"><svg width="46" height="46" viewBox="0 0 48 48"><circle class="rr-bg" cx="24" cy="24" r="20"/><circle class="rr-prog" cx="24" cy="24" r="20"/></svg></div>
<main class="page">
  <header class="ch-hero">
    <div class="ch-meta mono"><span>Issue #{note.issue_number:03d}</span><span>{esc(note.category)}</span><span>{mins} min read</span><span>{d_disp}</span></div>
    <h1 class="ch-title" data-reveal>{esc(note.topic)}</h1>
    <div class="ch-actions">
      <button class="pill sm" id="chapterBookmark">&#x2606; Bookmark</button>
      <button class="pill sm" id="chapterComplete">&#x25CB; Mark complete</button>
      <a class="pill sm pill-ghost" href="../index.html#roadmap">&#x2190; Back to roadmap</a>
    </div>
  </header>
  <article class="ch-body">
    {tldr}
    {''.join(blocks)}
  </article>
</main>
<footer class="ch-foot mono"><a href="../index.html#roadmap"><span class="roll">&#x2190; Back to roadmap</span></a><span>{SITE_TITLE} &#xB7; Issue #{note.issue_number:03d}</span></footer>
{tutor(tutor_ctx_js, note.topic)}
<script>const CURRENT_ISSUE={note.issue_number};</script>
{tail()}
</body></html>"""
            fpath.write_text(html, encoding="utf-8")
            return fname

        # ── landing page ───────────────────────────────────────────────
        def build_index(self, rows_asc, tutor_ctx_js: str):
            """rows_asc: (date, topic, html_file, subject, category, issue_number), oldest first."""
            total = len(rows_asc)
            cat_counts = {}
            for r in rows_asc:
                c = r[4] or "Data Science"
                cat_counts[c] = cat_counts.get(c, 0) + 1
            cats_sorted = sorted(cat_counts.items(), key=lambda kv: (-kv[1], kv[0]))
            latest_date = datetime.fromisoformat(rows_asc[-1][0][:10]).strftime("%d %b %Y") if rows_asc else "-"
            latest_file = rows_asc[-1][2] if rows_asc else "#roadmap"
            built = datetime.now().strftime("%Y-%m-%d")

            # gallery: newest six chapters
            cards = ""
            for date, topic, html_file, subject, category, num in list(reversed(rows_asc))[:6]:
                d = datetime.fromisoformat(date[:10]).strftime("%d %b")
                cards += f"""
<a class="dcard" href="{html_file}">
  <div class="dcard-top mono"><span>{esc(category or "Data Science")}</span><span>{d}</span></div>
  <div><div class="dcard-num">#{(num or 0):03d}</div><h3>{esc(topic.replace("_", " "))}</h3></div>
  <div class="dcard-go mono"><span>Read chapter</span><span aria-hidden="true">&#x2192;</span></div>
</a>"""
            cards += """
<a class="dcard end" href="#roadmap"><span class="mono">All chapters</span><h3>See the full roadmap &#x2192;</h3></a>"""

            steps = "".join(f"""
<div class="step"><i class="c c1"></i><i class="c c2"></i>
  <div class="mono">Step {i:02d}</div><h3>{esc(t)}</h3><p>{esc(d)}</p>
</div>""" for i, (t, d) in enumerate(PIPELINE, 1))

            top = cats_sorted[0][1] if cats_sorted else 1
            readout = "".join(f"""
<button class="rd" type="button" data-jump-cat="{_attr(c)}" aria-label="Show {_attr(c)} chapters in the roadmap">
  <span class="rd-name">{esc(c)}</span><span class="rd-n">{n:03d} &#xB7; {round(n / total * 100) if total else 0}%</span>
  <span class="rd-bar"><i style="--w:{max(4, round(n / top * 100))}%"></i></span>
</button>""" for c, n in cats_sorted)

            ticks = "".join(
                f'<line class="tick" x1="50" y1="{1.5 if k % 5 == 0 else 2.5}" x2="50" y2="5" '
                f'transform="rotate({k * 6} 50 50)" stroke-width="{0.5 if k % 5 == 0 else 0.3}"/>' for k in range(60))

            pills = '<button class="pill sm cat-pill on" data-cat="" aria-pressed="true">All</button>' + "".join(
                f'<button class="pill sm cat-pill" data-cat="{_attr(c)}" aria-pressed="false">{esc(c)} <span class="mono">{n}</span></button>'
                for c, n in cats_sorted)

            # roadmap weeks, oldest first, first week open
            weeks = []
            for row in rows_asc:
                ws = week_start(datetime.fromisoformat(row[0][:10]))
                if not weeks or weeks[-1][0] != ws:
                    weeks.append((ws, []))
                weeks[-1][1].append(row)
            weeks_html = ""
            for wi, (ws, wrows) in enumerate(weeks, 1):
                is_open = wi == 1
                rows_html = ""
                for date, topic, html_file, subject, category, num in wrows:
                    cat = category or "Data Science"
                    d = datetime.fromisoformat(date[:10]).strftime("%d %b %Y")
                    rows_html += f"""
<a class="row" href="{html_file}" data-issue="{num or 0}" data-cat="{_attr(cat)}">
  <span class="row-num">#{(num or 0):03d}</span><span class="row-title">{esc(topic.replace("_", " "))}</span>
  <span class="row-cat">{esc(cat)}</span><span class="row-date">{d}</span>
  <button class="bm" type="button" data-issue="{num or 0}" aria-label="Bookmark chapter {num or 0}">&#x2606;</button>
</a>"""
                n = len(wrows)
                weeks_html += f"""
<div class="wk">
  <button class="wk-head{' open' if is_open else ''}" type="button" aria-expanded="{'true' if is_open else 'false'}">
    <span class="mono">Week {wi:02d}</span><span class="wk-title">Week of {ws.strftime("%d %B %Y")}</span>
    <span class="wk-n mono">{n} chapter{'s' if n != 1 else ''}</span><span class="wk-ico" aria-hidden="true"></span>
  </button>
  <div class="wk-panel{' open' if is_open else ''}"><div>{rows_html}</div></div>
</div>"""
            if not weeks_html:
                weeks_html = ('<div class="rm-empty show"><h3 class="h-md">No chapters yet</h3>'
                              '<p class="lede">Run <code>python build_site.py --first-run</code> to process the archive.</p></div>')

            loader = """
<div id="loader" aria-hidden="true">
  <svg viewBox="0 0 520 240">
    <line class="ld-guide" x1="0" y1="120" x2="520" y2="120"/>
    <line class="ld-guide" x1="260" y1="10" x2="260" y2="230"/>
    <rect class="ld-guide" x="70" y="50" width="380" height="140"/>
    <path class="ld-draw" pathLength="1" d="M140 50 H380 A70 70 0 0 1 380 190 H140 A70 70 0 0 1 140 50 Z"/>
    <path class="ld-draw" pathLength="1" d="M260 50 V190"/>
    <line class="ld-guide" x1="140" y1="50" x2="140" y2="20"/><line class="ld-guide" x1="380" y1="190" x2="380" y2="220"/>
    <rect class="ld-handle" x="136" y="46" width="8" height="8"/><rect class="ld-handle" x="376" y="46" width="8" height="8"/>
    <rect class="ld-handle" x="136" y="186" width="8" height="8"/><rect class="ld-handle" x="376" y="186" width="8" height="8"/>
    <rect class="ld-handle" x="256" y="116" width="8" height="8"/>
    <text class="ld-txt" x="70" y="40">DOSE-01 / CAPSULE</text><text class="ld-txt" x="372" y="214">R = 70</text>
  </svg>
  <div class="ld-pct" id="ldPct">000</div>
  <div class="ld-note mono">Preparing today's dose</div>
</div>"""

            html = f"""{head(f"{SITE_TITLE} | A self-running AI learning roadmap", home=True)}
<body class="home">
{loader}
<canvas id="gl" aria-hidden="true"></canvas>
<div class="edge-glow" aria-hidden="true"></div>
{nav("", home=True)}
<div class="scroll-ind" aria-hidden="true"><i></i></div>
<main>

<section class="hero" id="hero" data-stage="hero">
  <div class="cap-fallback" aria-hidden="true"></div>
  <h1 id="heroLogo"><span class="main">DAILY DOSE</span><span class="sub">of Data Science, rewritten as a roadmap</span></h1>
  <div class="wrap hero-in">
    <div class="hero-copy" id="heroCopy">
      <span class="label">Auto-updated twice a day</span>
      <p class="lede">A self-running AI learning roadmap. Every new Daily Dose of Data Science issue becomes a clean, structured chapter, all by itself.</p>
      <div class="hero-btns">
        <a href="#roadmap" class="pill pill-lime"><span class="roll">Start learning</span> &#x2192;</a>
        <a href="{latest_file}" class="pill"><span class="roll">Read the latest</span></a>
        <a href="ebook.html" class="pill pill-ghost"><span class="roll">Open the e-book</span></a>
      </div>
    </div>
    <div class="hero-stats">
      <div><b>{total}</b><span class="mono">Chapters</span></div>
      <div><b>{len(cat_counts)}</b><span class="mono">Topics</span></div>
      <div><b>{latest_date}</b><span class="mono">Latest</span></div>
    </div>
  </div>
  <div class="scroll-cue mono" aria-hidden="true">Scroll<i></i></div>
</section>

<section class="pitch" id="pitch" data-stage="pitch">
  <div class="wrap">
    <span class="label">Dose-01</span>
    <p id="pitchText">Isn't just a newsletter.</p>
    <h2 id="pitchAi">Rewritten by AI<sup>*</sup></h2>
    <p class="footnote mono">* Gemini reads every issue, strips the ads and turns it into a chapter with a TL;DR, code, takeaways and interview questions.</p>
  </div>
</section>

<section class="daily" id="daily" data-stage="daily">
  <div class="daily-word" id="dailyWord" aria-hidden="true">A new chapter <em>every morning.</em></div>
  <div class="daily-frame" id="dailyFrame" aria-hidden="true"><b></b><b></b><b></b><b></b><span class="frame-tag mono">Fig. 02 / Today's dose</span><span class="frame-dim mono">Latest 6</span></div>
  <div class="daily-track" id="dailyTrack" aria-label="Newest chapters">{cards}</div>
</section>

<section class="how" id="how" data-stage="how">
  <div class="wrap">
    <div class="sec-head"><span class="label">Fig. 03 / Spec sheet</span><h2 class="h-lg" data-reveal>How it runs.<br>By itself.</h2>
      <p class="lede">No one copies, pastes or publishes anything. A scheduled GitHub Actions run does all seven steps.</p></div>
    <div class="how-grid">
      <div class="how-steps"><div class="how-line"><i></i></div>{steps}</div>
      <div class="xray-col" aria-hidden="true"><div class="xray-sticky">
        <div class="callout c-a mono"><b>Shell</b> Gemini rewrite</div>
        <div class="callout c-b mono"><b>Core</b> {total} chapters</div>
        <div class="callout c-c mono"><b>Seal</b> SQLite, committed each run</div>
        <div class="xray-ruler mono"><span>0</span><span>X-ray view</span><span>1:1</span></div>
      </div></div>
    </div>
  </div>
</section>

<section class="decode" id="decode" data-stage="decode">
  <div class="wrap decode-grid">
    <div></div>
    <div>
      <div class="sec-head"><span class="label">Fig. 04 / AI tutor</span><h2 class="h-lg" id="decodeTitle">Decode any chapter.</h2>
        <p class="lede">Ask about any issue by number or topic. The tutor answers from the full chapter index.</p></div>
      <div class="decode-box">
        <div class="decode-bar mono"><span>ai-tutor</span><span>{total} chapters indexed</span></div>
        <div class="decode-screen"><span class="dim">$</span> explain issue #{max(1, total)}<br><span class="dim">&gt; reading the index...</span><br><span class="dim">&gt; answer cites the issue number and date</span></div>
        <form class="decode-form" id="decodeForm">
          <input id="decodeIn" placeholder="explain issue #7" aria-label="Ask the tutor">
          <button class="pill pill-lime" type="submit"><span class="roll">Decode</span></button>
        </form>
      </div>
      <p class="mono" style="color:var(--fg-2);margin-top:14px">Uses your own free Gemini key, saved only in this browser.</p>
    </div>
  </div>
</section>

<section class="topics" id="topics" data-stage="topics">
  <div class="wrap topics-grid">
    <div class="lens" aria-hidden="true">
      <svg viewBox="0 0 100 100">{ticks}<circle cx="50" cy="50" r="38" fill="none" stroke="currentColor" stroke-opacity=".12" stroke-dasharray="1 2"/>
        <line x1="50" y1="12" x2="50" y2="88" stroke="currentColor" stroke-opacity=".12"/><line x1="12" y1="50" x2="88" y2="50" stroke="currentColor" stroke-opacity=".12"/></svg>
      <div class="lens-read mono">Sample: {total} chapters &#xB7; mag 40&#xD7;</div>
    </div>
    <div>
      <div class="sec-head"><span class="label">Fig. 05 / Readout</span><h2 class="h-lg" data-reveal>Topics under the microscope.</h2>
        <p class="lede">Tap a topic to see its chapters in the roadmap.</p></div>
      <div class="readout">{readout}</div>
    </div>
  </div>
</section>

<section class="steady" id="steady" data-stage="steady">
  <div class="wrap">
    <span class="label">Not motivation. A schedule.</span>
    <div id="steadyWord">consistency</div>
    <div class="steady-cards">
      <div class="sc"><span class="mono">Runs</span><b>2&#xD7; a day</b><p>At about 6:53 AM and 7:17 PM IST, every day.</p></div>
      <div class="sc"><span class="mono">Manual steps</span><b>0</b><p>Fetch, rewrite, build and deploy all happen on their own.</p></div>
      <div class="sc"><span class="mono">Chapters so far</span><b>{total}</b><p>And counting. A missed run is retried by the next one.</p></div>
    </div>
  </div>
</section>

<section class="roadmap" id="roadmap" data-stage="roadmap">
  <div class="wrap">
    <div class="sec-head"><span class="label">Fig. 06 / The roadmap</span><h2 class="h-lg" data-reveal>Pick your dose.</h2>
      <p class="lede">Every chapter, week by week. Filter by topic, search by keyword, and star the ones to come back to.</p></div>
    <div class="rm-tools">
      <label class="rm-search"><input id="q" type="search" placeholder="Search chapters" aria-label="Search chapters"><kbd>/</kbd></label>
    </div>
    <div class="rm-pills">{pills}</div>
    <div class="rm-count mono" id="qCount" aria-live="polite"></div>
    <div id="weeks">{weeks_html}</div>
    <div class="rm-empty" id="qEmpty"><h3 class="h-md">No chapters match that search</h3><p class="lede">Try another word, or clear the filter.</p>
      <button class="pill sm" id="qClear" type="button">Clear search</button></div>
  </div>
</section>

<section class="opensrc" id="open" data-stage="opensrc">
  <div class="wrap">
    <div class="sec-head"><span class="label">Fig. 07 / Open source</span><h2 class="h-lg" data-reveal>Read the recipe.</h2></div>
    <div class="term">
      <div class="term-bar"><i></i><i></i><i></i><span class="mono">daily-dose.config</span></div>
<pre><span class="k">$</span> <b>cat daily-dose.config</b>
repo        <b>github.com/Rishichamp/daily-dose-site</b>
source      <b>blog.dailydoseofds.com</b> (public archive)
model       <b>Gemini flash-lite</b>, plain summary if it fails
storage     <b>SQLite</b>, committed with every run
schedule    <b>01:23 and 13:47 UTC</b>, every day
chapters    <b>{total}</b>
built       <b>{built}</b></pre>
      <div class="term-links"><a class="pill sm pill-lime" href="{REPO}" target="_blank" rel="noopener"><span class="roll">View on GitHub</span></a>
        <a class="pill sm" href="{REPO}/blob/main/.github/workflows/daily-update.yml" target="_blank" rel="noopener"><span class="roll">The workflow</span></a></div>
    </div>
  </div>
</section>

</main>
{footer("", home=True)}
{tutor(tutor_ctx_js)}
<script>
document.getElementById('decodeForm').addEventListener('submit',function(e){{e.preventDefault();var v=document.getElementById('decodeIn').value.trim()||'explain issue #{max(1, total)}';window.openTutor(v);}});
</script>
{tail(home=True)}
</body></html>"""
            (self.out / "index.html").write_text(html, encoding="utf-8")
            log.info("Landing page built (design v2) with %d chapters.", total)

        # ── e-book ─────────────────────────────────────────────────────
        def build_ebook_page(self, db):
            rows = db.all_for_ebook()
            toc, chapters = "", ""
            for num, date, topic, note in rows:
                d = datetime.strptime(date[:10], "%Y-%m-%d").strftime("%d %b %Y")
                title = esc(topic.replace("_", " "))
                toc += f'<a href="#ch{num}"><span class="mono">#{num:03d}</span><span>{title}</span><small>{d}</small></a>'
                body = ""
                if note.tldr:
                    body += f'<div class="tldr"><span class="mono">TL;DR</span><p>{esc(note.tldr)}</p></div>'
                if note.overview:
                    body += "<h3>Overview</h3>" + "".join(f"<p>{esc(p)}</p>" for p in note.overview.split("\n") if p.strip())
                for sec in note.sections:
                    body += f'<h3>{esc(sec.get("title", ""))}</h3>' + "".join(
                        f"<p>{esc(p)}</p>" for p in sec.get("body", "").split("\n") if p.strip())
                    if sec.get("code"):
                        body += (f'<div class="code-wrap"><div class="code-head"><span class="mono">python</span>'
                                 f'<button class="code-copy">Copy</button></div><pre><code>{esc(sec["code"])}</code></pre></div>')
                if note.key_points:
                    body += "<h3>Key takeaways</h3><ul>" + "".join(f"<li>{esc(k)}</li>" for k in note.key_points) + "</ul>"
                chapters += f"""
<section class="eb-ch" id="ch{num}">
  <div class="ch-meta mono"><span>Chapter {num:03d}</span><span>{d}</span><span>{esc(note.category)}</span></div>
  <h2>{title}</h2>{body}
  <a class="eb-top mono" href="#toc">&#x2191; Contents</a>
</section>"""
            if not rows:
                chapters = '<p class="lede">No chapters yet. Run <code>python build_site.py --first-run</code> first.</p>'

            html = f"""{head(f"Complete e-book | {SITE_TITLE}")}
<body>
{nav("")}
<div class="scroll-ind" aria-hidden="true"><i></i></div>
<div class="read-ring" id="readRing" aria-hidden="true"><svg width="46" height="46" viewBox="0 0 48 48"><circle class="rr-bg" cx="24" cy="24" r="20"/><circle class="rr-prog" cx="24" cy="24" r="20"/></svg></div>
<main class="page">
  <header class="ch-hero">
    <div class="ch-meta mono"><span>The complete e-book</span><span>{len(rows)} chapters</span><span>Built {datetime.now().strftime("%d %B %Y")}</span></div>
    <h1 class="ch-title" data-reveal>Every dose, in one place.</h1>
  </header>
  <div class="ch-body">
    <div id="toc"><span class="label">Contents</span><div class="toc" style="margin-top:16px">{toc}</div></div>
    {chapters}
  </div>
</main>
<footer class="ch-foot mono"><a href="index.html#roadmap"><span class="roll">&#x2190; Back to roadmap</span></a><span>{SITE_TITLE} e-book</span></footer>
{tutor("''")}
{tail()}
</body></html>"""
            (self.out / "ebook.html").write_text(html, encoding="utf-8")
            log.info("E-book built (design v2) with %d chapters.", len(rows))

    return SiteBuilderV2
