#!/usr/bin/env python3
"""Verify output integrity and compare low-peg metrics to an independent raw-state solver."""
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent
CELLS = {(r, c) for r in range(7) for c in range(7) if 2 <= r <= 4 or 2 <= c <= 4}


def children(state):
    occupied = set(state)
    for r, c in state:
        for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            over, target = (r + dr, c + dc), (r + 2 * dr, c + 2 * dc)
            if over in occupied and target in CELLS and target not in occupied:
                yield tuple(sorted(occupied - {(r, c), over} | {target}))


@lru_cache(None)
def solve(state):
    # No symmetry reduction, bitboards, or reverse-generation lookup here.
    if len(state) == 1:
        won = state == ((3, 3),)
        return (int(won), float(won), 0., 0., 0., 0., 0., 0.)
    descendants = [solve(child) for child in children(state)]
    winners = [child for child in descendants if child[0]]
    legal, winning = len(descendants), len(winners)
    if not winning:
        return (0, 0., 0., 0., 0., 0., 0., 0.)
    local = (legal, winning, (legal-winning)/legal, float(winning == 1),
             float(winning == 1 and legal > 1), math.log2(legal/winning))
    return (sum(x[0] for x in winners), sum(x[1] for x in winners)/legal,
            *(value + sum(x[i+2] for x in winners)/winning for i, value in enumerate(local)))


def close(a, b):
    assert math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10), (a, b)


def main():
    data = json.loads((ROOT / 'difficulty-analysis.json').read_text())
    originals = json.loads((ROOT / 'generated-puzzles.json').read_text())
    solutions = json.loads((ROOT / 'generated-solutions.json').read_text())
    for name, digest in data['metadata']['inputSha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    assert len(data['puzzles']) == sum(map(len, originals.values())) == 2498
    seen, exact_checks = set(), 0
    for puzzle in data['puzzles']:
        n, i = puzzle['pegCount'], puzzle['puzzleIndex']
        key = str(n)
        assert (n, i) not in seen
        seen.add((n, i))
        assert puzzle['board'] == originals[key][i]
        state = tuple(sorted(tuple(cell) for cell in puzzle['board']))
        assert puzzle['legalFirstMoves'] == len(list(children(state)))
        assert 1 <= puzzle['winningFirstMoves'] <= puzzle['legalFirstMoves']
        for name in ('trapMoveRate', 'forcedMoveRate', 'forcedWithAlternativesRate', 'moveWeightedTrapRate'):
            assert 0 <= puzzle[name] <= 1
        assert 0 <= puzzle['difficultyScore'] < 100
        assert 0 < puzzle['randomLegalPlayWinProbability'] <= 1
        close(puzzle['solutionCountLog10'], math.log10(puzzle['solutionCountApprox']))
        assert puzzle['solutionCountCapped'] == (int(puzzle['solutionCount']) == 10**18)
        if not puzzle['solutionCountCapped']:
            close(puzzle['solutionCountApprox'], int(puzzle['solutionCount']))
        close(puzzle['randomPlaySurprisalBits'], -math.log2(puzzle['randomLegalPlayWinProbability']))
        # Jensen: the successful-route decision bit expectation bounds -log2(P) above.
        assert puzzle['expectedDecisionBits'] + 1e-9 >= puzzle['randomPlaySurprisalBits']
        load = (0.6 * puzzle['randomPlaySurprisalBits'] + 0.3 * puzzle['expectedDecisionBits']
                + 0.1 * (n-1) * puzzle['forcedWithAlternativesRate'])
        close(puzzle['difficultyScore'], -100 * math.expm1(-load/12))
        legal_along_route = []
        board = set(state)
        for move in solutions[key][i]:
            legal_along_route.append(len(list(children(tuple(sorted(board))))))
            board.remove(tuple(move['from']))
            board.remove(tuple(move['over']))
            board.add(tuple(move['to']))
        close(statistics.mean(legal_along_route), puzzle['savedSolutionMetrics']['averageLegalMoves'])
        if n <= 7:
            expected = solve(state)
            assert int(puzzle['solutionCount']) == expected[0]
            assert not puzzle['solutionCountCapped']
            close(puzzle['solutionCountApprox'], expected[0])
            close(puzzle['solutionCountLog10'], math.log10(expected[0]))
            close(puzzle['randomLegalPlayWinProbability'], expected[1])
            names = ('averageLegalMoves', 'averageWinningMoves', 'trapMoveRate', 'forcedMoveRate',
                     'forcedWithAlternativesRate', 'expectedDecisionBits')
            for j, name in enumerate(names):
                close(puzzle[name], expected[j+2] / (n-1) if j < 5 else expected[j+2])
            assert puzzle['winningFirstMoves'] == sum(solve(child)[0] > 0 for child in children(state))
            exact_checks += 1
    print(f'OK: all {len(seen)} records, original hashes, first moves, saved-route legal counts, score formulas.')
    print(f'OK: {exact_checks} puzzles (5–7 pegs) agree with independent exhaustive forward search on all main metrics.')


if __name__ == '__main__':
    main()
