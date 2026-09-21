// Optional browser QA: PLAYWRIGHT_MODULE can point to an existing Playwright installation.
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { createGame, legalMoves, move, status, CELLS } from '../game-core.js';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const puzzles = JSON.parse(readFileSync(new URL('../generated-puzzles.json', import.meta.url)));
const solutions = JSON.parse(readFileSync(new URL('../generated-solutions.json', import.meta.url)));
const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_EXECUTABLE ? { executablePath: process.env.CHROME_EXECUTABLE } : {}) });
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:4173';
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, reducedMotion: 'reduce' });
const errors = [];
page.on('pageerror', e => errors.push(e.message));
await page.addInitScript(() => { Math.random = () => 0; });
const hole = ([r,c]) => page.locator(`.hole[data-row="${r}"][data-col="${c}"]`);
const layout = async () => {
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  const box = await page.locator('#board').boundingBox();
  assert.ok(box.x >= 0 && box.x+box.width <= (await page.viewportSize()).width);
};
const playStep = async s => {
  await hole(s.from).tap();
  assert.ok(await hole(s.to).evaluate(el=>el.classList.contains('target')));
  await hole(s.to).tap();
};
try {
  await page.goto(base);
  await page.locator('#start-button:enabled').waitFor();
  assert.equal(await page.locator('input[name="peg-count"]').count(),28);
  await page.screenshot({ path:'/tmp/peg-start-mobile.png', fullPage:true });
  await page.locator('label').filter({has:page.locator('input[value="5"]')}).tap();
  await page.locator('#start-button').tap();
  assert.equal(await page.locator('#remaining').textContent(),'5');
  assert.equal(await page.locator('.hole').count(),33);
  const boardSnapshot = () => page.locator('.hole').evaluateAll(holes => holes.filter(h => h.querySelector('.peg')).map(h => `${h.dataset.row},${h.dataset.col}`).join(';'));
  const original = await boardSnapshot();
  await playStep(solutions['5'][0][0]);
  assert.equal(await page.locator('#remaining').textContent(),'4');
  assert.equal(await page.locator('#move-count').textContent(),'1');
  await page.locator('#undo').tap();
  assert.equal(await page.locator('#remaining').textContent(),'5');
  await playStep(solutions['5'][0][0]);
  await playStep(solutions['5'][0][1]);
  await page.locator('#undo').tap(); await page.locator('#undo').tap();
  assert.equal(await page.locator('#move-count').textContent(),'0');
  for(const step of solutions['5'][0]) await playStep(step);
  assert.equal(await page.locator('#message-title').textContent(),'CLEAR！');
  assert.equal(await page.locator('#move-count').textContent(),'4');
  assert.equal(await page.locator('#next').textContent(),'同じペグ数でもう1問');
  await page.screenshot({path:'/tmp/peg-clear-mobile.png',fullPage:true});
  await page.locator('#undo').tap();
  assert.equal(await page.locator('#remaining').textContent(),'2');
  await page.locator('#reset').tap();
  assert.equal(await boardSnapshot(),original);
  await page.locator('#next').tap();
  assert.notEqual(await boardSnapshot(),original);
  // Every supported count is selectable; no counts or difficulty labels are exposed.
  for(let n=5;n<=32;n++){
    await page.locator('#change-count').tap();
    await page.locator('label').filter({has:page.locator(`input[value="${n}"]`)}).tap();
    await page.locator('#start-button').tap();
    assert.equal(await page.locator('#remaining').textContent(),String(n));
  }
  await layout();
  await page.screenshot({path:'/tmp/peg-game-mobile.png',fullPage:true});
  await page.setViewportSize({width:320,height:568}); await layout();
  await page.screenshot({path:'/tmp/peg-game-small.png',fullPage:true});
  await page.setViewportSize({width:1280,height:900}); await layout();
  await page.screenshot({path:'/tmp/peg-game-desktop.png',fullPage:true});
  // Find a losing branch from an actual saved puzzle, without fabricating UI data.
  function deadPath(game,path=[]){
    if(status(game.board)==='stuck')return path;
    if(status(game.board)==='clear')return null;
    for(const step of legalMoves(game.board)){
      const found=deadPath(move(game,step.from,step.to),[...path,{from:CELLS[step.from],to:CELLS[step.to]}]);
      if(found)return found;
    }
    return null;
  }
  const dead=deadPath(createGame(puzzles['5'][0])); assert.ok(dead);
  // New page resets the deterministic problem selector.
  await page.reload(); await page.locator('#start-button:enabled').waitFor();
  await page.locator('label').filter({has:page.locator('input[value="5"]')}).click();
  await page.locator('#start-button').click();
  for(const step of dead)await playStep(step);
  assert.equal(await page.locator('#message-title').textContent(),'これ以上動かせません');
  await page.locator('#undo').click(); assert.notEqual(await page.locator('#message-title').textContent(),'これ以上動かせません');
  await page.locator('#reset').click(); assert.equal(await page.locator('#remaining').textContent(),'5');
  // Motion-enabled path also completes one move once.
  await page.emulateMedia({reducedMotion:'no-preference'});
  await playStep(solutions['5'][0][0]);
  await page.waitForFunction(()=>document.querySelector('#move-count').textContent==='1');
  assert.equal(await page.locator('#remaining').textContent(),'4');
  // Loading failure is recoverable by retry.
  let fail=true;
  await page.route('**/generated-puzzles.json',route=>fail?route.abort():route.continue());
  await page.reload(); await page.locator('#retry:visible').waitFor();
  assert.ok(await page.locator('#start-button').isDisabled());
  fail=false; await page.locator('#retry').click(); await page.locator('#start-button:enabled').waitFor();
  assert.deepEqual(errors,[]);
  console.log('OK: mobile taps, all 28 counts, full solve, undo/reset, distinct next, dead end, animation, retry, 320/390/1280px layouts; no JS errors.');
} finally { await browser.close(); }
