import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CELLS, CENTER, MOVES, bit, encode, indexAt, pegCount, legalMoves, status,
  createGame, move, undo, reset, chooseIndex, validatePuzzles } from '../game-core.js';
const puzzles = JSON.parse(readFileSync(new URL('../generated-puzzles.json', import.meta.url)));
const solutions = JSON.parse(readFileSync(new URL('../generated-solutions.json', import.meta.url)));

test('33 holes, 76 orthogonal jumps, and bit 32 remains distinct', () => {
  assert.equal(CELLS.length, 33); assert.equal(MOVES.length, 76);
  assert.equal(encode([[6, 4]]), 1n << 32n);
  assert.equal(pegCount(encode([[0, 2], [6, 4]])), 2);
});
test('all 2,498 original puzzles solve through game rules, undo fully, and reset', () => {
  validatePuzzles(puzzles); let total = 0;
  for (let n = 5; n <= 32; n++) for (const [i, coordinates] of puzzles[n].entries()) {
    let game = createGame(coordinates);
    for (const [j, step] of solutions[n][i].entries()) {
      assert.equal(status(game.board), 'playing');
      const before = game;
      game = move(game, indexAt(...step.from), indexAt(...step.to));
      assert.ok(game); assert.equal(pegCount(game.board), n - j - 1);
      assert.equal(game.history.length, j + 1);
      assert.equal(undo(game).board, before.board);
    }
    assert.equal(game.board, bit(CENTER)); assert.equal(status(game.board), 'clear');
    assert.equal(game.history.length, n - 1);
    assert.equal(reset(game).board, game.initial); assert.equal(reset(game).history.length, 0);
    while (game.history.length) game = undo(game);
    assert.equal(game.board, encode(coordinates)); assert.strictEqual(undo(game), game);
    total++;
  }
  assert.equal(total, 2498);
});
test('illegal diagonal, occupied destination, empty start, and nonadjacent jump rejected', () => {
  const game = createGame([[2, 2], [3, 3], [3, 4], [3, 5]]);
  for (const [a, b] of [[[2,2],[4,4]], [[3,3],[3,5]], [[3,2],[3,4]], [[3,3],[3,6]]]) {
    assert.equal(move(game, indexAt(...a), indexAt(...b)), null);
  }
  assert.equal(game.history.length, 0);
});
test('center-only clear, off-center singleton and isolated pegs are stuck', () => {
  assert.equal(status(encode([[3,3]])), 'clear');
  assert.equal(status(encode([[0,2]])), 'stuck');
  const game = createGame([[0,2],[6,4]]);
  assert.equal(legalMoves(game.board).length, 0); assert.equal(status(game.board), 'stuck');
});
test('dead end remains undoable and resettable', () => {
  let game = createGame([[3,0],[3,1],[0,2]]);
  const initial = game.board;
  game = move(game,indexAt(3,0),indexAt(3,2));
  assert.equal(status(game.board),'stuck');
  assert.equal(undo(game).board,initial); assert.equal(reset(game).board,initial);
});
test('random selection covers every alternative and excludes previous for every peg count', () => {
  for (let n=5;n<=32;n++) {
    const length=puzzles[n].length;
    for (let previous=0;previous<length;previous++) {
      const outcomes = new Set(Array.from({length:length-1},(_,i)=>chooseIndex(length,previous,()=> (i+.5)/(length-1))));
      assert.equal(outcomes.size,length-1); assert.ok(!outcomes.has(previous));
    }
    assert.equal(chooseIndex(length,-1,()=>0),0);
    assert.equal(chooseIndex(length,-1,()=>.999999),length-1);
  }
  assert.equal(chooseIndex(1,0),0);
});
