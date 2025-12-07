from fastapi import FastAPI
from fastapi.responses import StreamingResponse, HTMLResponse


def register_website_home_routes(app: FastAPI):
    """Register website home page routes to the FastAPI app"""

    @app.get("/", response_class=HTMLResponse)
    async def read_root():
        return """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">

            <!-- Primary Meta Tags -->
            <title>Dreaming of a Jet Plane - Interactive Yoto Plane Scanner</title>
            <meta name="title" content="Dreaming of a Jet Plane - Interactive Yoto Plane Scanner">
            <meta name="description" content="Magically turn your Yoto player into a Jet Plane Scanner that finds airplanes in the skies around you, then teaches you all about them and the faraway destinations they are headed.">
            <meta name="keywords" content="Yoto, airplane scanner, jet plane, kids learning, educational app, flight tracker, children audio">
            <meta name="author" content="Callum Merriman">
            <meta name="robots" content="index, follow">

            <!-- Open Graph / Facebook -->
            <meta property="og:type" content="website">
            <meta property="og:url" content="https://dreamingofajetplane.com/">
            <meta property="og:title" content="Dreaming of a Jet Plane - Interactive Yoto Plane Scanner">
            <meta property="og:description" content="Magically turn your Yoto player into a Jet Plane Scanner that finds airplanes in the skies around you, then teaches you all about them and the faraway destinations they are headed.">
            <meta property="og:image" content="https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/dreaming-of-a-jet-plane-share.jpg">
            <meta property="og:site_name" content="Dreaming of a Jet Plane">

            <!-- Twitter -->
            <meta property="twitter:card" content="summary_large_image">
            <meta property="twitter:url" content="https://dreamingofajetplane.com/">
            <meta property="twitter:title" content="Dreaming of a Jet Plane - Interactive Yoto Plane Scanner">
            <meta property="twitter:description" content="Magically turn your Yoto player into a Jet Plane Scanner that finds airplanes in the skies around you, then teaches you all about them and the faraway destinations they are headed.">
            <meta property="twitter:image" content="https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/dreaming-of-a-jet-plane-share.jpg">

            <!-- Additional SEO -->
            <link rel="canonical" href="https://dreamingofajetplane.com/">
            <meta name="theme-color" content="#f45436">

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
                "embedUrl": "https://www.youtube.com/embed/heSlOrH17po"
              }
            }
            </script>
            <style>
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
                    max-width: 900px;
                    margin: 0 auto;
                    padding: 2rem;
                    background: #fff;
                    color: #000;
                    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }

                .content-grid {
                    display: grid;
                    grid-template-columns: 2fr 1fr;
                    gap: 3rem;
                    align-items: center;
                }

                .description {
                    font-size: 1.1rem;
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
                    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }

                .footer p {
                    margin: 0;
                    color: #666;
                    font-size: 0.9rem;
                }

                .footer a {
                    color: #f45436;
                    text-decoration: none;
                    font-weight: 600;
                    transition: color 0.2s ease;
                }

                .footer a:hover {
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
                    }

                    .footer {
                        padding: 1.5rem;
                    }
                }

                .loading {
                    position: absolute;
                    top: 50%;
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

                .hidden {
                    display: none;
                }
            </style>
        </head>
        <body>
            <div class="video-container">
                <div class="loading" id="loading">Loading video...</div>
                <div class="click-to-play hidden" id="playButton">🔊 Turn On Sound</div>
                <video
                    id="mainVideo"
                    autoplay
                    muted
                    loop
                    playsinline
                    preload="auto">
                    <source src="https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/Dreaming+Of+A+Jet+Plane+-+Yoto.mp4" type="video/mp4">
                    <!-- Fallback to YouTube embed if video file not available -->
                    <div style="position: relative; width: 100%; height: 100%;">
                        <iframe
                            src="https://www.youtube.com/embed/heSlOrH17po?autoplay=1&mute=1&loop=1&playlist=heSlOrH17po&controls=0&showinfo=0&rel=0&iv_load_policy=3&modestbranding=1"
                            style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none;"
                            title="Dreaming of a Jet Plane"
                            allowfullscreen>
                        </iframe>
                    </div>
                </video>
            </div>

            <div class="content-container">
                <div class="content-grid">
                    <div class="description">
                        <p>Magically turn your Yoto player into a Jet Plane Scanner that finds airplanes in the skies around you, then teaches you all about them and the faraway destinations they are headed.</p>
                    </div>
                    <div class="button-column">
                        <a href="https://share.yoto.co/s/27Y3g3KjqiWkIqdTWc27g2" target="_blank" class="yoto-button">
                            <img src="https://play-lh.googleusercontent.com/x2yP9r4V-Gnh87GubVMOdwj8kpOW4pFFkB483C4-dCk_odXfuAH4sYqvwmeVFWsHQ5Y" alt="Yoto" class="button-icon">
                            Add To Library
                        </a>
                    </div>
                </div>
            </div>

            <footer class="footer">
                <p>Created by <a href="https://www.linkedin.com/in/cjkmerriman/" target="_blank">Callum Merriman</a></p>
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

                // Click anywhere to enable sound
                document.addEventListener('click', (e) => {
                    if (e.target !== playButton && video.muted) {
                        video.muted = false;
                        playButton.classList.add('hidden');
                    }
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
