import { CELLS, CENTER, hasPeg, pegCount, legalMoves, status, createGame, move, undo, reset,
  chooseIndex, validatePuzzles } from './game-core.js';

const $ = id => document.getElementById(id);
let puzzles, game, selected = null, busy = false, currentIndex = -1, currentCount = 7;
const lastIndices = new Map();
const buttons = [];
for (let n = 5; n <= 32; n++) {
  const label = document.createElement('label');
  label.className = 'peg-option';
  const radio = document.createElement('input');
  radio.type = 'radio'; radio.name = 'peg-count'; radio.value = n;
  radio.setAttribute('aria-label', `${n}個`); radio.checked = n === currentCount;
  label.append(radio, document.createTextNode(n));
  $('peg-picker').append(label);
}
for (const [i, [r, c]] of CELLS.entries()) {
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'hole';
  button.style.gridRow = r + 1; button.style.gridColumn = c + 1;
  button.dataset.row = r; button.dataset.col = c;
  button.addEventListener('click', () => tap(i));
  buttons.push(button); $('board').append(button);
}
async function load() {
  $('retry').hidden = true; $('load-status').textContent = '';
  $('start-button').disabled = true; $('start-button').textContent = '読み込み中…';
  try {
    const response = await fetch(new URL('./generated-puzzles.json', import.meta.url));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    puzzles = validatePuzzles(await response.json());
    $('start-button').disabled = false; $('start-button').textContent = 'スタート';
  } catch {
    $('load-status').textContent = '問題を読み込めませんでした。通信を確認して、もう一度お試しください。';
    $('start-button').textContent = 'スタート'; $('retry').hidden = false;
  }
}
function start(count) {
  if (busy || !puzzles) return;
  currentCount = count;
  currentIndex = chooseIndex(puzzles[count].length, lastIndices.get(count) ?? -1);
  lastIndices.set(count, currentIndex);
  game = createGame(puzzles[count][currentIndex]); selected = null;
  $('start-screen').hidden = true; $('game-screen').hidden = false;
  render(); $('message-title').focus({ preventScroll: true });
}
function render() {
  const state = status(game.board);
  const destinations = new Set(legalMoves(game.board).filter(m => m.from === selected).map(m => m.to));
  for (const [i, button] of buttons.entries()) {
    const occupied = hasPeg(game.board, i), target = destinations.has(i);
    button.className = ['hole', i === CENTER ? 'center' : '', selected === i ? 'selected' : '', target ? 'target' : ''].filter(Boolean).join(' ');
    button.replaceChildren();
    if (occupied) { const peg = document.createElement('span'); peg.className = 'peg'; button.append(peg); }
    button.disabled = busy || state !== 'playing' || (!occupied && !target);
    button.setAttribute('aria-pressed', String(selected === i));
    const [r, c] = CELLS[i];
    button.setAttribute('aria-label', `${r + 1}行${c + 1}列${i === CENTER ? ' 中央' : ''}、${occupied ? 'ペグ' : target ? '移動できる穴' : '空き穴'}${selected === i ? '、選択中' : ''}`);
  }
  $('remaining').textContent = pegCount(game.board);
  $('move-count').textContent = game.history.length;
  $('message').className = `message ${state}`;
  if (state === 'clear') {
    $('message-title').textContent = 'CLEAR！';
    $('message-detail').textContent = `${game.history.length}手でクリア！ 最後の1個が中央に。`;
  } else if (state === 'stuck') {
    $('message-title').textContent = 'これ以上動かせません';
    $('message-detail').textContent = pegCount(game.board) === 1 ? '最後の1個は中央へ。1手戻して考えよう。' : '1手戻すか、リセットでもう一度。';
  } else {
    $('message-title').textContent = selected === null ? '動かすペグをタップ' : destinations.size ? '輪のある穴へジャンプ！' : 'このペグは動かせません';
    $('message-detail').textContent = selected === null ? '最後の1個は、中央の穴へ。' : destinations.size ? '移動先の穴をタップしてください。' : '別のペグを選んでみよう。';
  }
  $('undo').disabled = busy || !game.history.length;
  $('reset').disabled = busy;
  $('next').disabled = busy;
  $('change-count').disabled = busy;
  $('next').textContent = state === 'clear' ? '同じペグ数でもう1問' : '別の問題';
}
async function tap(i) {
  if (busy || status(game.board) !== 'playing') return;
  if (hasPeg(game.board, i)) {
    selected = selected === i ? null : i; render(); return;
  }
  if (selected === null) return;
  const nextGame = move(game, selected, i);
  if (!nextGame) return;
  const from = selected;
  busy = true;
  render();
  // A short jump; state changes only once, and controls are locked during motion.
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches && Element.prototype.animate) {
    const a = buttons[from].getBoundingClientRect(), b = buttons[i].getBoundingClientRect();
    const ghost = document.createElement('span'); ghost.className = 'jump-peg';
    ghost.style.cssText = `left:${a.left + a.width * .06}px;top:${a.top + a.height * .06}px;width:${a.width * .88}px;height:${a.height * .88}px`;
    document.body.append(ghost); buttons[from].querySelector('.peg').style.visibility = 'hidden';
    try {
      await ghost.animate([{ transform: 'translate(0,0) scale(1)' },
        { transform: `translate(${(b.left-a.left)/2}px,${(b.top-a.top)/2-12}px) scale(1.12)`, offset: .5 },
        { transform: `translate(${b.left-a.left}px,${b.top-a.top}px) scale(1)` }],
      { duration: 180, easing: 'ease-in-out' }).finished;
    } catch { /* Interrupted animation still completes the legal move. */ }
    finally { ghost.remove(); }
  }
  game = nextGame; selected = null; busy = false; render();
  if (status(game.board) !== 'playing') $('message-title').focus({ preventScroll: true });
  else buttons[i].focus({ preventScroll: true });
}
$('start-form').addEventListener('submit', event => {
  event.preventDefault(); start(Number(new FormData(event.currentTarget).get('peg-count')));
});
$('undo').addEventListener('click', () => { if (!busy) { game = undo(game); selected = null; render(); } });
$('reset').addEventListener('click', () => { if (!busy) { game = reset(game); selected = null; render(); } });
$('next').addEventListener('click', () => start(currentCount));
$('change-count').addEventListener('click', () => {
  if (busy) return;
  selected = null; $('game-screen').hidden = true; $('start-screen').hidden = false;
  document.querySelector(`input[value="${currentCount}"]`).focus({ preventScroll: true });
});
$('retry').addEventListener('click', load);
document.addEventListener('keydown', event => { if (event.key === 'Escape' && game && !busy) { selected = null; render(); } });
load();

// Record one visit per page load without waiting for the response or retrying.
try {
  fetch('https://script.google.com/macros/s/AKfycbxssCIHsD-N97SHxNC_GN0ihYeC0qy-lb-EY0KmSs6Gnztaph1sITMerLVEnNWOGkYc/exec?app=peg-solitaire', {
    method: 'GET',
    mode: 'no-cors',
    cache: 'no-store',
    credentials: 'omit',
    keepalive: true,
  }).catch(() => {});
} catch {
  // Access logging must never interrupt the game.
}
