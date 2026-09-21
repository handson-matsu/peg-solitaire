/** Pure game rules. BigInt preserves all 33 holes (JS bitwise numbers only hold 32). */
export const CELLS = Object.freeze(Array.from({ length: 7 }, (_, r) =>
  Array.from({ length: 7 }, (_, c) => [r, c])).flat()
  .filter(([r, c]) => (r >= 2 && r <= 4) || (c >= 2 && c <= 4)));
const indices = new Map(CELLS.map(([r, c], i) => [`${r},${c}`, i]));
export const indexAt = (r, c) => indices.get(`${r},${c}`);
export const CENTER = indexAt(3, 3);
export const bit = i => 1n << BigInt(i);
export const hasPeg = (board, i) => (board & bit(i)) !== 0n;
export const MOVES = Object.freeze(CELLS.flatMap(([r, c], from) =>
  [[1, 0], [-1, 0], [0, 1], [0, -1]].flatMap(([dr, dc]) => {
    const over = indexAt(r + dr, c + dc), to = indexAt(r + 2 * dr, c + 2 * dc);
    return over === undefined || to === undefined ? [] : [{ from, over, to }];
  })));
export function encode(coordinates) {
  let board = 0n;
  for (const cell of coordinates) {
    if (!Array.isArray(cell) || cell.length !== 2) throw new Error('Invalid hole');
    const i = indexAt(...cell);
    if (i === undefined || hasPeg(board, i)) throw new Error('Invalid or duplicate hole');
    board |= bit(i);
  }
  return board;
}
export const pegCount = board => CELLS.reduce((n, _, i) => n + Number(hasPeg(board, i)), 0);
export const legalMoves = board => MOVES.filter(({ from, over, to }) =>
  hasPeg(board, from) && hasPeg(board, over) && !hasPeg(board, to));
export function status(board) {
  if (board === bit(CENTER)) return 'clear';
  return legalMoves(board).length ? 'playing' : 'stuck';
}
export function createGame(coordinates) {
  const initial = encode(coordinates);
  return { initial, board: initial, history: [] };
}
export function move(game, from, to) {
  const candidate = legalMoves(game.board).find(m => m.from === from && m.to === to);
  if (!candidate) return null;
  return { ...game, board: game.board ^ bit(from) ^ bit(candidate.over) ^ bit(to),
    history: [...game.history, game.board] };
}
export function undo(game) {
  if (!game.history.length) return game;
  return { ...game, board: game.history.at(-1), history: game.history.slice(0, -1) };
}
export const reset = game => ({ ...game, board: game.initial, history: [] });
export function chooseIndex(length, previous = -1, random = Math.random) {
  if (!Number.isInteger(length) || length < 1) throw new Error('No puzzles');
  if (length === 1) return 0;
  const exclude = previous >= 0 && previous < length;
  const value = Math.floor(random() * (length - Number(exclude)));
  return exclude && value >= previous ? value + 1 : value;
}
export function validatePuzzles(data) {
  for (let n = 5; n <= 32; n++) {
    if (!Array.isArray(data[n]) || !data[n].length) throw new Error(`Missing puzzles: ${n}`);
    for (const coordinates of data[n]) {
      if (!Array.isArray(coordinates) || coordinates.length !== n || pegCount(encode(coordinates)) !== n)
        throw new Error(`Invalid puzzle: ${n}`);
    }
  }
  return data;
}
