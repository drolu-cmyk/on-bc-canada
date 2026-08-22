<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform" xmlns:s="http://www.sitemaps.org/schemas/sitemap/0.9">
  <xsl:output method="html" encoding="UTF-8"/>
  <xsl:template match="/">
    <html lang="en-CA">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title>Site map | SozoRock Canada</title>
        <style>
          :root{--red:#d52b1e;--ink:#111;--muted:#5a5d61;--line:#d9d9d9;--max:1120px}
          *{box-sizing:border-box}body{margin:0;background:#fff;color:var(--ink);font:16px/1.5 Arial,Helvetica,sans-serif}.wrap{width:min(var(--max),calc(100% - 48px));margin:auto}.top{padding:28px 0;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:24px;align-items:center}.brand{font-family:Georgia,'Times New Roman',serif;font-size:28px;font-weight:700;text-decoration:none;color:var(--ink)}.back{font-size:14px;color:var(--ink);text-decoration:none;border-bottom:2px solid var(--red)}main{padding:64px 0 80px}.label{margin:0 0 12px;color:var(--red);font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}h1{max-width:760px;margin:0;font:600 clamp(42px,6vw,72px)/.98 Georgia,'Times New Roman',serif;letter-spacing:-.035em}p{max-width:700px;color:var(--muted)}.count{margin-top:28px;font-size:14px;font-weight:700}.list{margin-top:36px;border-top:1px solid var(--ink)}.row{display:grid;grid-template-columns:minmax(0,1fr) 130px;gap:24px;padding:16px 0;border-bottom:1px solid var(--line)}.row a{overflow-wrap:anywhere;color:var(--ink);text-decoration:none}.row a:hover{text-decoration:underline}.date{color:var(--muted);font-size:14px;text-align:right}@media(max-width:640px){.wrap{width:min(var(--max),calc(100% - 28px))}.top{align-items:flex-start}.row{grid-template-columns:1fr}.date{text-align:left}}
        </style>
      </head>
      <body>
        <div class="wrap top"><a class="brand" href="/">SozoRock Canada</a><a class="back" href="/">Return home</a></div>
        <main class="wrap">
          <p class="label">Site map</p>
          <h1>Canonical pages on canada.sozorock.com</h1>
          <p>This file is provided for search engines and for anyone who wants a direct view of the public site structure.</p>
          <div class="count"><xsl:value-of select="count(s:urlset/s:url)"/> public URLs</div>
          <div class="list">
            <xsl:for-each select="s:urlset/s:url">
              <div class="row"><a href="{s:loc}"><xsl:value-of select="s:loc"/></a><span class="date"><xsl:value-of select="s:lastmod"/></span></div>
            </xsl:for-each>
          </div>
        </main>
      </body>
    </html>
  </xsl:template>
</xsl:stylesheet>
