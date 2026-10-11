"""Prototype landing-page hero: a CSS-animated Yoto Mini instead of the video.

Served at /prototype/hero and deliberately kept out of robots/sitemap. The
concept: a Yoto Mini (the yellow adventure-jacket one) on a blue sky. Press
its green side button and the sky turns to sunset while Hamish starts
scanning. There is no card: this is a digital app, so the player itself is
the call to action. Nothing here is wired into the real landing page yet.
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
    --yoto: clamp(190px, 36vmin, 340px);
    --cream: #F7F2E8;
    --cream-2: #E6DDCB;
    --cream-3: #D4C9B4;
    --orange: #FE6601;
    --ink: #1F1A2E;
    --cloud: #FFFFFF;
    --t-sun: 3200ms;
    --ease-sun: cubic-bezier(.45, .05, .25, 1);
}

* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; }
body {
    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #4FB3F6;
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

.sky {
    position: absolute; inset: 0;
    background: linear-gradient(#3FA9F5 0%, #86CFFF 52%, #D9F0FF 100%);
}
.sky-sunset {
    position: absolute; inset: 0;
    background: linear-gradient(#2A1848 0%, #4E2466 24%, #8E3A5F 44%, #D9582F 66%, #F59A2E 84%, #FFD36B 100%);
    opacity: 0;
    transition: opacity var(--t-sun) var(--ease-sun);
}
.is-sunset .sky-sunset { opacity: 1; }

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

.sun {
    position: absolute;
    width: 13vmin; height: 13vmin;
    left: 76%; top: 12%;
    border-radius: 50%;
    background: #FFF6C2;
    box-shadow: 0 0 50px 18px rgba(255, 246, 194, .55);
    transition:
        top var(--t-sun) var(--ease-sun),
        left var(--t-sun) var(--ease-sun),
        transform var(--t-sun) var(--ease-sun),
        background var(--t-sun) var(--ease-sun),
        box-shadow var(--t-sun) var(--ease-sun);
}
.is-sunset .sun {
    left: 14%; top: 64%;
    transform: scale(2.1);
    background: #FFB03A;
    box-shadow: 0 0 70px 30px rgba(255, 150, 50, .55);
}

/* clouds: pill plus two bumps, drifting */
.cloud {
    position: absolute;
    width: 18vmin; height: 5.5vmin;
    background: var(--cloud);
    border-radius: 100px;
    opacity: .95;
    animation: drift linear infinite;
    transition: background var(--t-sun) var(--ease-sun);
}
.cloud::before, .cloud::after {
    content: "";
    position: absolute;
    background: inherit;
    border-radius: 50%;
}
.cloud::before { width: 7vmin; height: 7vmin; left: 18%; top: -58%; }
.cloud::after  { width: 9vmin; height: 9vmin; left: 44%; top: -92%; }
.cloud.c1 { top: 16%; animation-duration: 95s; animation-delay: -30s; }
.cloud.c2 { top: 31%; animation-duration: 120s; animation-delay: -80s; transform: scale(.7); }
.cloud.c3 { top: 44%; animation-duration: 140s; animation-delay: -10s; transform: scale(.85); }
.cloud.c4 { top: 8%;  animation-duration: 110s; animation-delay: -60s; transform: scale(.55); }
@keyframes drift {
    from { left: -25vw; }
    to   { left: 105vw; }
}
.is-sunset { --cloud: #FFB38C; }

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

.ground {
    position: absolute;
    left: -30vw; right: -30vw;
    bottom: -26vh;
    height: 42vh;
    border-radius: 50% 50% 0 0 / 100% 100% 0 0;
    background: #74C476;
    box-shadow: 0 -8px 0 #9ADB8D;
    transition: background var(--t-sun) var(--ease-sun), box-shadow var(--t-sun) var(--ease-sun);
}
.is-sunset .ground {
    background: #2E1E3E;
    box-shadow: 0 -10px 0 #F6A443, 0 -12px 60px 10px rgba(255, 160, 60, .55);
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
.wordmark { width: min(78vw, 420px); height: auto; filter: drop-shadow(0 4px 0 rgba(255,255,255,.55)); }
.tagline {
    margin: .6rem auto 0;
    max-width: 520px;
    color: var(--orange);
    font-family: 'Dream Wish Sans', 'Nunito', sans-serif;
    font-size: clamp(1rem, 2.4vmin, 1.4rem);
    line-height: 1.45;
    text-transform: uppercase;
    transition: color var(--t-sun) var(--ease-sun);
}
.is-sunset .tagline { color: #FFF1D6; }
.is-sunset .wordmark { filter: drop-shadow(0 4px 0 rgba(60, 20, 70, .55)); }

.hint {
    position: absolute;
    left: 50%; bottom: 7%;
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
.yoto {
    position: absolute;
    left: 50%;
    bottom: 16vh;
    width: var(--yoto);
    height: var(--yoto);
    transform: translateX(-50%);
    transform-origin: 50% 100%;
    z-index: 10;
}
.is-pressed .yoto { animation: settle .5s ease-out; }
@keyframes settle {
    0%   { transform: translateX(-50%) scale(1, 1); }
    30%  { transform: translateX(-50%) scale(1.03, .955); }
    65%  { transform: translateX(-50%) scale(.99, 1.015); }
    100% { transform: translateX(-50%) scale(1, 1); }
}

/* the front: a squircle of matte yellow silicone */
.yoto-body {
    position: absolute; inset: 0;
    background: radial-gradient(120% 120% at 25% 15%, #FFCB55 0%, #F7B63A 45%, #E9A223 100%);
    border-radius: 27%;
    box-shadow:
        0 22px 40px rgba(60, 30, 10, .30),
        inset -8px -12px 26px rgba(150, 80, 0, .20),
        inset 8px 10px 22px rgba(255, 240, 190, .35);
    z-index: 3;
}

/* two big ribbed orange buttons */
.btn {
    position: absolute;
    top: 13%;
    width: 31%; height: 31%;
    border-radius: 50%;
    background:
        repeating-linear-gradient(90deg, rgba(255,255,255,0) 0 9%, rgba(255,255,255,.12) 9% 11%, rgba(120,30,10,.10) 11% 13%, rgba(255,255,255,0) 13% 18%),
        radial-gradient(circle at 40% 32%, #FF8A5C 0%, #F2643D 45%, #DE4F2E 100%);
    box-shadow:
        0 0 0 3px rgba(150, 85, 0, .22),
        0 3px 0 rgba(150, 50, 20, .35),
        inset 0 -6px 10px rgba(150, 40, 10, .35),
        inset 0 5px 8px rgba(255, 190, 160, .55);
}
.btn.l { left: 16%; }
.btn.r { right: 16%; }

/* speaker holes, bottom-left, in a rounded diamond */
.grille {
    position: absolute;
    left: 13%; bottom: 13%;
    width: 30%; height: 30%;
    background-image:
        radial-gradient(circle, #4A3115 2.2px, transparent 2.9px),
        radial-gradient(circle, #4A3115 2.2px, transparent 2.9px);
    background-size: 14% 14%;
    background-position: 0 0, 7% 7%;
    -webkit-mask: radial-gradient(circle, #000 58%, transparent 60%);
            mask: radial-gradient(circle, #000 58%, transparent 60%);
}

/* the screen, bottom-right, with its cream bezel */
.screen {
    position: absolute;
    right: 13%; bottom: 13%;
    width: 29%; height: 29%;
    background: #141120;
    border-radius: 18%;
    box-shadow:
        0 0 0 3px #F3E8D2,
        0 0 0 4.5px rgba(120, 70, 0, .25),
        inset 0 0 12px rgba(0,0,0,.9);
    overflow: hidden;
}
.screen .face {
    position: absolute; inset: 10%;
    width: 80%; height: 80%;
    object-fit: contain;
    opacity: .9;
    transition: opacity .4s;
}
.is-sunset .screen .face { opacity: 0; }

/* a glowing top-down pixel plane, one unit per pixel on an 11x9 grid */
.pixel-plane {
    --u: calc(var(--yoto) * 0.021);
    position: absolute;
    left: 12%; top: 10%;
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

/* the green side button is the play control */
.side-btn {
    position: absolute;
    right: -5%; top: 61%;
    width: 12%; height: 18%;
    border: 0; padding: 0;
    border-radius: 50%;
    background: radial-gradient(circle at 40% 35%, #4DBB72, #2E9A57 60%, #237A44);
    box-shadow: 0 3px 6px rgba(0,0,0,.25), 0 0 0 0 rgba(77, 187, 114, 0);
    cursor: pointer;
    z-index: 2;
    transform-origin: 0% 50%;
    transition: transform .12s ease-out, box-shadow .3s;
    -webkit-appearance: none;
    appearance: none;
}
.side-btn:hover { transform: scaleX(1.12); }
.side-btn:focus-visible { outline: 3px solid #fff; outline-offset: 3px; }
.side-btn.pressed { animation: press .32s ease-out; }
@keyframes press {
    0%   { transform: scaleX(1); }
    35%  { transform: scaleX(.55); }
    100% { transform: scaleX(1); }
}
/* a soft pulse until it has been pressed once */
.hero:not(.is-sunset) .side-btn { animation: beckon 1.8s ease-in-out infinite; }
@keyframes beckon {
    50% { box-shadow: 0 3px 6px rgba(0,0,0,.25), 0 0 0 10px rgba(77, 187, 114, .28); }
}

@media (max-width: 640px) {
    :root { --yoto: clamp(170px, 56vw, 260px); }
    .yoto { bottom: 15vh; }
    .copy { top: 5%; }
    .cloud { transform: scale(.8); }
    .sun { width: 16vmin; height: 16vmin; left: 72%; top: 24%; }
    .is-sunset .sun { left: 4%; top: 62%; transform: scale(1.5); }
}

@media (prefers-reduced-motion: reduce) {
    .cloud, .is-pressed .yoto, .is-sunset .plane, .hint, .stars, .side-btn, .pixel-plane { animation: none !important; }
    .sun, .sky-sunset, .ground, .tagline, .cloud { transition-duration: 1ms; }
}
</style>
</head>
<body>
<section class="hero" id="hero" aria-label="Dreaming of a Jet Plane on a Yoto Mini">
    <div class="sky"></div>
    <div class="sky-sunset"></div>
    <div class="stars"></div>
    <div class="sun"></div>
    <div class="cloud c1"></div>
    <div class="cloud c2"></div>
    <div class="cloud c3"></div>
    <div class="cloud c4"></div>
    <div class="plane" aria-hidden="true"><div class="trail"></div><div class="body"></div><div class="wing"></div></div>
    <div class="ground"></div>

    <div class="copy">
        <img class="wordmark" src="/assets/img/wordmark.png" alt="Dreaming of a Jet Plane">
        <p class="tagline">Magically turn your Yoto into a Jet Plane Scanner that finds planes in the skies around you.</p>
    </div>

    <div class="yoto" id="yoto">
        <button class="side-btn" id="play" type="button" aria-label="Play"></button>
        <div class="yoto-body">
            <div class="btn l"></div>
            <div class="btn r"></div>
            <div class="grille"></div>
            <div class="screen">
                <img class="face" src="/assets/img/yoto.png" alt="">
                <div class="pixel-plane"></div>
                <div class="eq"><i></i><i></i><i></i><i></i><i></i><i></i></div>
            </div>
        </div>
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
