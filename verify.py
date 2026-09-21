#!/usr/bin/env python3
"""Independently validate every saved board, D4 uniqueness, and solution."""
import json
from pathlib import Path

CELLS = {(r, c) for r in range(7) for c in range(7)
         if 2 <= r <= 4 or 2 <= c <= 4}


def canonical(board):
    variants = []
    for reflect in (False, True):
        for turns in range(4):
            transformed = []
            for r, c in board:
                if reflect:
                    c = 6 - c
                for _ in range(turns):
                    r, c = c, 6 - r
                transformed.append((r, c))
            variants.append(tuple(sorted(transformed)))
    return min(variants)


def verify(directory=Path('.')):
    puzzles = json.loads((directory / 'generated-puzzles.json').read_text())
    solutions = json.loads((directory / 'generated-solutions.json').read_text())
    expected = {str(k) for k in range(5, 33)}
    assert set(puzzles) == set(solutions) == expected
    total = 0
    for key in sorted(expected, key=int):
        assert len(puzzles[key]) == len(solutions[key]) <= 100
        seen = set()
        for coordinates, steps in zip(puzzles[key], solutions[key]):
            board = {tuple(p) for p in coordinates}
            assert len(board) == len(coordinates) == int(key)
            assert board <= CELLS
            representative = canonical(board)
            assert representative not in seen, (key, 'symmetry duplicate')
            seen.add(representative)
            assert len(steps) == int(key) - 1
            for step in steps:
                assert set(step) == {'from', 'over', 'to'}
                a, b, c = (tuple(step[name]) for name in ('from', 'over', 'to'))
                assert {a, b, c} <= CELLS
                assert abs(a[0] - c[0]) + abs(a[1] - c[1]) == 2
                assert a[0] == c[0] or a[1] == c[1]
                assert (a[0] + c[0], a[1] + c[1]) == (2*b[0], 2*b[1])
                assert a in board and b in board and c not in board
                board.remove(a)
                board.remove(b)
                board.add(c)
            assert board == {(3, 3)}
            total += 1
    print(f'OK: {total} puzzles; legal solutions, center finish, and D4 uniqueness verified.')


if __name__ == '__main__':
    import sys
    verify(Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.'))
