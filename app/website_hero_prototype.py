"""Prototype landing-page hero: a CSS-animated Yoto Mini instead of the video.

Served at /prototype/hero and deliberately kept out of robots/sitemap. The
concept: a Yoto Mini on a blue sky, the Dreaming of a Jet Plane card drops
into the slot, the sky turns to sunset, and Hamish starts scanning. Nothing
here is wired into the real landing page yet.
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
    --yoto: clamp(190px, 38vmin, 360px);
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
    cursor: pointer;
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
    bottom: 17vh;
    width: var(--yoto);
    height: var(--yoto);
    transform: translateX(-50%);
    transform-origin: 50% 100%;
    z-index: 10;
}
.is-dropping .yoto { animation: settle .55s ease-out .66s; }
@keyframes settle {
    0%   { transform: translateX(-50%) scale(1, 1); }
    30%  { transform: translateX(-50%) scale(1.03, .955); }
    65%  { transform: translateX(-50%) scale(.99, 1.015); }
    100% { transform: translateX(-50%) scale(1, 1); }
}

/* top face: knobs and the slot */
.yoto-top {
    position: absolute;
    left: 3%; right: 3%;
    top: -8%;
    height: 15%;
    background: linear-gradient(var(--cream-2), var(--cream-3));
    border-radius: 14% 14% 6% 6% / 60% 60% 30% 30%;
    z-index: 1;
}
.knob {
    position: absolute;
    top: -40%;
    width: 16%; height: 78%;
    background: linear-gradient(#FF8A3D, var(--orange) 55%, #D85200);
    border-radius: 45% / 50%;
    box-shadow: 0 3px 0 #B84400, inset 0 2px 0 rgba(255,255,255,.4);
}
.knob.l { left: 9%; }
.knob.r { right: 9%; }
.slot {
    position: absolute;
    left: 34%; width: 32%;
    top: 30%; height: 16%;
    background: #241C2E;
    border-radius: 3px;
    box-shadow: inset 0 2px 2px rgba(0,0,0,.6);
}

/* the front */
.yoto-body {
    position: absolute; inset: 0;
    background: linear-gradient(170deg, #FBF7F0, var(--cream) 60%, #EFE8DA);
    border-radius: 17%;
    box-shadow:
        0 22px 40px rgba(20, 10, 40, .28),
        inset 0 -10px 0 rgba(0,0,0,.05),
        inset 0 2px 0 rgba(255,255,255,.8);
    z-index: 3;
}
.screen {
    position: absolute;
    left: 10%; top: 11%;
    width: 36%; height: 36%;
    background: #110E14;
    border-radius: 12%;
    box-shadow: inset 0 0 0 3px #2A2330, inset 0 0 14px rgba(0,0,0,.9);
    overflow: hidden;
}
.screen .face {
    position: absolute; inset: 8%;
    width: 84%; height: 84%;
    object-fit: contain;
    opacity: .9;
    transition: opacity .4s;
}
.is-sunset .screen .face { opacity: 0; }

/* pixel plane drawn with box-shadow, one unit per pixel on a 12x8 grid */
.pixel-plane {
    --u: calc(var(--yoto) * 0.026);
    position: absolute;
    left: 8%; top: 20%;
    width: var(--u); height: var(--u);
    background: transparent;
    opacity: 0;
    transition: opacity .3s;
}
.pixel-plane::before {
    content: "";
    position: absolute;
    width: 100%; height: 100%;
    background: var(--orange);
    /* 11x7 side profile, nose to the right */
    box-shadow:
        calc(var(--u) * 1) calc(var(--u) * 0) var(--orange),
        calc(var(--u) * 1) calc(var(--u) * 1) var(--orange),
        calc(var(--u) * 2) calc(var(--u) * 1) var(--orange),
        calc(var(--u) * 1) calc(var(--u) * 2) var(--orange),
        calc(var(--u) * 2) calc(var(--u) * 2) var(--orange),
        calc(var(--u) * 3) calc(var(--u) * 2) var(--orange),
        calc(var(--u) * 7) calc(var(--u) * 2) var(--orange),
        calc(var(--u) * 8) calc(var(--u) * 2) var(--orange),
        calc(var(--u) * 0) calc(var(--u) * 3) var(--orange),
        calc(var(--u) * 1) calc(var(--u) * 3) var(--orange),
        calc(var(--u) * 2) calc(var(--u) * 3) var(--orange),
        calc(var(--u) * 3) calc(var(--u) * 3) var(--orange),
        calc(var(--u) * 4) calc(var(--u) * 3) var(--orange),
        calc(var(--u) * 5) calc(var(--u) * 3) var(--orange),
        calc(var(--u) * 6) calc(var(--u) * 3) var(--orange),
        calc(var(--u) * 7) calc(var(--u) * 3) var(--orange),
        calc(var(--u) * 8) calc(var(--u) * 3) var(--orange),
        calc(var(--u) * 9) calc(var(--u) * 3) var(--orange),
        calc(var(--u) * 10) calc(var(--u) * 3) var(--orange),
        calc(var(--u) * 4) calc(var(--u) * 4) var(--orange),
        calc(var(--u) * 5) calc(var(--u) * 4) var(--orange),
        calc(var(--u) * 6) calc(var(--u) * 4) var(--orange),
        calc(var(--u) * 3) calc(var(--u) * 5) var(--orange),
        calc(var(--u) * 4) calc(var(--u) * 5) var(--orange),
        calc(var(--u) * 2) calc(var(--u) * 6) var(--orange)
}
.is-sunset .pixel-plane { opacity: 1; animation: hover-px 1.4s steps(2) infinite; }
@keyframes hover-px { 50% { transform: translateY(-7%); } }

.eq {
    position: absolute;
    left: 14%; right: 14%; bottom: 10%;
    height: 22%;
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
    background: #FFC46B;
    border-radius: 1px;
    animation: bars .8s ease-in-out infinite alternate;
}
.eq i:nth-child(2) { animation-delay: -.2s; } .eq i:nth-child(3) { animation-delay: -.5s; }
.eq i:nth-child(4) { animation-delay: -.1s; } .eq i:nth-child(5) { animation-delay: -.35s; }
.eq i:nth-child(6) { animation-delay: -.6s; }
@keyframes bars { from { height: 18%; } to { height: 100%; } }
.is-playing .eq i { animation-play-state: running; }
.hero:not(.is-playing) .eq i { animation-play-state: paused; }

.grille {
    position: absolute;
    background-image: radial-gradient(circle, rgba(40, 25, 20, .26) 1.3px, transparent 1.9px);
    background-size: 6.5% 6.5%;
}
.grille.right  { left: 54%; right: 10%; top: 12%; height: 35%; }
.grille.bottom { left: 10%; right: 10%; top: 56%; bottom: 11%; }

/* the card */
.card {
    position: absolute;
    left: 50%;
    top: -18%;
    width: 24%;
    aspect-ratio: 54 / 86;
    border-radius: 6% / 4%;
    background:
        url('/assets/img/prototype/dojp-card.jpg') center top / 100% auto no-repeat,
        linear-gradient(#F9B64B, #E65A2B 40%, #7A2E58);
    box-shadow: 0 6px 18px rgba(20, 10, 40, .35), inset 0 0 0 1.5px rgba(255,255,255,.35);
    z-index: 2;
    transform: translate(-50%, -40%) rotate(-7deg);
    animation: bob 2.6s ease-in-out infinite;
    will-change: transform;
}
@keyframes bob {
    50% { transform: translate(-50%, -48%) rotate(-5deg); }
}
.is-dropping .card { animation: drop 1.15s forwards; }
@keyframes drop {
    0%   { transform: translate(-50%, -120vh) rotate(-14deg); animation-timing-function: cubic-bezier(.5, 0, .9, .45); }
    58%  { transform: translate(-50%, 3%) rotate(0deg); animation-timing-function: ease-out; }
    76%  { transform: translate(-50%, -6%) rotate(0deg); animation-timing-function: ease-in; }
    100% { transform: translate(-50%, 0) rotate(0deg); }
}

@media (max-width: 640px) {
    :root { --yoto: clamp(170px, 56vw, 260px); }
    .yoto { bottom: 16vh; }
    .copy { top: 5%; }
    .cloud { transform: scale(.8); }
    .sun { width: 16vmin; height: 16vmin; left: 72%; top: 24%; }
    .is-sunset .sun { left: 4%; top: 62%; transform: scale(1.5); }
}

@media (prefers-reduced-motion: reduce) {
    .card, .is-dropping .card, .cloud, .is-dropping .yoto, .is-sunset .plane, .hint, .stars { animation: none !important; }
    .card { transform: translate(-50%, 0) rotate(0); }
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
        <div class="card" id="card" aria-hidden="true"></div>
        <div class="yoto-top">
            <div class="knob l"></div>
            <div class="slot"></div>
            <div class="knob r"></div>
        </div>
        <div class="yoto-body">
            <div class="screen">
                <img class="face" src="/assets/img/yoto.png" alt="">
                <div class="pixel-plane"></div>
                <div class="eq"><i></i><i></i><i></i><i></i><i></i><i></i></div>
            </div>
            <div class="grille right"></div>
            <div class="grille bottom"></div>
        </div>
    </div>

    <div class="hint" id="hint">Tap to drop the card</div>
    <audio id="narration" preload="auto" src="__CLIP__"></audio>
</section>

<script>
(function () {
    const hero = document.getElementById('hero');
    const card = document.getElementById('card');
    const hint = document.getElementById('hint');
    const audio = document.getElementById('narration');
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let state = 'idle'; // idle -> dropping -> sunset -> done

    function showHint(text, replay) {
        hint.textContent = text;
        hint.classList.toggle('replay', !!replay);
        hint.classList.add('show');
    }
    function hideHint() { hint.classList.remove('show', 'replay'); }

    function begin() {
        if (state !== 'idle') return;
        state = 'dropping';
        hideHint();
        if (reduced) { landed(); return; }
        hero.classList.add('is-dropping');
    }

    function landed() {
        state = 'sunset';
        hero.classList.add('is-dropping', 'is-sunset');
        audio.currentTime = 0;
        audio.play()
            .then(() => hero.classList.add('is-playing'))
            .catch(() => showHint('Tap for sound'));
    }

    card.addEventListener('animationend', (e) => {
        if (e.animationName === 'drop' && state === 'dropping') landed();
    });

    audio.addEventListener('play', () => hero.classList.add('is-playing'));
    audio.addEventListener('pause', () => hero.classList.remove('is-playing'));
    audio.addEventListener('ended', () => {
        state = 'done';
        hero.classList.remove('is-playing');
        showHint('Play it again', true);
    });

    function reset() {
        audio.pause();
        hero.className = 'hero';
        state = 'idle';
        hideHint();
        // force a reflow so the drop animation can replay from the top
        void card.offsetWidth;
        begin();
    }

    hero.addEventListener('click', () => {
        if (state === 'idle') return begin();
        if (state === 'sunset' && audio.paused) {
            audio.play().then(hideHint).catch(() => {});
            return;
        }
        if (state === 'done') reset();
    });
    hero.addEventListener('keydown', (e) => {
        if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); hero.click(); }
    });
    hero.tabIndex = 0;

    // Autoplay probe: if the browser lets us play with sound, run the whole
    // sequence unprompted; otherwise wait for a tap, like the video did.
    const probe = audio.play();
    if (probe && probe.then) {
        probe.then(() => {
            audio.pause();
            audio.currentTime = 0;
            setTimeout(begin, 900);
        }).catch(() => showHint('Tap to drop the card'));
    } else {
        showHint('Tap to drop the card');
    }
})();
</script>
</body>
</html>
""".replace("__CLIP__", SCANNING_CLIP)


def register_hero_prototype_routes(app: FastAPI) -> None:
    @app.get("/prototype/hero", response_class=HTMLResponse, include_in_schema=False)
    async def hero_prototype():
        return HTMLResponse(content=HERO_HTML)
