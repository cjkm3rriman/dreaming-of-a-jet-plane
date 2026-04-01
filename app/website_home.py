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
              "@type": "WebSite",
              "name": "Dreaming of a Jet Plane",
              "url": "https://dreamingofajetplane.com/"
            }
            </script>
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
              "url": "https://dreamingofajetplane.com/"
            }
            </script>
            <script type="application/ld+json">
            {
              "@context": "https://schema.org",
              "@type": "VideoObject",
              "name": "Dreaming of a Jet Plane Demo",
              "description": "Demo video showing the Yoto Plane Scanner in action",
              "thumbnailUrl": "https://img.youtube.com/vi/heSlOrH17po/maxresdefault.jpg",
              "embedUrl": "https://www.youtube.com/embed/heSlOrH17po",
              "uploadDate": "2025-12-07T00:00:00Z",
              "contentUrl": "https://dreaming-of-a-jet-plane.s3.us-east-2.amazonaws.com/Dreaming+Of+A+Jet+Plane+-+Yoto.mp4"
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
                    font-size: 1.5rem;
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

                .flight-path {
                    width: 100%;
                    padding: 6.5rem 4rem 5rem;
                    background: #fff url('/assets/img/card-bg.png') center top repeat-x;
                    background-size: 240px auto;
                    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }

                .flight-path-inner {
                    max-width: 900px;
                    margin: 0 auto;
                }

                .flight-path h2 {
                    font-family: 'Dream Wish Sans', 'Nunito', sans-serif;
                    font-size: 1.6rem;
                    color: #000;
                    margin-bottom: 0.5rem;
                    font-weight: 400;
                    text-transform: uppercase;
                    text-align: center;
                }

                .flight-path-intro {
                    font-size: 1.1rem;
                    line-height: 1.6;
                    color: #333;
                    text-align: center;
                    margin-bottom: 2rem;
                }

                .tier-cards {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 1.5rem;
                    margin-bottom: 2.5rem;
                    align-items: start;
                }

                .tier-card {
                    border-radius: 16px;
                    padding: 1.8rem;
                    position: relative;
                }

                .tier-card-club {
                    background: #003c1f;
                }

                .tier-card-free {
                    background: #fbf9f9;
                }



                .tier-card h3 {
                    font-family: 'Dream Wish Sans', 'Nunito', sans-serif;
                    font-size: 1.2rem;
                    font-weight: 400;
                    margin-bottom: 0.5rem;
                    text-transform: uppercase;
                    text-align: center;
                }

                .tier-card h3 span {
                    display: block;
                    font-size: 1.6rem;
                    margin-top: 0.2rem;
                }


                .tier-card-button {
                    text-align: center;
                    margin-top: 0.8rem;
                    margin-bottom: 1rem;
                }

                .yoto-button-sm {
                    padding: 0.7rem 1.5rem;
                    font-size: 0.9rem;
                    padding-top: 0.8rem;
                    padding-bottom: 0.6rem;
                }

                button.yoto-button {
                    border: none;
                    cursor: pointer;
                }

                .modal-overlay {
                    display: none;
                    position: fixed;
                    top: 0; left: 0; right: 0; bottom: 0;
                    background: rgba(0, 0, 0, 0.6);
                    justify-content: center;
                    align-items: center;
                    z-index: 1000;
                }

                .modal-content {
                    background: white;
                    border-radius: 1rem;
                    padding: 2rem;
                    max-width: 420px;
                    text-align: center;
                    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
                }

                .modal-content h3 {
                    font-family: 'Dream Wish Sans', 'Nunito', sans-serif;
                    font-size: 1.6rem;
                    font-weight: 400;
                    text-transform: uppercase;
                    margin-bottom: 1rem;
                    color: #000;
                }

                .modal-content p {
                    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    font-size: 1.1rem;
                    line-height: 1.6;
                    color: #333;
                    margin-bottom: 1.5rem;
                }

                .modal-close {
                    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: #FE6601;
                    color: white;
                    border: none;
                    padding: 0.7rem 1.5rem;
                    border-radius: 0.5rem;
                    font-size: 1rem;
                    cursor: pointer;
                    font-weight: 600;
                }

                .modal-close:hover {
                    background: #e55b00;
                }

                .tier-card > p {
                    font-size: 1.1rem;
                    line-height: 1.6;
                    color: rgba(0, 0, 0, 0.6);
                    margin-bottom: 1rem;
                }

                .tier-card ul {
                    list-style: none;
                    padding: 0;
                }

                .tier-card ul li {
                    font-size: 1.1rem;
                    line-height: 1.6;
                    color: rgba(0, 0, 0, 0.6);
                    margin-bottom: 0.6rem;
                    padding-left: 0.2rem;
                }

                .tier-card ul li strong {
                    color: #000;
                }

                .tier-card-club,
                .tier-card-club > p,
                .tier-card-club ul li,
                .tier-card-club h3 {
                    color: rgba(255, 255, 255, 0.9);
                }

                .tier-card-club ul li strong,
                .tier-card-club h3 span {
                    color: #fff;
                }

                .tier-card-free h3 {
                    color: rgba(0, 0, 0, 0.6);
                }

                .tier-card-free h3 span {
                    color: #222;
                }

                .comparison-table {
                    width: 100%;
                    border-collapse: separate;
                    border-spacing: 0;
                    font-size: 0.95rem;
                    border-radius: 8px;
                    border: 1px solid #eee;
                }

                .comparison-table thead th:first-child {
                    width: 35%;
                }

                .comparison-table thead th {
                    background: #eee;
                    color: #111;
                    padding: 0.8rem 1rem;
                    text-align: left;
                    font-family: 'Dream Wish Sans', 'Nunito', sans-serif;
                    font-weight: 400;
                    font-size: 1.1rem;
                    text-transform: uppercase;
                }

                .comparison-table thead th:not(:first-child) {
                    text-align: center;
                }

                .comparison-table tbody td {
                    padding: 0.7rem 1rem;
                    border-bottom: 1px solid #eee;
                    color: #333;
                }

                .comparison-table tbody td:not(:first-child) {
                    text-align: center;
                }

                .comparison-table tbody tr:nth-child(even) {
                    background: #f9f9f9;
                }

                .comparison-table tbody tr:last-child td {
                    border-bottom: none;
                }

                @media (max-width: 768px) {
                    .tier-cards {
                        grid-template-columns: 1fr;
                    }

                    .flight-path {
                        padding: 3rem 2rem;
                    }

                    .flight-path h2 {
                        font-size: 1.2rem;
                    }

                    .flight-path-intro {
                        font-size: 0.9rem;
                    }

                    .tier-card h3 {
                        font-size: 1.1rem;
                    }

                    .tier-card > p,
                    .tier-card ul li,
                    .comparison-table {
                        font-size: 0.85rem;
                    }

                    .comparison-table thead th,
                    .comparison-table tbody td {
                        padding: 0.5rem 0.6rem;
                    }
                }

                .testimonials {
                    width: 100%;
                    padding: 2rem;
                    background: #f5f0f0;
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

                .faq {
                    width: 100%;
                    padding: 3rem 2rem;
                    background: #FE6601;
                    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }

                .faq-inner {
                    max-width: 900px;
                    margin: 0 auto;
                }

                .faq h2 {
                    font-family: 'Dream Wish Sans', 'Nunito', sans-serif;
                    font-size: 1.6rem;
                    color: #fff;
                    font-weight: 400;
                    text-transform: uppercase;
                    margin-bottom: 1.5rem;
                }

                .faq-item {
                    margin-bottom: 2rem;
                }

                .faq-question {
                    font-size: 1.1rem;
                    font-weight: 700;
                    color: #fff;
                    margin-bottom: 0.5rem;
                }

                .faq-answer {
                    font-size: 1.1rem;
                    line-height: 1.6;
                    color: rgba(255, 255, 255, 0.9);
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
                        font-size: 0.7rem;
                        max-width: 160px;
                        top: 45%;
                    }

                    .tagline-extended {
                        display: none;
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
                    .disclaimer h2,
                    .faq h2 {
                        font-size: 1.2rem;
                    }

                    .testimonials-intro,
                    .testimonial-quote,
                    .disclaimer p,
                    .disclaimer-list li,
                    .faq-question,
                    .faq-answer {
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
                    <p class="video-tagline">Magically turn your Yoto into a Jet Plane Scanner that finds planes in the skies around you<span class="tagline-extended">, then teaches you all about them and the faraway destinations they are headed</span>.</p>
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

            <section class="flight-path">
                <div class="flight-path-inner">
                    <h2>Choose Your Flight Path</h2>
                    <p class="flight-path-intro">Whether you want to track the jets flying directly over your house, or simply tune into recently spotted flights from around the world, there's a version of Dreaming of a Jet Plane for every young air traffic controller on Yoto.</p>

                    <div class="tier-cards">
                        <div class="tier-card tier-card-club">
                            <h3>Yoto Club Members<span>Your Own Scanner</span></h3>
                            <div class="tier-card-button">
                                <button onclick="document.getElementById('comingSoonModal').style.display='flex'" class="yoto-button yoto-button-sm">
                                    <img src="/assets/img/yoto.png" alt="Yoto app icon" class="button-icon">
                                    Add to Library & Listen
                                </button>
                            </div>
                            <p>Yoto Club members unlock the full power of the jet plane scanner, giving them real-time information on the planes traversing the skies above their Yoto.</p>
                            <ul>
                                <li><strong>Real-Time Scanning:</strong> Find real jet planes in the skies above your Yoto, and understand exactly how far away the plane is from your Yoto.</li>
                                <li><strong>Jet Plane Facts &amp; Fun:</strong> Learn all about the aircraft, its route, and fun facts about the destination it is headed to.</li>
                                <li><strong>A Full Flight Deck:</strong> Track the top five local aircraft and their destinations with each scan.</li>
                                <li><strong>Unlimited Scans:</strong> Don't miss a single flight. Refresh your radar at any time to catch every jet plane entering your airspace.</li>
                                <li><strong>Special Signal Events:</strong> Exclusive access to magical scanning events throughout the year, such as Santa's sleigh on Christmas Eve.</li>
                            </ul>
                        </div>
                        <div class="tier-card tier-card-free">
                            <h3>Free<span>Tune In</span></h3>
                            <div class="tier-card-button">
                                <a href="https://share.yoto.co/s/27Y3g3KjqiWkIqdTWc27g2" target="_blank" rel="noopener" class="yoto-button yoto-button-sm">
                                    <img src="/assets/img/yoto.png" alt="Yoto app icon" class="button-icon">
                                    Add to Library & Listen
                                </a>
                            </div>
                            <p>Not a Yoto Club member, no problem! Listen in on flights recently spotted by our network of junior air traffic controllers around the world.</p>
                            <ul>
                                <li><strong>Tune In:</strong> Hear what other jet planes spotters are finding across the globe. There will always be something new to discover.</li>
                                <li><strong>Jet Plane Facts &amp; Fun:</strong> Get the same high-quality details on aircraft types, airlines, and fun destination facts.</li>
                                <li><strong>A Discovery Deck:</strong> Get the details on three jet planes with each play, with the ability to tune in multiple times per day.</li>
                            </ul>
                        </div>
                    </div>

                    <table class="comparison-table">
                        <thead>
                            <tr>
                                <th>Feature</th>
                                <th>Yoto Club</th>
                                <th>Free</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr><td>Kid-Safe Content</td><td>Yes</td><td>Yes</td></tr>
                            <tr><td>High Quality Narration from Hamish</td><td>Yes</td><td>Yes</td></tr>
                            <tr><td>Jet Plane Facts</td><td>Yes</td><td>Yes</td></tr>
                            <tr><td>Destination Fun Facts</td><td>Yes</td><td>Yes</td></tr>
                            <tr><td>Realtime Local Scanning</td><td>Yes</td><td>No</td></tr>
                            <tr><td>Jet Plane Selection Pool</td><td>Local To Your Yoto</td><td>Random</td></tr>
                            <tr><td>Jet Plane Results per Scan</td><td>5</td><td>3</td></tr>
                            <tr><td>Special Signal Events</td><td>Yes</td><td>No</td></tr>
                            <tr><td>Unlimited Scans</td><td>Yes</td><td>No: Daily Limits</td></tr>
                        </tbody>
                    </table>
                </div>
            </section>

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
                    <p>While the voice is generated by AI, the information and content is from professional sources and curated by humans:</p>
                    <ul class="disclaimer-list">
                        <li><strong>Flight Data:</strong> All flight details are pulled from industry-standard flight tracking services such as FlightRadar and Airlabs.</li>
                        <li><strong>City Facts:</strong> Every educational city fact was hand-picked and personally verified as child-friendly.</li>
                        <li><strong>Human Content:</strong> All words spoken by Hamish were either written or reviewed by the developer. The app does not use AI to write content or chat with children.</li>
                    </ul>
                    <p><strong>Safety First.</strong> Because the content has been reviewed and the flight data comes from professional sources, there is no risk of the app hallucinating or saying something unexpected. The content is fixed and predictable.</p>
                    <p>As a parent myself, I built this with my own children in mind. I wanted to create something that feels like magic but operates within a strictly controlled, safe environment that parents can trust completely.</p>
                    <p>Any questions, get in touch on <a href="https://yoto.space/developers/post/dreaming-of-a-jet-plane-cDFgOvSmJNJi4LK?highlight=31rkfxQwLKqiW7U" target="_blank" rel="noopener">Yoto Space</a></p>
                </div>
            </section>

            <section class="faq">
                <div class="faq-inner">
                    <h2>FAQs</h2>
                    <div class="faq-item">
                        <h3 class="faq-question">Why is Dreaming of a Jet Plane no longer free?</h3>
                        <p class="faq-answer">Dreaming of a Jet Plane uses real-time flight data and AI-powered narration to create a unique experience every time you play. These services come with ongoing costs that grow as more families discover the app. We believe making the full experience available through Yoto Club is the most accessible way to keep it running and improving for everyone. That said, the free version still offers the same engaging, high-quality content with Hamish and fun destination facts - it's just not personalized to the skies above your Yoto.</p>
                    </div>
                    <div class="faq-item">
                        <h3 class="faq-question">Where has Hamish gone?</h3>
                        <p class="faq-answer">Hamish has taken a well-earned respite in the Maldives! In the meantime, Hugo has taken his place at the scanner and will be guiding your little ones through the skies for the foreseeable future.</p>
                    </div>
                </div>
            </section>

            <footer class="footer">
                <img src="/assets/img/raccoonresearchlabs.png" alt="Raccoon Research Labs" class="footer-logo">
            </footer>

            <div id="comingSoonModal" class="modal-overlay" onclick="if(event.target===this)this.style.display='none'">
                <div class="modal-content">
                    <h3>Link Coming Soon!</h3>
                    <p>For now, find it in the <strong>Yoto Club</strong> section of your Yoto app.</p>
                    <button class="modal-close" onclick="document.getElementById('comingSoonModal').style.display='none'">Got it</button>
                </div>
            </div>

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
