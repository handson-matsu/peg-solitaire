#!/usr/bin/env python3
"""Exact game analysis with a provisional, common-scale human-difficulty proxy."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent
CELLS = [(r, c) for r in range(7) for c in range(7) if 2 <= r <= 4 or 2 <= c <= 4]
INDEX = {cell: i for i, cell in enumerate(CELLS)}
CAP = 10**18


def canonical(coordinates):
    boards = []
    for reflection in (False, True):
        for turns in range(4):
            value = 0
            for row, col in coordinates:
                if reflection:
                    col = 6 - col
                for _ in range(turns):
                    row, col = col, 6 - row
                value |= 1 << INDEX[row, col]
            boards.append(value)
    return min(boards)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summary(values):
    return dict(count=len(values), min=min(values), max=max(values), median=statistics.median(values))


def histogram(values, step=10):
    return [sum(low <= x < low + step or (low + step == 100 and x == 100) for x in values)
            for low in range(0, 100, step)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=180, help='C++ analysis time limit; no sampling')
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 3600:
        parser.error('--seconds must be in (0, 3600]')
    inputs = [ROOT / 'generated-puzzles.json', ROOT / 'generated-solutions.json']
    hashes = {p.name: digest(p) for p in inputs}
    puzzles, solutions = [json.loads(p.read_text()) for p in inputs]
    # Verify original data before analysis, including the supplied solution paths.
    subprocess.run(['python3', str(ROOT / 'verify.py'), str(ROOT)], check=True)
    queries, paths = set(), {}
    for key, boards in puzzles.items():
        for index, coordinates in enumerate(boards):
            state = {tuple(c) for c in coordinates}
            path = []
            for step in solutions[key][index]:
                encoded = canonical(state)
                queries.add(encoded)
                path.append(encoded)
                state.remove(tuple(step['from']))
                state.remove(tuple(step['over']))
                state.add(tuple(step['to']))
            paths[key, index] = path
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='peg-difficulty-') as work:
        work = Path(work)
        binary = work / 'engine'
        subprocess.run([os.environ.get('CXX', 'c++'), '-O3', '-std=c++17', '-Wall', '-Wextra', '-pedantic',
                        str(ROOT / 'difficulty-engine.cpp'), '-o', str(binary)], check=True, timeout=60)
        (work / 'queries.txt').write_text('\n'.join(map(str, sorted(queries))))
        subprocess.run([str(binary), str(work / 'queries.txt'), str(work / 'metrics.tsv'), str(args.seconds)],
                       check=True, timeout=args.seconds + 30)
        metrics = {}
        with (work / 'metrics.tsv').open() as stream:
            for row in csv.DictReader(stream, delimiter='\t'):
                converted = {key: (int(value) if key in ('board', 'pegs', 'legal', 'winning', 'solutionCountCapped')
                                   else float(value)) for key, value in row.items()}
                metrics[converted['board']] = converted
    results = []
    for key, boards in puzzles.items():
        pegs = int(key)
        length = pegs - 1
        for index, coordinates in enumerate(boards):
            route = [metrics[b] for b in paths[key, index]]
            m = route[0]
            surprise = -math.log2(m['randomSuccess'])
            # Bit-equivalent load. Forced traps excludes automatic moves (L=W=1).
            load = 0.6 * surprise + 0.3 * m['decisionBits'] + 0.1 * m['forcedTrapSum']
            score = -100 * math.expm1(-load / 12)
            result = {
                'pegCount': pegs,
                'puzzleIndex': index,
                'board': coordinates,
                'difficultyScore': score,
                'legalFirstMoves': m['legal'],
                'winningFirstMoves': m['winning'],
                'firstMoveTrapRate': 1 - m['winning'] / m['legal'],
                'solutionCount': str(m['solutionCountCapped']),
                'solutionCountCapped': m['solutionCountCapped'] == CAP,
                'solutionCountLog10': math.log10(m['solutionCountApprox']),
                'solutionCountApprox': m['solutionCountApprox'],
                'averageLegalMoves': m['legalSum'] / length,
                'averageWinningMoves': m['winningSum'] / length,
                'trapMoveRate': m['trapSum'] / length,
                'moveWeightedTrapRate': 1 - m['winningSum'] / m['legalSum'],
                'forcedMoveRate': m['forcedSum'] / length,
                'forcedWithAlternativesRate': m['forcedTrapSum'] / length,
                'randomLegalPlayWinProbability': m['randomSuccess'],
                'randomPlaySurprisalBits': surprise,
                'expectedDecisionBits': m['decisionBits'],
                'decisionLoad': load,
                'savedSolutionMetrics': {
                    'averageLegalMoves': statistics.mean(x['legal'] for x in route),
                    'averageWinningMoves': statistics.mean(x['winning'] for x in route),
                    'trapMoveRate': statistics.mean(1 - x['winning'] / x['legal'] for x in route),
                    'forcedMoveRate': statistics.mean(x['winning'] == 1 for x in route),
                    'forcedWithAlternativesRate': statistics.mean(x['winning'] == 1 and x['legal'] > 1 for x in route),
                    'decisionBits': sum(math.log2(x['legal'] / x['winning']) for x in route),
                },
            }
            results.append(result)
    assert all(digest(p) == hashes[p.name] for p in inputs), 'Input data changed'
    scores = [x['difficultyScore'] for x in results]
    meta = {
        'version': 1,
        'inputSha256': hashes,
        'problemCount': len(results),
        'analysis': 'exact central-goal reachability and dynamic programming; no beam pruning',
        'solutionDefinition': 'ordered sequences of coordinate jumps; symmetric sequences and different move orders are distinct',
        'solutionCountCap': str(CAP),
        'solutionCountNote': 'decimal string; capped=true means >= cap; log10 and approximate count use floating-point DP',
        'routePolicy': 'uniform choice among winning moves at each state; expected sums divided by pegCount-1; terminal excluded',
        'puzzleIndexNote': 'zero-based index in the original per-peg array',
        'difficultyFormula': '100*(1-exp(-(0.6*(-log2(P))+0.3*B+0.1*F)/12))',
        'formulaVariables': {'P': 'win probability when choosing uniformly among ALL legal moves',
                             'B': 'expected sum log2(legal/winning) under routePolicy',
                             'F': 'expected count of states with winning=1 and legal>1 under routePolicy'},
        'calibration': 'provisional heuristic, not validated against human play data',
        'overallScore': summary(scores),
        'proposedStarThresholds': [60, 80],
        'starThresholdStatus': 'provisional common-scale thresholds, not per-peg quantiles; no star labels assigned',
        'elapsedSecondsIncludingCompilation': time.monotonic() - started,
    }
    report = build_report(meta, results)
    # Publish only after a complete analysis; original inputs are read-only throughout.
    for name, content in [('difficulty-analysis.json', json.dumps({'metadata': meta, 'puzzles': results},
                                                                 ensure_ascii=False, indent=2, allow_nan=False) + '\n'),
                          ('difficulty-report.txt', report)]:
        target = ROOT / name
        temporary = target.with_suffix(target.suffix + '.tmp')
        temporary.write_text(content)
        temporary.replace(target)
    print(report)


def build_report(meta, results):
    scores = [x['difficultyScore'] for x in results]
    stats = summary(scores)
    lines = ['ペグソリティア難易度解析（中央1個ゴール）', '',
             f"対象: {len(results):,}問 / 所要時間: {meta['elapsedSecondsIncludingCompilation']:.2f}秒（コンパイル含む）",
             '全到達可能クラスを逆列挙し、通常手の動的計画法で厳密判定。間引き・乱択推定なし。',
             f"全体 difficultyScore: 最小 {stats['min']:.4f} / 最大 {stats['max']:.4f} / 中央値 {stats['median']:.4f}",
             f"解法数の最大（近似）: {max(x['solutionCountApprox'] for x in results):.8e}",
             f"解法数が10^18以上の問題: {sum(x['solutionCountCapped'] for x in results)}問（対数値も保存）",
             '', 'ペグ数 | 問題数 | 最小 | 最大 | 中央値']
    for pegs in range(5, 33):
        s = summary([x['difficultyScore'] for x in results if x['pegCount'] == pegs])
        lines.append(f"{pegs:2} | {s['count']:3} | {s['min']:.4f} | {s['max']:.4f} | {s['median']:.4f}")
    lines += ['', 'difficultyScore 分布（左端を含み右端を含まない。最終区間のみ100を含む）']
    for low, count in zip(range(0, 100, 10), histogram(scores)):
        lines.append(f'{low:2}〜{low+10:3}: {count:4} ({100*count/len(scores):5.2f}%) ' + '█' * round(count / 25))
    ordered = sorted(scores)
    lines += ['', '全体の分位点（補間による参考値）']
    for q in (0.1, 0.25, 0.5, 0.75, 0.9, 0.95):
        p = (len(ordered)-1)*q
        lo, hi = math.floor(p), math.ceil(p)
        v = ordered[lo] + (ordered[hi]-ordered[lo])*(p-lo)
        lines.append(f'{q*100:g}%: {v:.4f}')
    buckets = [sum(s < 60 for s in scores), sum(60 <= s < 80 for s in scores), sum(s >= 80 for s in scores)]
    lines += ['', '★分類を設ける場合の暫定候補（今回は各問に分類を付けない）',
              f'★1: score < 60       : {buckets[0]}問',
              f'★2: 60 <= score < 80 : {buckets[1]}問',
              f'★3: 80 <= score      : {buckets[2]}問',
              '共通の負荷尺度で約11.00 bit相当と19.31 bit相当に境界を置く案。',
              '分布は70〜90に集中し、明確な3群の谷はない。60/80は低負荷側と高密度部分を分ける丸い運用値。',
              '40/70案では★1が113問、★3が1631問に偏るため、今回は60/80案を参考として提示する。',
              '各ペグ数内の3等分や、31・32個の少数問題に合わせた境界調整は行わない。',
              'この境界は暫定的な運用案であり、自然な3群の存在や人間の難度を実証するものではない。',
              '問題の抽出は人間の難度に関して無作為ではない。全体分布にも問題数の構成比が影響する。',
              'プレイ時間・失敗回数・ヒント使用率を収集した後、共通の境界と係数を校正する。',
              '', '指標・評価式',
              'L(s): 合法手数。W(s): 子が中央1個へ到達可能な合法手数。',
              '解法は座標付きジャンプの順序列。対称な手順や独立した手の順序違いも別解とする。',
              '対称性は計算のメモ化にのみ使い、異なる合法手を重複除去して解法数を減らさない。',
              'C(goal)=1、C(s)=Σ C(child)。負け状態のC=0。',
              'solutionCountは10^18で飽和させた整数文字列。Capped=trueのとき下限値。',
              'solutionCountLog10とsolutionCountApproxは浮動小数点の加算DPで計算した近似値。',
              '手数は最大31、各局面の候補手は最大76なのでC<=76^31<10^59。doubleの範囲内。',
              'P(goal)=1、P(s)=Σ P(child)/L(s)。全合法手を一様に選ぶプレイの成功確率。',
              '解けない局面に移った場合は成功確率0。Pは人間の成功率ではない。',
              'ルート統計は各局面で正解手W本から一様に選ぶ方策の期待値。',
              'すべての正解ルートを扱うが、完成した解法を一様抽出する重み付けではない。',
              '各統計を「現在値 + 正解の子の期待値の平均」で計算し、pegCount-1で割る。',
              '最終中央1個の局面は分母に含めない。合法手数・正解手数は座標上の手の本数。',
              'trapMoveRate = E[Σ (L-W)/L] / (pegCount-1)。局面ごとの罠率の平均。',
              'moveWeightedTrapRate = 1-E[ΣW]/E[ΣL]。選択肢の数で重み付けした別指標。',
              'forcedMoveRate = E[Σ 1(W=1)] / (pegCount-1)。自明な唯一手も含む。',
              'forcedWithAlternativesRate = E[Σ 1(W=1 and L>1)] / (pegCount-1)。罠の中の唯一正解。',
              '保存済み解法に沿う統計もsavedSolutionMetricsとして別記する。',
              '', 'B = E[Σ log2(L/W)]、F = E[Σ 1(W=1 and L>1)]',
              '負荷 D = 0.6*(-log2(P)) + 0.3*B + 0.1*F',
              'difficultyScore = 100*(1-exp(-D/12))',
              '', '採用理由',
              'Pは正解の総量と各手の分岐を併せて扱う。解法数だけが膨大でも罠が多ければ難度が上がる。',
              'Bは正解ルート上で必要な選択の厳しさを積算し、Pだけでは薄れる継続的な判断負荷を補う。',
              'Fは多数の罠から唯一の正解を選ぶ局面を軽く加点する。L=W=1の自動的な手は加点しない。',
              'ペグ数そのものは加点しない。同じ長さでも罠や正解の広さにより値が変わる。',
              '長い問題は難しい選択が累積すれば高くなるが、全手が安全なら長くても0になる。',
              '100への滑らかな単調変換で連続値に保ち、12は表示の広がりを決める固定定数。',
              '0.6/0.3/0.1と12は理論上唯一の値ではなく、実測校正前の説明可能な仮設定。',
              '局面を読むための先読み深さ、見た目の認識、定石の知識、操作負荷は直接測っていない。',
              '数学的な到達判定は厳密だが、人間にとっての難しさの妥当性には別途プレイ検証が必要。',
              '', '入力SHA-256（解析前後で一致）']
    lines += [f'{name}: {value}' for name, value in meta['inputSha256'].items()]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    main()
