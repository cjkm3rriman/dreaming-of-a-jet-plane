"""Prototype landing-page hero: a CSS-animated Yoto Mini instead of the video.

Served at /prototype/hero and deliberately kept out of robots/sitemap. The
concept: a Yoto Mini on a blue sky. Press its green side button and the sky
turns to sunset while Hamish starts scanning. No card: this is a digital
app, so the player itself is the call to action.

The player is Yoto's own product render, cut out of its flat background
(assets/img/prototype/yoto-mini.webp). Only two things sit on top of it:
a live screen drawn in CSS over the real screen's rectangle, and the green
button as its own layer so it can be pressed. Nothing here is wired into
the real landing page yet.
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

SCANNING_CLIP = "https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/edward/scanning.mp3"

HERO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Hero prototype - Dreaming of a Jet Plane</title>
<link rel="icon" type="image/png" href="/assets/img/icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@600;800&display=swap" rel="stylesheet">
<style>
@font-face {
    font-family: 'Dream Wish Sans';
    src: url('/assets/fonts/DreamWishSansRegular.woff2') format('woff2'),
         url('/assets/fonts/DreamWishSansRegular.woff') format('woff');
    font-weight: 400;
    font-style: normal;
    font-display: swap;
}

:root {
    --yoto: clamp(200px, 38vmin, 360px);
    --orange: #FE6601;
    --ink: #1F1A2E;
    --t-sun: 3200ms;
    --ease-sun: cubic-bezier(.45, .05, .25, 1);
}

* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; }
body {
    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #5EC3F2;
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
}

/* ---------- scene ---------- */
.hero {
    position: relative;
    width: 100%;
    height: 100dvh;
    min-height: 540px;
    overflow: hidden;
    user-select: none;
    -webkit-tap-highlight-color: transparent;
}

/* day sky: a photo (placeholder stock preview; needs licensing before it
   ships). At sunset the same photo is warmed so the clouds stay. */
.sky {
    position: absolute; inset: 0;
    background: #3F8FE0 url('/assets/img/prototype/sky.jpg') center bottom / cover no-repeat;
    transition: filter var(--t-sun) var(--ease-sun);
}
.is-sunset .sky { filter: sepia(.95) saturate(2.4) hue-rotate(-28deg) brightness(.72) contrast(1.1); }
.sky-sunset {
    position: absolute; inset: 0;
    background: linear-gradient(#2A1848 0%, #4E2466 24%, #8E3A5F 44%, #D9582F 66%, #F59A2E 84%, #FFD36B 100%);
    opacity: 0;
    transition: opacity var(--t-sun) var(--ease-sun);
}
.is-sunset .sky-sunset { opacity: .62; }

.stars {
    position: absolute; inset: 0 0 40% 0;
    background-image:
        radial-gradient(1.5px 1.5px at 12% 18%, #fff 50%, transparent 55%),
        radial-gradient(1.2px 1.2px at 28% 8%,  #fff 50%, transparent 55%),
        radial-gradient(1.8px 1.8px at 41% 26%, #fff 50%, transparent 55%),
        radial-gradient(1.2px 1.2px at 57% 12%, #fff 50%, transparent 55%),
        radial-gradient(1.6px 1.6px at 66% 31%, #fff 50%, transparent 55%),
        radial-gradient(1.3px 1.3px at 79% 6%,  #fff 50%, transparent 55%),
        radial-gradient(1.8px 1.8px at 88% 22%, #fff 50%, transparent 55%),
        radial-gradient(1.2px 1.2px at 94% 40%, #fff 50%, transparent 55%),
        radial-gradient(1.4px 1.4px at 6% 44%,  #fff 50%, transparent 55%),
        radial-gradient(1.2px 1.2px at 35% 48%, #fff 50%, transparent 55%);
    opacity: 0;
    transition: opacity calc(var(--t-sun) * 1.4) ease-in;
    transition-delay: 600ms;
}
.is-sunset .stars { opacity: .9; }
.is-sunset .stars { animation: twinkle 3.2s ease-in-out infinite alternate; animation-delay: 2.5s; }
@keyframes twinkle { from { opacity: .55; } to { opacity: 1; } }

/* the sun: no sun by day; at sunset it glows on the horizon */
.sun {
    position: absolute;
    width: 13vmin; height: 13vmin;
    left: 14%; top: 64%;
    border-radius: 50%;
    background: #FFB03A;
    box-shadow: 0 0 70px 30px rgba(255, 150, 50, .55);
    transform: scale(2.1);
    opacity: 0;
    transition: opacity var(--t-sun) var(--ease-sun);
}
.is-sunset .sun { opacity: 1; }

/* a plane crossing the sunset sky */
.plane {
    position: absolute;
    top: 20%; left: -22vw;
    width: 9vmin; height: 2.1vmin;
    opacity: 0;
}
.is-sunset .plane { animation: fly 18s linear infinite 1.6s; }
.plane .body {
    position: absolute; inset: 0;
    background: #FFF4E6;
    border-radius: 100px 100px 100px 100px / 60% 60% 60% 60%;
    box-shadow: inset 0 -0.6vmin 0 rgba(200, 80, 60, .35);
}
.plane .body::after {
    /* tail fin */
    content: "";
    position: absolute;
    right: 2%; top: -115%;
    width: 24%; height: 130%;
    background: #E5443A;
    clip-path: polygon(100% 0, 100% 100%, 0 100%);
}
.plane .wing {
    position: absolute;
    left: 34%; top: 55%;
    width: 34%; height: 1.6vmin;
    background: #F2D2B8;
    transform: skewX(-48deg);
    z-index: 1;
    border-radius: 2px;
}
.plane .trail {
    position: absolute;
    right: 95%; top: 42%;
    width: 36vmin; height: .6vmin;
    border-radius: 100px;
    background: linear-gradient(to left, rgba(255,255,255,.75), rgba(255,255,255,0));
}
@keyframes fly {
    0%   { opacity: 0; transform: translate(0, 0); }
    4%   { opacity: 1; }
    92%  { opacity: 1; }
    100% { opacity: 0; transform: translate(150vw, -9vh); }
}

/* ---------- copy ---------- */
.copy {
    position: absolute;
    left: 50%; top: 6%;
    transform: translateX(-50%);
    width: min(92vw, 640px);
    text-align: center;
    z-index: 20;
    pointer-events: none;
}
.wordmark { width: min(60vw, 300px); height: auto; }

.hint {
    position: absolute;
    left: 50%; bottom: 3%;
    transform: translateX(-50%);
    z-index: 20;
    padding: .6rem 1.1rem;
    border-radius: 100px;
    background: rgba(255,255,255,.85);
    color: var(--ink);
    font-weight: 800;
    font-size: .95rem;
    letter-spacing: .02em;
    box-shadow: 0 6px 20px rgba(20, 40, 80, .18);
    animation: pulse 1.8s ease-in-out infinite;
    opacity: 0;
    transition: opacity .4s;
    pointer-events: none;
}
.hint.show { opacity: 1; }
.hint.replay { pointer-events: auto; animation: none; cursor: pointer; }
@keyframes pulse { 50% { transform: translateX(-50%) scale(1.05); } }

/* ---------- the yoto mini ---------- */
/* The product render, with the screen and the green button measured as
   percentages of the cutout so the overlays land exactly on the photo. */
.yoto {
    position: absolute;
    left: 50%;
    bottom: 12vh;
    width: var(--yoto);
    aspect-ratio: 793 / 746;
    transform: translateX(-50%);
    transform-origin: 50% 100%;
    z-index: 10;
}
.is-pressed .yoto { animation: settle .5s ease-out; }
@keyframes settle {
    0%   { transform: translateX(-50%) scale(1, 1); }
    30%  { transform: translateX(-50%) scale(1.02, .97); }
    65%  { transform: translateX(-50%) scale(.995, 1.01); }
    100% { transform: translateX(-50%) scale(1, 1); }
}
.shell {
    position: absolute; inset: 0;
    width: 100%; height: 100%;
    display: block;
    filter: drop-shadow(0 26px 28px rgba(20, 10, 40, .32));
    pointer-events: none;
    user-select: none;
    -webkit-user-drag: none;
}

/* The live screen sits over the photo's screen. Idle, it is invisible and the
   render's own sun-and-clouds clock shows through; it fades in on press. */
.screen {
    position: absolute;
    left: 51.7%; top: 55.0%;
    width: 29.3%; height: 31.0%;
    background: #0C0A0F;
    border-radius: 22%;
    box-shadow: inset 0 0 10px rgba(0,0,0,.9);
    overflow: hidden;
    opacity: 0;
    transition: opacity .5s ease-out;
}
.is-sunset .screen { opacity: 1; }

/* a glowing top-down pixel plane, one unit per pixel on an 11x9 grid */
.pixel-plane {
    --u: calc(var(--yoto) * 0.0215);
    position: absolute;
    left: 12%; top: 11%;
    width: var(--u); height: var(--u);
    opacity: 0;
    transition: opacity .3s;
    filter: drop-shadow(0 0 3px rgba(150, 190, 255, .8));
}
.pixel-plane::before {
    content: "";
    position: absolute;
    width: 100%; height: 100%;
    background: transparent;
    box-shadow:
        calc(var(--u) * 5) calc(var(--u) * 0) #F4F6FF,
        calc(var(--u) * 5) calc(var(--u) * 1) #F4F6FF,
        calc(var(--u) * 5) calc(var(--u) * 2) #F4F6FF,
        calc(var(--u) * 5) calc(var(--u) * 3) #F4F6FF,
        calc(var(--u) * 5) calc(var(--u) * 4) #F4F6FF,
        calc(var(--u) * 5) calc(var(--u) * 5) #F4F6FF,
        calc(var(--u) * 5) calc(var(--u) * 6) #F4F6FF,
        calc(var(--u) * 5) calc(var(--u) * 7) #F4F6FF,
        calc(var(--u) * 4) calc(var(--u) * 2) #F4F6FF,
        calc(var(--u) * 6) calc(var(--u) * 2) #F4F6FF,
        calc(var(--u) * 4) calc(var(--u) * 3) #F4F6FF,
        calc(var(--u) * 6) calc(var(--u) * 3) #F4F6FF,
        calc(var(--u) * 4) calc(var(--u) * 4) #F4F6FF,
        calc(var(--u) * 6) calc(var(--u) * 4) #F4F6FF,
        calc(var(--u) * 4) calc(var(--u) * 5) #F4F6FF,
        calc(var(--u) * 6) calc(var(--u) * 5) #F4F6FF,
        calc(var(--u) * 4) calc(var(--u) * 6) #F4F6FF,
        calc(var(--u) * 6) calc(var(--u) * 6) #F4F6FF,
        calc(var(--u) * 1) calc(var(--u) * 4) #F4F6FF,
        calc(var(--u) * 2) calc(var(--u) * 4) #F4F6FF,
        calc(var(--u) * 3) calc(var(--u) * 4) #F4F6FF,
        calc(var(--u) * 4) calc(var(--u) * 4) #F4F6FF,
        calc(var(--u) * 5) calc(var(--u) * 4) #F4F6FF,
        calc(var(--u) * 6) calc(var(--u) * 4) #F4F6FF,
        calc(var(--u) * 7) calc(var(--u) * 4) #F4F6FF,
        calc(var(--u) * 8) calc(var(--u) * 4) #F4F6FF,
        calc(var(--u) * 9) calc(var(--u) * 4) #F4F6FF,
        calc(var(--u) * 2) calc(var(--u) * 5) #8FB4FF,
        calc(var(--u) * 3) calc(var(--u) * 5) #8FB4FF,
        calc(var(--u) * 4) calc(var(--u) * 5) #8FB4FF,
        calc(var(--u) * 5) calc(var(--u) * 5) #8FB4FF,
        calc(var(--u) * 6) calc(var(--u) * 5) #8FB4FF,
        calc(var(--u) * 7) calc(var(--u) * 5) #8FB4FF,
        calc(var(--u) * 8) calc(var(--u) * 5) #8FB4FF,
        calc(var(--u) * 0) calc(var(--u) * 4) #FF5F5F,
        calc(var(--u) * 10) calc(var(--u) * 4) #4CD964,
        calc(var(--u) * 3) calc(var(--u) * 8) #F4F6FF,
        calc(var(--u) * 4) calc(var(--u) * 8) #F4F6FF,
        calc(var(--u) * 5) calc(var(--u) * 8) #F4F6FF,
        calc(var(--u) * 6) calc(var(--u) * 8) #F4F6FF,
        calc(var(--u) * 7) calc(var(--u) * 8) #F4F6FF,
        calc(var(--u) * 5) calc(var(--u) * 1) #8FB4FF;
}
.is-sunset .pixel-plane { opacity: 1; animation: hover-px 1.4s steps(2) infinite; }
@keyframes hover-px { 50% { transform: translateY(-5%); } }

.eq {
    position: absolute;
    left: 14%; right: 14%; bottom: 8%;
    height: 18%;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    opacity: 0;
    transition: opacity .3s;
}
.is-playing .eq { opacity: 1; }
.eq i {
    width: 11%;
    height: 30%;
    background: #9CC4FF;
    border-radius: 1px;
    animation: bars .8s ease-in-out infinite alternate;
}
.eq i:nth-child(2) { animation-delay: -.2s; } .eq i:nth-child(3) { animation-delay: -.5s; }
.eq i:nth-child(4) { animation-delay: -.1s; } .eq i:nth-child(5) { animation-delay: -.35s; }
.eq i:nth-child(6) { animation-delay: -.6s; }
@keyframes bars { from { height: 18%; } to { height: 100%; } }
.hero:not(.is-playing) .eq i { animation-play-state: paused; }

/* the green side button, as its own layer, is the play control */
.side-btn {
    position: absolute;
    left: 87.5%; top: 54.8%;
    width: 12.2%; height: 30.4%;
    border: 0; padding: 0;
    background: url('/assets/img/prototype/yoto-mini-button.webp') center / contain no-repeat;
    cursor: pointer;
    z-index: 2;
    transform-origin: 20% 50%;
    transition: transform .12s ease-out, filter .12s;
    -webkit-appearance: none;
    appearance: none;
    -webkit-tap-highlight-color: transparent;
}
.side-btn:hover { transform: scale(1.04); filter: brightness(1.06); }
.side-btn:focus-visible { outline: 3px solid #fff; outline-offset: 4px; border-radius: 50%; }
.side-btn.pressed { animation: press .3s ease-out; }
@keyframes press {
    0%   { transform: scale(1); filter: brightness(1); }
    35%  { transform: scale(.88, .94); filter: brightness(.85); }
    100% { transform: scale(1); filter: brightness(1); }
}
/* a soft pulse until it has been pressed once */
.side-btn::after {
    content: "";
    position: absolute; inset: 6% 8%;
    border-radius: 50%;
    box-shadow: 0 0 0 0 rgba(77, 187, 114, 0);
    pointer-events: none;
}
.hero:not(.is-sunset) .side-btn::after { animation: beckon 1.8s ease-in-out infinite; }
@keyframes beckon {
    50% { box-shadow: 0 0 0 12px rgba(77, 187, 114, .3); }
}

@media (max-width: 640px) {
    :root { --yoto: clamp(180px, 56vw, 260px); }
    .yoto { bottom: 14vh; }
    .is-sunset .sun { left: 4%; top: 62%; }
    .sun { transform: scale(1.5); }
}

@media (prefers-reduced-motion: reduce) {
    .is-pressed .yoto, .is-sunset .plane, .hint, .stars, .side-btn, .side-btn::after, .pixel-plane { animation: none !important; }
    .sun, .sky, .sky-sunset { transition-duration: 1ms; }
}
</style>
</head>
<body>
<section class="hero" id="hero" aria-label="Dreaming of a Jet Plane on a Yoto Mini">
    <div class="sky"></div>
    <div class="sky-sunset"></div>
    <div class="stars"></div>
    <div class="sun"></div>
    <div class="plane" aria-hidden="true"><div class="trail"></div><div class="body"></div><div class="wing"></div></div>

    <div class="copy">
        <img class="wordmark" src="/assets/img/wordmark.png" alt="Dreaming of a Jet Plane">
    </div>

    <div class="yoto" id="yoto">
        <img class="shell" src="/assets/img/prototype/yoto-mini.webp" alt="A Yoto Mini player" draggable="false">
        <div class="screen">
            <div class="pixel-plane"></div>
            <div class="eq"><i></i><i></i><i></i><i></i><i></i><i></i></div>
        </div>
        <button class="side-btn" id="play" type="button" aria-label="Play"></button>
    </div>

    <div class="hint" id="hint">Press the green button</div>
    <audio id="narration" preload="auto" src="__CLIP__"></audio>
</section>

<script>
(function () {
    const hero = document.getElementById('hero');
    const btn = document.getElementById('play');
    const hint = document.getElementById('hint');
    const audio = document.getElementById('narration');

    function showHint(text, replay) {
        hint.textContent = text;
        hint.classList.toggle('replay', !!replay);
        hint.classList.add('show');
    }
    function hideHint() { hint.classList.remove('show', 'replay'); }

    function press() {
        btn.classList.remove('pressed');
        hero.classList.remove('is-pressed');
        void btn.offsetWidth;
        btn.classList.add('pressed');
        hero.classList.add('is-pressed');
    }

    btn.addEventListener('click', () => {
        press();
        if (audio.paused) {
            // First press: the sky turns to sunset while Hamish warms up
            hero.classList.add('is-sunset');
            if (audio.ended) audio.currentTime = 0;
            hideHint();
            audio.play().catch(() => showHint('Press again for sound'));
        } else {
            audio.pause();
            showHint('Press the green button to resume');
        }
    });

    audio.addEventListener('play', () => hero.classList.add('is-playing'));
    audio.addEventListener('pause', () => hero.classList.remove('is-playing'));
    audio.addEventListener('ended', () => {
        hero.classList.remove('is-playing');
        showHint('Play it again', true);
    });
    hint.addEventListener('click', () => { if (hint.classList.contains('replay')) btn.click(); });

    showHint('Press the green button');
})();
</script>
</body>
</html>
""".replace("__CLIP__", SCANNING_CLIP)


def register_hero_prototype_routes(app: FastAPI) -> None:
    @app.get("/prototype/hero", response_class=HTMLResponse, include_in_schema=False)
    async def hero_prototype():
        return HTMLResponse(content=HERO_HTML)
