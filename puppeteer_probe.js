// DevTools-level probe: listing pages -> law pages -> PDFs summary
// Uses puppeteer-core with the provided Chrome for Testing binary

const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

const START_URL = 'https://main.knesset.gov.il/Activity/Legislation/Laws/Pages/LawLaws.aspx?t=LawLaws&st=LawLawsValidity';
const CHROME = 'C:/users/niyaz/chrome-cft-142.0.7444.162/chrome-win64/chrome.exe';

function sleep(ms){ return new Promise(r => setTimeout(r, ms)); }

async function nextByPostback(page) {
  const prevSig = await pageSignature(page);
  // Prefer explicit lnkbtnNext anchors that are visible and enabled
  const clicked = await page.evaluate(() => {
    function visible(el){
      const r = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    }
    const candidates = Array.from(document.querySelectorAll("a[id*='lnkbtnNext']"))
      .filter(a => visible(a) && !/disabled/i.test(a.outerHTML));
    if (candidates.length) {
      candidates[0].click();
      return true;
    }
    // fallback: any __doPostBack next-ish anchor
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
    }, { timeout: 15000 }, prevSig);
  } catch { return false; }
  await page.waitForLoadState?.('domcontentloaded').catch(()=>{});
  await sleep(500);
  return true;
}

async function pageSignature(page){
  return await page.evaluate(() => {
    const cur = location.href;
    const hrefs = Array.from(document.querySelectorAll('a')).map(a=>a.href||'').filter(Boolean).sort().slice(0,500);
    return cur + '|' + hrefs.join('|');
  });
}

async function collectListingLawLinks(page, maxPages=0){
  const seen = new Set();
  const out = new Set();
  let pages = 0;
  while(true){
    const cur = await page.url();
    if (seen.has(cur)) break;
    seen.add(cur);
    const links = await page.$$eval('a[href*="lawitemid="]', as => Array.from(new Set(as.map(a=>a.href).filter(Boolean))));
    links.forEach(h => out.add(h));
    pages++;
    if (maxPages && pages>=maxPages) break;
    const moved = await nextByPostback(page);
    if (!moved) break;
  }
  return [...out];
}

async function collectPdfLinksFromLaw(page, maxPages=0){
  const pdfs = new Set();
  let pages = 0;
  let lastCount = -1;
  while(true){
    const curLinks = await page.$$eval('a', as => as.map(a=>a.href||'').filter(Boolean).filter(h => /\.pdf(\?|#|$)/i.test(h)));
    curLinks.forEach(h => pdfs.add(h));
    pages++;
    if (maxPages && pages>=maxPages) break;
    const before = pdfs.size;
    const moved = await nextByPostback(page);
    if (!moved) break;
    if (pdfs.size === before) {
      // no new links after moving, stop
      break;
    }
  }
  return [...pdfs];
}

async function main(){
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: false,
    defaultViewport: { width: 1600, height: 1000 },
    args: [
      '--lang=he-IL',
      '--disable-blink-features=AutomationControlled',
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--window-size=1600,1000'
    ]
  });
  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) ' +
    'AppleWebKit/537.36 (KHTML, like Gecko) ' +
    'Chrome/122.0.0.0 Safari/537.36');
  await page.setExtraHTTPHeaders({ 'Accept-Language': 'he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7' });
  await page.goto(START_URL, { waitUntil: 'networkidle2', timeout: 120000 });
  // Dismiss common banners
  try {
    await page.$$eval("button#onetrust-accept-btn-handler, button[aria-label*='accept' i]", bs => bs.forEach(b=>b.click()));
  } catch {}
  await sleep(500);
  // Wait for listing anchors to appear (grid renders late)
  try {
    await page.waitForSelector("a[href*='lawitemid=']", { timeout: 30000 });
  } catch {}
  const lawLinks = await collectListingLawLinks(page, 3); // probe first 3 listing pages
  console.log(`Listing law links (first 3 pages): ${lawLinks.length}`);

  let total = 0;
  const samples = [];
  for (const url of lawLinks.slice(0, 15)) {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    const pdfs = await collectPdfLinksFromLaw(page, 3); // probe up to 3 pagination steps per law
    total += pdfs.length;
    samples.push({ url, count: pdfs.length, sample: pdfs.slice(0,5) });
  }
  console.log(JSON.stringify({ lawPagesProbed: samples.length, totalPdfsFound: total, pages: samples }, null, 2));
  await browser.close();
}

main().catch(err => { console.error(err); process.exit(1); });
