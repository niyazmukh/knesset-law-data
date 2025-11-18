// Chrome DevTools scraper: listing -> per-law PDFs (paginated) -> next listing pages
// Usage: node devtools_scrape.js --chromeExe <path> --startUrl <url> --urlOut <file> --pdfOut <file> [--maxListing <n>] [--maxLaw <n>]

const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

function arg(name, def){
  const i = process.argv.indexOf(name);
  if (i !== -1 && i + 1 < process.argv.length) return process.argv[i+1];
  return def;
}

const CHROME = arg('--chromeExe', process.env.CHROME_BINARY || '');
const START_URL = arg('--startUrl', '');
const URL_OUT = arg('--urlOut', path.join(process.cwd(), 'scraped_urls_devtools.txt'));
const PDF_OUT = arg('--pdfOut', path.join(process.cwd(), 'pdf_links_devtools.txt'));
const MAX_LISTING = parseInt(arg('--maxListing', process.env.MAX_LISTING_PAGES || '0'), 10) || 0;
const MAX_LAW = parseInt(arg('--maxLaw', process.env.MAX_LAW_PAGES || '0'), 10) || 0;

function sleep(ms){ return new Promise(r => setTimeout(r, ms)); }

async function nextByPostback(page) {
  const prevSig = await pageSignature(page);
  const clicked = await page.evaluate(() => {
    function visible(el){
      const r = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    }
    const directNext = Array.from(document.querySelectorAll("a[id*='aNextPage']"))
      .filter(a => visible(a) && !/disabled/i.test(a.outerHTML));
    if (directNext.length) { directNext[0].click(); return true; }
    const candidates = Array.from(document.querySelectorAll("a[id*='lnkbtnNext']"))
      .filter(a => visible(a) && !/disabled/i.test(a.outerHTML));
    if (candidates.length) { candidates[0].click(); return true; }
    const postbacks = Array.from(document.querySelectorAll('a[href*="__doPostBack"]'));
    const nextLike = postbacks.find(a => /next|lnkbtnnext/i.test(a.outerHTML));
    if (nextLike) { nextLike.click(); return true; }
    if (postbacks[0]) { postbacks[0].click(); return true; }
    return false;
  });
  if (!clicked) return false;
  try {
    await page.waitForFunction((sig)=>{
      const cur = location.href;
      const hrefs = Array.from(document.querySelectorAll('a')).map(a=>a.href||'').filter(Boolean).sort().slice(0,500);
      const data = cur + '|' + hrefs.join('|');
      return data !== sig;
    }, { timeout: 20000 }, prevSig);
  } catch { return false; }
  await sleep(300);
  return true;
}

async function pageSignature(page){
  return await page.evaluate(() => {
    const cur = location.href;
    const hrefs = Array.from(document.querySelectorAll('a')).map(a=>a.href||'').filter(Boolean).sort().slice(0,500);
    return cur + '|' + hrefs.join('|');
  });
}

async function collectPdfLinksFromLaw(page){
  const pdfs = new Set();
  let pages = 0;
  let added = 0;
  while(true){
    const cur = await page.$$eval('a', as => as.map(a=>a.href||'').filter(Boolean).filter(h => /\.pdf(\?|#|$)/i.test(h)));
    const before = pdfs.size;
    cur.forEach(h => pdfs.add(h));
    added = pdfs.size - before;
    pages++;
    if (MAX_LAW && pages >= MAX_LAW) break;
    const moved = await nextByPostback(page);
    if (!moved || added === 0) break;
  }
  return [...pdfs];
}

async function collectListingLawLinks(page){
  const seenListingSignatures = new Set();
  const lawSet = new Set();
  let listPages = 0;

  while (true) {
    const curSig = await pageSignature(page);
    if (seenListingSignatures.has(curSig)) break;
    seenListingSignatures.add(curSig);

    try { await page.waitForSelector("a[href*='lawitemid=']", { timeout: 20000 }); } catch {}
    const lawLinks = await page.$$eval("a[href*='lawitemid=']", as => Array.from(new Set(as.map(a=>a.href).filter(Boolean))));
    lawLinks.forEach(h => lawSet.add(h));

    listPages++;
    if (MAX_LISTING && listPages >= MAX_LISTING) break;
    const moved = await nextByPostback(page);
    if (!moved) break;
  }

  return [...lawSet].sort();
}

async function collectPdfsForLaws(page, lawUrls){
  const pdfSet = new Set();
  for (const href of lawUrls) {
    await page.goto(href, { waitUntil: 'networkidle2', timeout: 120000 });
    const lawPdfs = await collectPdfLinksFromLaw(page);
    lawPdfs.forEach(u => pdfSet.add(u));
  }
  return [...pdfSet].sort();
}

async function collectAll(CHROME, START_URL){
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: false,
    defaultViewport: { width: 1600, height: 1000 },
    args: [
      '--lang=he-IL',
      '--disable-blink-features=AutomationControlled',
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--start-maximized'
    ]
  });
  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) ' +
    'AppleWebKit/537.36 (KHTML, like Gecko) ' +
    'Chrome/122.0.0.0 Safari/537.36');
  await page.setExtraHTTPHeaders({ 'Accept-Language': 'he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7' });
  await page.goto(START_URL, { waitUntil: 'networkidle2', timeout: 120000 });
  try { await page.$$eval("button#onetrust-accept-btn-handler, button[aria-label*='accept' i]", bs => bs.forEach(b=>b.click())); } catch {}
  await sleep(300);

  const lawUrls = await collectListingLawLinks(page);
  const pdfLinks = await collectPdfsForLaws(page, lawUrls);

  await browser.close();
  return { lawUrls, pdfLinks };
}

(async () => {
  if (!CHROME || !START_URL) {
    console.error('Usage: node devtools_scrape.js --chromeExe <path> --startUrl <url> --urlOut <file> --pdfOut <file>');
    process.exit(2);
  }
  const { lawUrls, pdfLinks } = await collectAll(CHROME, START_URL);
  fs.writeFileSync(URL_OUT, lawUrls.join('\n') + '\n', 'utf-8');
  fs.writeFileSync(PDF_OUT, pdfLinks.join('\n') + '\n', 'utf-8');
  console.log(`Saved ${lawUrls.length} law URLs -> ${URL_OUT}`);
  console.log(`Saved ${pdfLinks.length} PDF URLs -> ${PDF_OUT}`);
})().catch(e => { console.error(e); process.exit(1); });

