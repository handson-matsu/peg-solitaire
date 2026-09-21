// Reuse the exact board geometry / D4 implementation without running the generator.
#define PEG_BOARD_ONLY
#include "generator.cpp"
#undef PEG_BOARD_ONLY
#include <cmath>
#include <iomanip>
#include <unordered_map>

// Route statistics use the policy: choose uniformly among winning moves.
// All nonterminal states are included; the final center singleton is excluded.
struct Stats {
    double solutions = 0;
    double randomSuccess = 0;
    double legalSum = 0;
    double winningSum = 0;
    double trapSum = 0;
    double forcedSum = 0;
    double forcedTrapSum = 0;
    double decisionBits = 0;
    uint64_t cappedSolutions = 0;
};
constexpr uint64_t COUNT_CAP = 1000000000000000000ULL;
using Table = std::unordered_map<Board, Stats>;

int main(int argc, char** argv) {
    try {
        if (argc != 4) throw std::runtime_error("Usage: difficulty-engine query-boards.txt metrics.tsv seconds");
        double limit = std::stod(argv[3]);
        if (!(limit > 0)) throw std::runtime_error("Invalid time limit");
        setup();
        std::unordered_set<Board> queries;
        std::ifstream input(argv[1]);
        if (!input) throw std::runtime_error("Cannot open queries");
        Board board;
        while (input >> board) queries.insert(canonical(board));
        if (!input.eof()) throw std::runtime_error("Invalid queries");
        std::ofstream out(argv[2]);
        if (!out) throw std::runtime_error("Cannot open metrics output");
        out << std::setprecision(17);
        out << "board\tpegs\tlegal\twinning\tsolutionCountCapped\tsolutionCountApprox\t"
               "randomSuccess\tlegalSum\twinningSum\ttrapSum\tforcedSum\tforcedTrapSum\tdecisionBits\n";
        auto start = std::chrono::steady_clock::now();
        auto elapsed = [&]() {
            return std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        };
        auto checkTime = [&]() {
            if (elapsed() > limit) throw std::runtime_error("Time limit; no final analysis published");
        };
        Table previous;
        Stats goal;
        goal.solutions = goal.randomSuccess = 1;
        goal.cappedSolutions = 1;
        previous.emplace(Board(1) << ids[3][3], goal);
        size_t answered = 0;
        for (int pegs = 2; pegs <= 32; ++pegs) {
            checkTime();
            Table current;
            current.reserve(std::min(size_t(4000000), previous.size() * 3));
            size_t progress = 0;
            for (const auto& entry : previous) {
                if (++progress % 4096 == 0) checkTime();
                for (const Move& move : moves) {
                    if ((entry.first & move.mask) == move.reverseSource) {
                        current.try_emplace(canonical(entry.first ^ move.mask));
                    }
                }
            }
            progress = 0;
            for (auto& entry : current) {
                if (++progress % 4096 == 0) checkTime();
                int legal = 0, winning = 0;
                Stats& result = entry.second;
                for (const Move& move : moves) {
                    if ((entry.first & move.mask) != (move.mask ^ move.reverseSource)) continue;
                    ++legal;
                    auto found = previous.find(canonical(entry.first ^ move.mask));
                    if (found == previous.end()) continue;
                    ++winning;
                    const Stats& child = found->second;
                    // Distinct coordinate moves are counted even when their children are symmetric.
                    result.solutions += child.solutions;
                    result.cappedSolutions = std::min(COUNT_CAP, result.cappedSolutions + child.cappedSolutions);
                    result.randomSuccess += child.randomSuccess;
                    result.legalSum += child.legalSum;
                    result.winningSum += child.winningSum;
                    result.trapSum += child.trapSum;
                    result.forcedSum += child.forcedSum;
                    result.forcedTrapSum += child.forcedTrapSum;
                    result.decisionBits += child.decisionBits;
                }
                if (!winning) throw std::runtime_error("Reverse / forward reachability mismatch");
                result.randomSuccess /= legal;
                result.legalSum = legal + result.legalSum / winning;
                result.winningSum = winning + result.winningSum / winning;
                result.trapSum = double(legal - winning) / legal + result.trapSum / winning;
                result.forcedSum = (winning == 1) + result.forcedSum / winning;
                result.forcedTrapSum = (winning == 1 && legal > 1) + result.forcedTrapSum / winning;
                result.decisionBits = std::log2(double(legal) / winning) + result.decisionBits / winning;
                if (!std::isfinite(result.solutions) || result.randomSuccess <= 0)
                    throw std::runtime_error("Numerical range failure");
                if (queries.count(entry.first)) {
                    ++answered;
                    out << entry.first << '\t' << pegs << '\t' << legal << '\t' << winning << '\t'
                        << result.cappedSolutions << '\t' << result.solutions << '\t'
                        << result.randomSuccess << '\t' << result.legalSum << '\t' << result.winningSum << '\t'
                        << result.trapSum << '\t' << result.forcedSum << '\t' << result.forcedTrapSum << '\t'
                        << result.decisionBits << '\n';
                }
            }
            std::cout << "pegs=" << pegs << " exact winning classes=" << current.size()
                      << " queries=" << answered << '/' << queries.size()
                      << " elapsed=" << elapsed() << "s" << std::endl;
            previous = std::move(current);
        }
        if (answered != queries.size()) throw std::runtime_error("Some query states were not found");
        out.close();
        if (!out) throw std::runtime_error("Failed writing metrics");
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }
}
