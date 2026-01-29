from fastapi import FastAPI
from fastapi.responses import StreamingResponse, HTMLResponse, PlainTextResponse


def register_website_home_routes(app: FastAPI):
    """Register website home page routes to the FastAPI app"""

    @app.get("/robots.txt", response_class=PlainTextResponse)
    async def robots_txt():
        return """User-agent: *
Allow: /

Sitemap: https://dreamingofajetplane.com/sitemap.xml"""

    @app.get("/sitemap.xml")
    async def sitemap_xml():
        content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://dreamingofajetplane.com/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>"""
        return HTMLResponse(content=content, media_type="application/xml")

    @app.get("/", response_class=HTMLResponse)
    async def read_root():
        return """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">

            <!-- Primary Meta Tags -->
            <title>Dreaming of a Jet Plane - Magical Yoto Jet Plane Scanner</title>
            <meta name="title" content="Dreaming of a Jet Plane - Magical Yoto Jet Plane Scanner">
            <meta name="description" content="Magically turn your Yoto player into a Jet Plane Scanner that finds airplanes in the skies around you, then teaches you all about them and the faraway destinations they are headed.">
            <meta name="keywords" content="Yoto, airplane scanner, jet plane, kids learning, educational app, flight tracker, children audio">
            <meta name="author" content="Callum Merriman">
            <meta name="robots" content="index, follow">

            <!-- Open Graph / Facebook -->
            <meta property="og:type" content="website">
            <meta property="og:url" content="https://dreamingofajetplane.com/">
            <meta property="og:title" content="Dreaming of a Jet Plane - Magical Yoto Jet Plane Scanner">
            <meta property="og:description" content="Magically turn your Yoto player into a Jet Plane Scanner that finds airplanes in the skies around you, then teaches you all about them and the faraway destinations they are headed.">
            <meta property="og:image" content="https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/dreaming-of-a-jet-plane-share.jpg">
            <meta property="og:site_name" content="Dreaming of a Jet Plane">

            <!-- Twitter -->
            <meta property="twitter:card" content="summary_large_image">
            <meta property="twitter:url" content="https://dreamingofajetplane.com/">
            <meta property="twitter:title" content="Dreaming of a Jet Plane - Magical Yoto Jet Plane Scanner">
            <meta property="twitter:description" content="Magically turn your Yoto player into a Jet Plane Scanner that finds airplanes in the skies around you, then teaches you all about them and the faraway destinations they are headed.">
            <meta property="twitter:image" content="https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/dreaming-of-a-jet-plane-share.jpg">

            <!-- Additional SEO -->
            <link rel="canonical" href="https://dreamingofajetplane.com/">
            <meta name="theme-color" content="#f45436">
            <link rel="icon" type="image/png" href="/assets/img/icon.png">
            <link rel="apple-touch-icon" href="/assets/img/apple-touch-icon.png">

            <!-- Fonts -->
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
            <link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700&display=swap" rel="stylesheet">

            <!-- Structured Data -->
            <script type="application/ld+json">
            {
              "@context": "https://schema.org",
              "@type": "SoftwareApplication",
              "name": "Dreaming of a Jet Plane",
              "description": "Interactive Yoto Plane Scanner that finds airplanes in the skies and teaches kids about destinations",
              "applicationCategory": "Educational",
              "operatingSystem": "Yoto Player",
              "creator": {
                "@type": "Person",
                "name": "Callum Merriman",
                "url": "https://www.linkedin.com/in/cjkmerriman/"
              },
              "url": "https://dreamingofajetplane.com/",
              "video": {
                "@type": "VideoObject",
                "name": "Dreaming of a Jet Plane Demo",
                "description": "Demo video showing the Yoto Plane Scanner in action",
                "thumbnailUrl": "https://img.youtube.com/vi/heSlOrH17po/maxresdefault.jpg",
                "embedUrl": "https://www.youtube.com/embed/heSlOrH17po",
                "uploadDate": "2025-12-07",
                "contentUrl": "https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/Dreaming+Of+A+Jet+Plane+-+Yoto.mp4"
              }
            }
            </script>
            <style>
                @font-face {
                    font-family: 'Dream Wish Sans';
                    src: url('/assets/fonts/DreamWishSansRegular.woff2') format('woff2'),
                         url('/assets/fonts/DreamWishSansRegular.woff') format('woff');
                    font-weight: 400;
                    font-style: normal;
                    font-display: swap;
                }

                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }

                body, html {
                    min-height: 100%;
                    background: #fff;
                    overflow-x: hidden;
                    cursor: none;
                }

                .site-logo {
                    position: absolute;
                    top: 30%;
                    left: 25%;
                    transform: translate(-50%, -50%);
                    z-index: 15;
                    height: 100px;
                    width: auto;
                }

                .video-tagline {
                    position: absolute;
                    top: 42%;
                    left: 25%;
                    transform: translateX(-50%);
                    z-index: 15;
                    color: #FE6601;
                    font-family: 'Dream Wish Sans', 'Nunito', sans-serif;
                    font-size: 1.3rem;
                    font-weight: 600;
                    line-height: 1.5;
                    text-align: center;
                    max-width: 400px;
                    text-transform: uppercase;
                }

                .video-container {
                    position: relative;
                    width: 100vw;
                    display: flex;
                    align-items: flex-start;
                    justify-content: center;
                }

                video {
                    width: 100%;
                    height: auto;
                    display: block;
                }

                .content-container {
                    width: 100%;
                    background: #fff url('/assets/img/card-bg.png') center top repeat-x;
                    background-size: 240px auto;
                    color: #000;
                    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    padding: 2rem;
                }

                .content-container .content-grid {
                    max-width: 900px;
                    margin: 0 auto;
                }

                .content-grid {
                    display: grid;
                    grid-template-columns: 2fr 1fr;
                    gap: 3rem;
                    align-items: center;
                }

                .description h1 {
                    font-family: 'Dream Wish Sans', 'Nunito', sans-serif;
                    font-size: 1.8rem;
                    color: #000;
                    margin-bottom: 0.8rem;
                    font-weight: 400;
                }

                .description {
                    font-size: 1.3rem;
                    line-height: 1.6;
                    color: #333;
                    font-weight: 600;
                }

                .button-column {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                }

                .yoto-button {
                    display: inline-flex;
                    align-items: center;
                    gap: 0.5rem;
                    background: linear-gradient(180deg, #f45436 0%, #e03e20 100%);
                    color: white;
                    text-decoration: none;
                    padding: 1.2rem 2.5rem;
                    border-radius: 15px;
                    font-size: 1.1rem;
                    font-weight: 700;
                    text-align: center;
                    transition: all 0.2s ease;
                    box-shadow: 0 4px 0 #c1301a, 0 6px 20px rgba(244, 84, 54, 0.3);
                    border: none;
                    cursor: pointer;
                    font-family: inherit;
                    letter-spacing: 0.5px;
                    white-space: nowrap;
                    padding-top: 1.3rem;
                    padding-bottom: 1.1rem;
                }

                .button-icon {
                    width: 28px;
                    height: 28px;
                    border-radius: 4px;
                }

                .yoto-button:hover {
                    transform: translateY(-1px);
                    box-shadow: 0 5px 0 #c1301a, 0 8px 25px rgba(244, 84, 54, 0.4);
                    background: linear-gradient(180deg, #f66648 0%, #e03e20 100%);
                }

                .yoto-button:active {
                    transform: translateY(2px);
                    box-shadow: 0 2px 0 #c1301a, 0 4px 15px rgba(244, 84, 54, 0.3);
                }

                .footer {
                    background: #fff;
                    padding: 2rem;
                    text-align: center;
                    border-top: 1px solid #eee;
                }

                .footer-logo {
                    height: 70px;
                    width: auto;
                }

                .award-banner {
                    width: 100%;
                    background: #FE6601 url('/assets/img/dev-bg.png') repeat;
                    background-size: auto 80px;
                    padding: 0.6rem 1rem;
                    text-align: center;
                    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    flex-direction: row;
                    align-items: center;
                    justify-content: center;
                    gap: 1rem;
                    flex-wrap: wrap;
                }

                .award-icon {
                    height: 40px;
                    width: auto;
                    object-fit: contain;
                    background: #eee;
                    padding: 6px;
                    border-radius: 50%;
                    border: 2px solid #222;
                }

                .award-banner p {
                    color: #222;
                    font-size: 1rem;
                    font-weight: 700;
                    margin: 0;
                    letter-spacing: 0.5px;
                }

                .award-link {
                    color: #222;
                    text-decoration: none;
                }

                .award-link:hover {
                    text-decoration: underline;
                }

                .testimonials {
                    width: 100%;
                    padding: 2rem;
                    background: linear-gradient(to bottom, #fff, #eee);
                    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }

                .testimonials-inner {
                    max-width: 900px;
                    margin: 0 auto;
                }

                .testimonials h2 {
                    font-family: 'Dream Wish Sans', 'Nunito', sans-serif;
                    font-size: 1.6rem;
                    color: #000;
                    margin-bottom: 1rem;
                    font-weight: 400;
                    text-transform: uppercase;
                }

                .testimonials-intro {
                    font-size: 1.1rem;
                    line-height: 1.6;
                    color: #333;
                    margin-bottom: 1.5rem;
                }

                .testimonial-quote {
                    padding: 0;
                    margin: 0 0 1rem 0;
                    font-size: 1.1rem;
                    line-height: 1.6;
                    color: #555;
                }

                .testimonial-quote p::before {
                    content: '"';
                    font-family: Georgia, serif;
                    font-size: 2.5rem;
                    color: #ccc;
                    line-height: 0;
                    vertical-align: -0.3em;
                    margin-right: 0.1em;
                }

                .testimonial-quote p::after {
                    content: '"';
                    font-family: Georgia, serif;
                    font-size: 2.5rem;
                    color: #ccc;
                    line-height: 0;
                    vertical-align: -0.3em;
                    margin-left: 0.1em;
                }

                .disclaimer {
                    width: 100%;
                    padding: 2rem;
                    background: #333;
                    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }

                .disclaimer-inner {
                    max-width: 900px;
                    margin: 0 auto;
                }

                .disclaimer h2 {
                    font-family: 'Dream Wish Sans', 'Nunito', sans-serif;
                    font-size: 1.6rem;
                    color: #fff;
                    margin-bottom: 1rem;
                    font-weight: 400;
                    text-transform: uppercase;
                }

                .disclaimer p {
                    font-size: 1.1rem;
                    line-height: 1.6;
                    color: #fff;
                    margin-bottom: 0.8rem;
                }

                .disclaimer p:last-child {
                    margin-bottom: 0;
                }

                .disclaimer-list {
                    list-style: disc;
                    padding-left: 1.5rem;
                    margin-bottom: 0.8rem;
                }

                .disclaimer-list li {
                    font-size: 1.1rem;
                    line-height: 1.6;
                    color: #fff;
                    margin-bottom: 0.5rem;
                }

                .disclaimer a {
                    color: #f45436;
                    text-decoration: none;
                    font-weight: 600;
                }

                .disclaimer a:hover {
                    color: #e03e20;
                    text-decoration: underline;
                }

                @media (max-width: 768px) {
                    .content-grid {
                        grid-template-columns: 1fr;
                        gap: 2rem;
                        text-align: center;
                    }

                    .content-container {
                        padding: 1.5rem;
                        background-size: 140px auto;
                    }

                    .footer {
                        padding: 1.5rem;
                    }
                }

                .loading {
                    position: absolute;
                    top: 30%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    color: white;
                    font-family: Arial, sans-serif;
                    font-size: 24px;
                    z-index: 10;
                }

                .click-to-play {
                    position: absolute;
                    top: 2rem;
                    right: 2rem;
                    display: inline-flex;
                    align-items: center;
                    gap: 0.5rem;
                    background: linear-gradient(180deg, #e0e0e0 0%, #d0d0d0 100%);
                    color: #333;
                    padding: 1.2rem 2.5rem;
                    border-radius: 15px;
                    font-size: 1.1rem;
                    font-weight: 700;
                    text-align: center;
                    transition: all 0.2s ease;
                    box-shadow: 0 4px 0 #b0b0b0, 0 6px 20px rgba(224, 224, 224, 0.3);
                    border: none;
                    cursor: pointer;
                    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    letter-spacing: 0.5px;
                    white-space: nowrap;
                    padding-top: 1.3rem;
                    padding-bottom: 1.1rem;
                    z-index: 20;
                }

                .click-to-play:hover {
                    transform: translateY(-1px);
                    box-shadow: 0 5px 0 #b0b0b0, 0 8px 25px rgba(224, 224, 224, 0.4);
                    background: linear-gradient(180deg, #e8e8e8 0%, #d0d0d0 100%);
                }

                .click-to-play:active {
                    transform: translateY(2px);
                    box-shadow: 0 2px 0 #b0b0b0, 0 4px 15px rgba(224, 224, 224, 0.3);
                }

                @media (max-width: 768px) {
                    .click-to-play {
                        padding: 0.3rem 0.6rem;
                        font-size: 0.55rem;
                        border-radius: 10px;
                        top: 1rem;
                        right: 1rem;
                        box-shadow: 0 2px 0 #b0b0b0, 0 3px 10px rgba(224, 224, 224, 0.3);
                    }

                    .sound-full {
                        display: none;
                    }

                    .site-logo {
                        height: 52px;
                        top: 30%;
                        left: 25%;
                    }

                    .video-tagline {
                        font-size: 0.55rem;
                        max-width: 160px;
                        top: 45%;
                    }

                    .award-banner p {
                        font-size: 0.7rem;
                    }

                    .award-icon {
                        height: 24px;
                        padding: 4px;
                    }

                    .yoto-button {
                        padding: 0.6rem 1.2rem;
                        font-size: 0.85rem;
                    }

                    .testimonials h2,
                    .disclaimer h2 {
                        font-size: 1.2rem;
                    }

                    .testimonials-intro,
                    .testimonial-quote,
                    .disclaimer p,
                    .disclaimer-list li {
                        font-size: 0.9rem;
                    }

                    .testimonial-quote p::before,
                    .testimonial-quote p::after {
                        font-size: 1.8rem;
                    }
                }

                .hidden {
                    display: none;
                }
            </style>
        </head>
        <body>
            <section class="award-banner">
                <img src="/assets/img/happytrophy.png" alt="Trophy" class="award-icon">
                <p><a href="https://yoto.space/news/post/the-developer-challenge-2025-winners-bbCk0Y8q8fK6JNY" target="_blank" rel="noopener" class="award-link">Yoto 2025 Developer Challenge Winner</a></p>
            </section>

            <header>
                <div class="video-container">
                    <a href="/"><img src="/assets/img/wordmark.png" alt="Dreaming of a Jet Plane" class="site-logo"></a>
                    <p class="video-tagline">Magically turn your Yoto into a Jet Plane Scanner that finds planes in the skies around you, then teaches you all about them and the faraway destinations they are headed.</p>
                    <div class="loading" id="loading">Loading video...</div>
                    <div class="click-to-play hidden" id="playButton">🔊 <span class="sound-full">Turn On </span>Sound</div>
                    <video
                        id="mainVideo"
                        autoplay
                        muted
                        loop
                        playsinline
                        preload="auto">
                        <source src="https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/website-header-compressed.mp4" type="video/mp4">
                        <!-- Fallback to YouTube embed if video file not available -->
                        <div style="position: relative; width: 100%; height: 100%;">
                            <iframe
                                src="https://www.youtube.com/embed/heSlOrH17po?autoplay=1&mute=1&loop=1&playlist=heSlOrH17po&controls=0&showinfo=0&rel=0&iv_load_policy=3&modestbranding=1"
                                style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none;"
                                title="Dreaming of a Jet Plane - Yoto Plane Scanner Demo Video"
                                allowfullscreen>
                            </iframe>
                        </div>
                    </video>
                </div>
            </header>

            <main class="content-container">
                <div class="button-column">
                    <a href="https://share.yoto.co/s/27Y3g3KjqiWkIqdTWc27g2" target="_blank" rel="noopener" class="yoto-button">
                        <img src="/assets/img/yoto.png" alt="Yoto app icon" class="button-icon">
                        Listen & Add To Your Library
                    </a>
                </div>
            </main>

            <section class="testimonials">
                <div class="testimonials-inner">
                    <h2>Love For Dreaming Of A Jet Plane</h2>
                    <p class="testimonials-intro">Thank you to the tens of thousands of families who spot jet planes every week with Dreaming of a Jet Plane. Here is just some of the awesome feedback we have received.</p>
                    <blockquote class="testimonial-quote">
                        <p>This is wonderful!! Thank you for making it - we listen every morning at breakfast. We love to pretend our hands are scanning the sky during the cool scanning sounds. Most planes detected for us are coming in and out of our local airport, but occasionally it detects some flying high over us between countries, and that is extra cool!</p>
                    </blockquote>
                    <blockquote class="testimonial-quote">
                        <p>This is absolutely amazing! My 5 year old who is obsessed with planes loves this (as do I - I always pop my head in to hear). Could you release one that just keeps going on and on - we'd easily pay for that!</p>
                    </blockquote>
                    <blockquote class="testimonial-quote">
                        <p>As former flight attendants we are obsessed with this card! Such a fun way to get my kids excited about aircrafts!</p>
                    </blockquote>
                    <blockquote class="testimonial-quote">
                        <p>This is incredible! We absolutely adore it here and I had a very happy little boy when one of the planes was going to Portugal (where his nanny and grandad are right now). Thank you so much x</p>
                    </blockquote>
                </div>
            </section>

            <section class="disclaimer">
                <div class="disclaimer-inner">
                    <h2>How we use AI</h2>
                    <p>The app uses AI to bring Hamish to life in real-time, allowing the audio to be personalized for each user based on their location. The AI is simply the voice reading a script; it does not think or create its own stories.</p>
                    <p>While the voice is generated by AI, the information and content it shares is not:</p>
                    <ul class="disclaimer-list">
                        <li><strong>Flight Data:</strong> All flight details are pulled from industry-standard flight tracking services such as FlightRadar and Airlabs.</li>
                        <li><strong>City Facts:</strong> Every educational city fact was hand-picked and personally verified as child-friendly.</li>
                        <li><strong>Human Content:</strong> All words spoken by Hamish were either written or reviewed by the developer. The app does not use AI to write content or "chat" with children.</li>
                    </ul>
                    <p><strong>Safety First.</strong> Because the content has been reviewed and the flight data comes from professional sources, there is no risk of the app "hallucinating" or saying something unexpected. The content is fixed and predictable.</p>
                    <p>As a parent myself, I built this with my own children in mind. I wanted to create something that feels like magic but operates within a strictly controlled, safe environment that parents can trust completely.</p>
                    <p>Any questions, get in touch on <a href="https://yoto.space/developers/post/dreaming-of-a-jet-plane-cDFgOvSmJNJi4LK?highlight=31rkfxQwLKqiW7U" target="_blank" rel="noopener">Yoto Space</a></p>
                </div>
            </section>

            <footer class="footer">
                <img src="/assets/img/raccoonresearchlabs.png" alt="Raccoon Research Labs" class="footer-logo">
            </footer>

            <script>
                const video = document.getElementById('mainVideo');
                const loading = document.getElementById('loading');
                const playButton = document.getElementById('playButton');

                // Handle video loading
                video.addEventListener('loadstart', () => {
                    loading.style.display = 'block';
                });

                video.addEventListener('canplay', () => {
                    loading.style.display = 'none';

                    // Try to play with sound first
                    video.muted = false;
                    const playPromise = video.play();

                    if (playPromise !== undefined) {
                        playPromise.catch(() => {
                            // If autoplay with sound fails, fall back to muted autoplay
                            video.muted = true;
                            video.play().then(() => {
                                // Show button to enable sound
                                playButton.classList.remove('hidden');
                            }).catch(() => {
                                // If even muted autoplay fails, show play button
                                playButton.classList.remove('hidden');
                                playButton.textContent = '▶ Click to Play';
                            });
                        });
                    }
                });

                video.addEventListener('error', () => {
                    loading.textContent = 'Loading YouTube player...';
                    // Video failed to load, fallback will show
                });

                // Handle click to play with sound
                playButton.addEventListener('click', () => {
                    video.muted = false;
                    video.play();
                    playButton.classList.add('hidden');
                });

                // Hide cursor after inactivity
                let cursorTimer;
                document.addEventListener('mousemove', () => {
                    document.body.style.cursor = 'default';
                    clearTimeout(cursorTimer);
                    cursorTimer = setTimeout(() => {
                        document.body.style.cursor = 'none';
                    }, 3000);
                });

            </script>
        </body>
        </html>
        """

    @app.options("/")
    async def root_options():
        """Handle CORS preflight requests for main endpoint"""
        return StreamingResponse(
            iter([b""]),
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "Range, Content-Range, Content-Length",
                "Access-Control-Max-Age": "3600"
            }
        )
